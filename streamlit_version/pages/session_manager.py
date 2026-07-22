from datetime import datetime, timedelta, timezone
from html import escape

import pandas as pd
import streamlit as st
from sqlalchemy import select

from db import get_session
from models import GameSession, MarketPrice, MarketPriceDraft, Option
from session_services import (
    add_participant,
    close_session,
    create_game_session,
    delete_preparation_session,
    duplicate_session,
    email_list_text,
    parse_emails,
    participants_for_session,
    remove_participant,
    session_query,
    set_participant_emails,
    start_session,
    status_label,
    validate_session_setup,
)
from state import bump_session_version
from ui import inject_app_styles, require_login, show_user_sidebar

st.set_page_config(page_title="Session Manager", page_icon="settings", layout="wide")

inject_app_styles()
user = require_login({"Professor"})


def set_managed_session() -> None:
    selected_id = st.session_state.get("managed_session_select")
    if selected_id is not None:
        st.session_state["managed_session_id"] = selected_id


def toggle_state(key: str) -> None:
    st.session_state[key] = not st.session_state.get(key, False)


def utc_plus_2_timestamp() -> str:
    paris_like_tz = timezone(timedelta(hours=2))
    return datetime.now(paris_like_tz).strftime("%Y-%m-%d %H:%M:%S UTC+2")


def ensure_market_rows(option: Option, bid_price: float = 9.0, ask_price: float = 11.0) -> None:
    if option.market_price is None:
        option.market_price = MarketPrice(option_id=option.id, bid_price=bid_price, ask_price=ask_price)
    if option.market_price_draft is None:
        option.market_price_draft = MarketPriceDraft(
            option_id=option.id,
            draft_bid_price=bid_price,
            draft_ask_price=ask_price,
        )


def default_underlying(display_order: int) -> str:
    return f"Asset {display_order}"


def option_rows(session, game_session_id: int) -> pd.DataFrame:
    options = list(
        session.scalars(
            select(Option)
            .where(Option.game_session_id == game_session_id, Option.is_active.is_(True))
            .order_by(Option.display_order, Option.id)
        )
    )
    rows = []
    for option in options:
        ensure_market_rows(option)
        rows.append(
            {
                "ID": option.id,
                "Type": option.option_type,
                "Underlying": option.underlying_asset,
                "Strike": option.strike_price,
                "Bid": option.market_price.bid_price,
                "Ask": option.market_price.ask_price,
            }
        )
    return pd.DataFrame(rows)


def validate_option_rows(rows: list[dict]) -> list[str]:
    errors = []
    seen = set()
    for index, row in enumerate(rows, start=1):
        try:
            option_type = str(row["Type"]).strip()
            underlying = "" if pd.isna(row["Underlying"]) else str(row["Underlying"]).strip()
            strike = int(row["Strike"])
            bid = round(float(row["Bid"]), 1)
            ask = round(float(row["Ask"]), 1)
        except (TypeError, ValueError):
            errors.append(f"Option #{index} has invalid numeric values.")
            continue
        if option_type not in {"Call", "Put"}:
            errors.append(f"Option #{index} must be Call or Put.")
        if not underlying:
            errors.append(f"Option #{index} needs an underlying asset.")
        if len(underlying) > 30:
            errors.append(f"Option #{index} underlying asset must be 30 characters or fewer.")
        if strike <= 0:
            errors.append(f"Option #{index} strike must be positive.")
        if bid <= 0 or ask <= 0:
            errors.append(f"Option #{index} bid and ask must be positive.")
        if ask <= bid:
            errors.append(f"Option #{index} ask must be strictly greater than bid.")
        signature = (option_type, underlying.lower(), strike)
        if signature in seen:
            errors.append(f"Duplicate active option: {option_type} {underlying} K={strike}.")
        seen.add(signature)
    return errors


