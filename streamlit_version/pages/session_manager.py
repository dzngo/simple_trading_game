import pandas as pd
import streamlit as st
from sqlalchemy import select

from db import get_session
from models import GameSession, MarketPrice, MarketPriceDraft, Option
from session_manager import (
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


def render_participant_cards(db_session, game_session: GameSession, role: str) -> None:
    participants = participants_for_session(db_session, game_session.id, role)
    header, action = st.columns([4, 1], vertical_alignment="center")
    header.subheader(f"{role}s")
    if action.button(":material/add:", key=f"add_{role}_{game_session.id}", disabled=game_session.status != "preparation"):
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
                        remove_participant(db_session, participant.id)
                        st.rerun()


def render_professor_emails(db_session, game_session: GameSession) -> None:
    professor = participants_for_session(db_session, game_session.id, "Professor")[0]
    with st.container(border=True):
        st.subheader("Professor access")
        email_key = f"professor_emails_{professor.id}"
        st.text_area(
            "Authorized professor emails",
            value=email_list_text(professor),
            key=email_key,
            height=90,
            disabled=game_session.status == "closed",
        )
        st.caption(f"{len(parse_emails(st.session_state[email_key]))} authorized email(s)")
        if st.button("Save professor emails", disabled=game_session.status == "closed", width="stretch"):
            set_participant_emails(
                db_session,
                professor,
                parse_emails(st.session_state[email_key]),
            )
            st.toast("Professor emails saved.")
            st.rerun()


def render_options_setup(db_session, game_session: GameSession) -> None:
    with st.container(border=True):
        st.subheader("Options")
        if game_session.status != "preparation":
            st.caption("Option definitions are locked after the session starts.")
        setup_df = option_rows(db_session, game_session.id)
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
        edited = st.data_editor(
            setup_df,
            key=f"session_options_{game_session.id}",
            hide_index=True,
            width="stretch",
            num_rows="dynamic" if game_session.status == "preparation" else "fixed",
            disabled=["ID"] if game_session.status == "preparation" else True,
            column_config={
                "ID": st.column_config.NumberColumn("ID", disabled=True),
                "Type": st.column_config.SelectboxColumn("Type", options=["Call", "Put"], required=True),
                "Underlying": st.column_config.TextColumn("Underlying", max_chars=30, required=True),
                "Strike": st.column_config.NumberColumn("Strike", min_value=1, step=1, format="%d"),
                "Bid": st.column_config.NumberColumn("Bid", min_value=0.1, step=0.1, format="€ %.1f"),
                "Ask": st.column_config.NumberColumn("Ask", min_value=0.1, step=0.1, format="€ %.1f"),
            },
        )
        rows = edited.to_dict("records")
        errors = validate_option_rows(rows)
        if errors:
            st.error(errors[0])
        if st.button(
            "Save options",
            type="primary",
            disabled=bool(errors) or game_session.status != "preparation",
            width="stretch",
        ):
            save_option_rows(db_session, game_session.id, rows)
            st.toast("Options saved.")
            st.rerun()


def render_session_actions(db_session, game_session: GameSession) -> None:
    with st.container(border=True):
        st.subheader("Session actions")
        st.badge(status_label(game_session.status))
        errors = validate_session_setup(db_session, game_session.id)
        if errors:
            st.warning(errors[0])
        if game_session.status == "preparation":
            if st.button("Start session", type="primary", disabled=bool(errors), width="stretch"):
                start_errors = start_session(db_session, game_session.id)
                if start_errors:
                    st.error(start_errors[0])
                else:
                    st.success("Session is live.")
                    st.rerun()
            confirm_delete = st.checkbox("Confirm delete draft", key=f"confirm_delete_{game_session.id}")
            if st.button("Delete preparation session", disabled=not confirm_delete, width="stretch"):
                delete_preparation_session(db_session, game_session.id)
                st.session_state.pop("managed_session_id", None)
                st.rerun()
        elif game_session.status == "live":
            confirm_close = st.checkbox("Confirm close session", key=f"confirm_close_{game_session.id}")
            if st.button("Close session", type="primary", disabled=not confirm_close, width="stretch"):
                close_session(db_session, game_session.id)
                st.rerun()
        else:
            st.caption("Closed sessions are read-only.")

        duplicate_name = st.text_input(
            "Duplicate as",
            value=f"{game_session.name} copy",
            key=f"duplicate_name_{game_session.id}",
        )
        copy_emails = st.checkbox("Copy student emails", value=False, key=f"copy_student_emails_{game_session.id}")
        if st.button("Duplicate setup", width="stretch"):
            duplicated = duplicate_session(
                db_session,
                game_session.id,
                duplicate_name,
                copy_student_emails=copy_emails,
                copy_professor_emails=True,
            )
            st.session_state["managed_session_id"] = duplicated.id
            st.rerun()


st.title("Session Manager")
show_user_sidebar(user)

with get_session() as db_session:
    sessions = list(db_session.scalars(session_query()).all())

    with st.container(border=True):
        st.subheader("Create session")
        new_name = st.text_input("Session name", value="New Session")
        if st.button("Create session", type="primary"):
            created = create_game_session(db_session, new_name)
            st.session_state["managed_session_id"] = created.id
            st.rerun()

    if not sessions:
        st.info("Create the first session to configure the game.")
        st.stop()

    selected_session_id = st.session_state.get("managed_session_id") or sessions[0].id
    selected_session = db_session.get(GameSession, selected_session_id)
    if selected_session is None:
        selected_session = sessions[0]

    selector = st.selectbox(
        "Session",
        sessions,
        index=sessions.index(selected_session),
        format_func=lambda item: f"{item.name} - {status_label(item.status)}",
    )
    st.session_state["managed_session_id"] = selector.id
    selected_session = db_session.get(GameSession, selector.id)

    header_left, header_right = st.columns([3, 1], vertical_alignment="center")
    if selected_session.status == "preparation":
        new_session_name = header_left.text_input("Selected session name", value=selected_session.name)
        if new_session_name.strip() != selected_session.name:
            selected_session.name = new_session_name.strip()
            bump_session_version(db_session, selected_session.id)
    else:
        header_left.subheader(selected_session.name)
    header_right.badge(status_label(selected_session.status))

    top_left, top_right = st.columns([2, 1], gap="large")
    with top_left:
        company_tab, bank_tab, option_tab = st.tabs(["Companies", "Banks", "Options"])
        with company_tab:
            render_participant_cards(db_session, selected_session, "Company")
        with bank_tab:
            render_participant_cards(db_session, selected_session, "Bank")
        with option_tab:
            render_options_setup(db_session, selected_session)
    with top_right:
        render_professor_emails(db_session, selected_session)
        render_session_actions(db_session, selected_session)

    if selected_session.status in {"live", "closed"}:
        if st.button("Open control room", type="primary", width="stretch"):
            professor = participants_for_session(db_session, selected_session.id, "Professor")[0]
            st.session_state["user_id"] = professor.id
            st.session_state["game_session_id"] = selected_session.id
            st.session_state["role"] = "Professor"
            st.switch_page("pages/professor.py")