def save_option_rows(session, game_session_id: int, rows: list[dict]) -> None:
    existing_options = {
        option.id: option
        for option in session.scalars(
            select(Option).where(Option.game_session_id == game_session_id).order_by(Option.display_order, Option.id)
        )
    }
    kept_ids = set()
    for display_order, row in enumerate(rows, start=1):
        option_id = row.get("ID")
        option = existing_options.get(int(option_id)) if not pd.isna(option_id) else None
        if option is None:
            option = Option(
                game_session_id=game_session_id,
                option_type="Call",
                underlying_asset=default_underlying(display_order),
                strike_price=100,
                is_active=True,
                display_order=display_order,
            )
            session.add(option)
            session.flush()
        kept_ids.add(option.id)
        option.display_order = display_order
        option.is_active = True
        option.option_type = str(row["Type"]).strip()
        option.underlying_asset = str(row["Underlying"]).strip()
        option.strike_price = int(row["Strike"])
        ensure_market_rows(option)
        option.market_price.bid_price = round(float(row["Bid"]), 1)
        option.market_price.ask_price = round(float(row["Ask"]), 1)
        option.market_price_draft.draft_bid_price = round(float(row["Bid"]), 1)
        option.market_price_draft.draft_ask_price = round(float(row["Ask"]), 1)

    for option_id, option in existing_options.items():
        if option_id not in kept_ids:
            option.is_active = False
    session.flush()
    bump_session_version(session, game_session_id)


def option_setup_state_keys(game_session_id: int) -> tuple[str, str, str]:
    prefix = f"session_options_setup_{game_session_id}"
    return f"{prefix}_source_rows", f"{prefix}_last_status", f"{prefix}_editor_nonce"


def load_option_setup_source_rows(game_session_id: int, force: bool = False) -> list[dict]:
    source_key, _, editor_nonce_key = option_setup_state_keys(game_session_id)
    if force or source_key not in st.session_state:
        with get_session() as session:
            setup_df = option_rows(session, game_session_id)
        if setup_df.empty:
            setup_df = pd.DataFrame(
                [
                    {
                        "ID": pd.NA,
                        "Type": "Call",
                        "Underlying": "Asset 1",
                        "Strike": 100,
                        "Bid": 9.0,
                        "Ask": 11.0,
                    }
                ]
            )
        st.session_state[source_key] = setup_df.to_dict("records")
        st.session_state.setdefault(editor_nonce_key, 0)
    return st.session_state[source_key]


def render_participant_cards(db_session, game_session: GameSession, role: str) -> None:
    participants = participants_for_session(db_session, game_session.id, role)
    header, action = st.columns([4, 1], vertical_alignment="center")
    header.subheader(f"{role}s")
    if action.button(
        ":material/add:", key=f"add_{role}_{game_session.id}", disabled=game_session.status != "preparation"
    ):
        with st.spinner(f"Adding {role.lower()}..."):
            add_participant(db_session, game_session.id, role)
        st.rerun()

    if not participants:
        st.caption(f"No {role.lower()}s yet.")
        return

    for row_start in range(0, len(participants), 2):
        columns = st.columns(2)
        for column, participant in zip(columns, participants[row_start : row_start + 2]):
            with column:
                with st.container(border=True):
                    name_key = f"participant_name_{participant.id}"
                    email_key = f"participant_emails_{participant.id}"
                    st.text_input(
                        "Name",
                        value=participant.username,
                        key=name_key,
                        disabled=game_session.status != "preparation",
                    )
                    st.text_area(
                        "Authorized emails",
                        value=email_list_text(participant),
                        key=email_key,
                        height=90,
                        disabled=game_session.status == "closed",
                    )
                    parsed = parse_emails(st.session_state[email_key])
                    st.caption(f"{len(parsed)} authorized email(s)")
                    controls = st.columns([1, 1])
                    if controls[0].button(
                        "Save",
                        key=f"save_participant_{participant.id}",
                        disabled=game_session.status == "closed",
                        width="stretch",
                    ):
                        with st.spinner("Saving participant..."):
                            new_name = st.session_state[name_key].strip()
                            name_changed = new_name != participant.username
                            participant.username = new_name
                            set_participant_emails(db_session, participant, parsed)
                            if name_changed:
                                bump_session_version(db_session, participant.game_session_id)
                        st.toast("Participant saved.")
                        st.rerun()
                    if controls[1].button(
                        ":material/delete:",
                        key=f"delete_participant_{participant.id}",
                        disabled=game_session.status != "preparation",
                        width="stretch",
                    ):
                        with st.spinner("Removing participant..."):
                            remove_participant(db_session, participant.id)
                        st.rerun()


@st.fragment
def render_options_setup(game_session_id: int, game_session_status: str) -> None:
    with st.container(border=True):
        st.subheader("Options")
        if game_session_status != "preparation":
            st.caption("Option definitions are locked after the session starts.")
        source_key, status_key, editor_nonce_key = option_setup_state_keys(game_session_id)
        source_rows = load_option_setup_source_rows(game_session_id)
        setup_df = pd.DataFrame([row.copy() for row in source_rows])
        edited = st.data_editor(
            setup_df,
            key=f"session_options_{game_session_id}_{st.session_state.get(editor_nonce_key, 0)}",
            hide_index=True,
            width="stretch",
            num_rows="dynamic" if game_session_status == "preparation" else "fixed",
            column_order=["Type", "Underlying", "Strike", "Bid", "Ask"],
            disabled=["ID"] if game_session_status == "preparation" else True,
            column_config={
                "ID": None,
                "Type": st.column_config.SelectboxColumn("Type", options=["Call", "Put"], required=True),
                "Underlying": st.column_config.TextColumn("Underlying", max_chars=30, required=True),
                "Strike": st.column_config.NumberColumn("Strike", min_value=1, step=1, format="%d"),
                "Bid": st.column_config.NumberColumn("Bid", min_value=0.1, step=0.1, format="€ %.1f"),
                "Ask": st.column_config.NumberColumn("Ask", min_value=0.1, step=0.1, format="€ %.1f"),
            },
        )
        rows = edited.to_dict("records")
        errors = validate_option_rows(rows)
        last_status = st.session_state.pop(status_key, None)
        if last_status is not None:
            status_type, status_message = last_status
            if status_type == "success":
                st.success(status_message, icon=":material/check_circle:")
            else:
                st.error(status_message, icon=":material/error:")
        if errors:
            st.error(errors[0])
        if st.button(
            "Save options",
            type="primary",
            disabled=bool(errors) or game_session_status != "preparation",
            width="stretch",
        ):
            with st.spinner("Saving options..."):
                with get_session() as session:
                    save_option_rows(session, game_session_id, rows)
                st.session_state[f"options_saved_at_{game_session_id}"] = utc_plus_2_timestamp()
                st.session_state[source_key] = load_option_setup_source_rows(game_session_id, force=True)
                st.session_state[editor_nonce_key] = st.session_state.get(editor_nonce_key, 0) + 1
                st.session_state[status_key] = ("success", "Options saved.")
            st.toast("Options saved.")
            st.rerun(scope="fragment")
        saved_at = st.session_state.get(f"options_saved_at_{game_session_id}")
        if saved_at:
            st.caption(f"Option data last updated at {saved_at}.")


def render_session_actions(db_session, game_session: GameSession) -> None:
    with st.container(border=True):
        st.subheader("Session actions")
        errors = validate_session_setup(db_session, game_session.id)
        if errors:
            st.warning(errors[0])
        else:
            st.success("Session setup is complete. You can start the session.", icon=":material/check_circle:")

        if game_session.status == "preparation":
            if st.button("Start session", type="primary", disabled=bool(errors), width="stretch"):
                with st.spinner("Starting session..."):
                    start_errors = start_session(db_session, game_session.id)
                if start_errors:
                    st.error(start_errors[0])
                else:
                    st.success("Session is live.")
                    st.rerun()
            confirm_delete = st.checkbox("Confirm delete draft", key=f"confirm_delete_{game_session.id}")
            if st.button("Delete preparation session", disabled=not confirm_delete, width="stretch"):
                with st.spinner("Deleting preparation session..."):
                    delete_preparation_session(db_session, game_session.id)
                    st.session_state.pop("managed_session_id", None)
                st.rerun()
        elif game_session.status == "live":
            confirm_close = st.checkbox("Confirm close session", key=f"confirm_close_{game_session.id}")
            if st.button("Close session", type="primary", disabled=not confirm_close, width="stretch"):
                with st.spinner("Closing session..."):
                    close_session(db_session, game_session.id)
                st.rerun()
        else:
            st.caption("Closed sessions are read-only.")

        duplicate_key = f"duplicate_session_open_{game_session.id}"
        if st.button("Duplicate session", key=f"toggle_duplicate_{game_session.id}", width="stretch"):
            toggle_state(duplicate_key)
        if st.session_state.get(duplicate_key, False):
            duplicate_name = st.text_input(
                "Duplicate as",
                value=f"{game_session.name} copy",
                key=f"duplicate_name_{game_session.id}",
            )
            copy_emails = st.checkbox(
                "Copy student emails",
                value=False,
                key=f"copy_student_emails_{game_session.id}",
            )
            if st.button("Create duplicate", type="primary", width="stretch"):
                with st.spinner("Duplicating session..."):
                    duplicated = duplicate_session(
                        db_session,
                        game_session.id,
                        duplicate_name,
                        copy_student_emails=copy_emails,
                        copy_professor_emails=True,
                    )
                    st.session_state["managed_session_id"] = duplicated.id
                    st.session_state["managed_session_select"] = duplicated.id
                st.rerun()


st.title("Session Manager")
show_user_sidebar(user)

with get_session() as db_session:
    sessions = list(db_session.scalars(session_query()).all())

    with st.container(border=True):
        st.subheader("Create session")
        new_name = st.text_input("Session name", value="New Session")
        if st.button("Create session", type="primary"):
            with st.spinner("Creating session..."):
                created = create_game_session(db_session, new_name)
                st.session_state["managed_session_id"] = created.id
            st.rerun()

    if not sessions:
        st.info("Create the first session to configure the game.")
        st.stop()

    session_ids = [session.id for session in sessions]
    labels_by_id = {session.id: f"{session.name} - {status_label(session.status)}" for session in sessions}
    selected_session_id = st.session_state.get("managed_session_id") or sessions[0].id
    if selected_session_id not in session_ids:
        selected_session_id = sessions[0].id
        st.session_state["managed_session_id"] = selected_session_id
    st.session_state["managed_session_select"] = selected_session_id

    selected_session = db_session.get(GameSession, selected_session_id)
    if selected_session is None:
        selected_session = sessions[0]

    with st.container(border=True):
        st.subheader("Session setting")
        selector_id = st.selectbox(
            "Select session",
            session_ids,
            index=session_ids.index(selected_session_id),
            format_func=lambda item_id: labels_by_id[item_id],
            key="managed_session_select",
            on_change=set_managed_session,
        )
        selected_session = db_session.get(GameSession, selector_id)

        header_name, header_status = st.columns([3.2, 1.45], vertical_alignment="center")
        header_name.markdown(
            f'<div class="session-header-name">{escape(selected_session.name)}</div>',
            unsafe_allow_html=True,
        )
        header_status.markdown(
            (
                '<div class="session-status-inline">'
                '<span class="session-status-label">Session status:</span>'
                f'<span class="session-status-pill session-status-pill-{selected_session.status}">'
                f"{status_label(selected_session.status)}</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

        rename_key = f"rename_session_open_{selected_session.id}"

        if st.button(
            "Rename",
            icon=":material/edit:",
            key=f"toggle_rename_{selected_session.id}",
            disabled=selected_session.status != "preparation",
        ):
            toggle_state(rename_key)
        if st.session_state.get(rename_key, False):
            new_session_name = st.text_input(
                "New session name",
                value=selected_session.name,
                key=f"rename_session_name_{selected_session.id}",
            )
            if st.button("Save session name", type="primary", key=f"save_session_name_{selected_session.id}"):
                with st.spinner("Renaming session..."):
                    cleaned_name = new_session_name.strip()
                    if cleaned_name and cleaned_name != selected_session.name:
                        selected_session.name = cleaned_name
                        bump_session_version(db_session, selected_session.id)
                    st.session_state[rename_key] = False
                st.toast("Session renamed.")
                st.rerun()

        top_left, top_right = st.columns([2, 1], gap="small")
        with top_left:
            with st.container(border=True):
                company_tab, bank_tab, option_tab = st.tabs(["Companies", "Banks", "Options"])
                with company_tab:
                    render_participant_cards(db_session, selected_session, "Company")
                with bank_tab:
                    render_participant_cards(db_session, selected_session, "Bank")
                with option_tab:
                    render_options_setup(selected_session.id, selected_session.status)
        with top_right:
            render_session_actions(db_session, selected_session)

    if selected_session.status in {"live", "closed"}:
        if st.button("Open control room", type="primary", width="stretch"):
            professor = participants_for_session(db_session, selected_session.id, "Professor")[0]
            st.session_state["user_id"] = professor.id
            st.session_state["game_session_id"] = selected_session.id
            st.session_state["role"] = "Professor"
            st.switch_page("pages/professor.py")
