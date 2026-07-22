import pandas as pd
import streamlit as st
from sqlalchemy import select

from analytics import (
    option_label,
    client_bank_trades_for_group,
    payoff_curve_df,
    selected_trade_totals,
    users_by_role,
)
from db import get_session
from exports import export_workbook_bytes, payoff_graph_zip_bytes, safe_filename
from matching import normalize_price
from models import GameSession, MarketPrice, MarketPriceDraft, Option
from session_services import status_label
from snapshots import professor_pnl_snapshot, professor_trade_history_snapshot
from state import bump_session_version, current_session_version
from ui import (
    AUTO_REFRESH_INTERVAL,
    auto_refresh_caption,
    inject_app_styles,
    require_login,
    show_table,
    show_user_sidebar,
    status_chips,
)

st.set_page_config(page_title="Professor", page_icon="mortar_board", layout="wide")

inject_app_styles()
user = require_login({"Professor"}, allowed_statuses={"live", "closed"})
GAME_SESSION_ID = int(st.session_state["game_session_id"])


def default_underlying(display_order: int) -> str:
    return f"Asset {display_order}"


def ensure_market_rows(session, option: Option, bid_price: float = 9.0, ask_price: float = 11.0) -> None:
    if option.market_price is None:
        option.market_price = MarketPrice(option_id=option.id, bid_price=bid_price, ask_price=ask_price)
    if option.market_price_draft is None:
        option.market_price_draft = MarketPriceDraft(
            option_id=option.id,
            draft_bid_price=bid_price,
            draft_ask_price=ask_price,
        )


def active_options_for_setup(session) -> list[Option]:
    return list(
        session.scalars(
            select(Option)
            .where(Option.game_session_id == GAME_SESSION_ID, Option.is_active.is_(True))
            .order_by(Option.display_order, Option.id)
        )
    )


def set_active_option_count(session, target_count: int) -> None:
    active_options = active_options_for_setup(session)
    if len(active_options) > target_count:
        for option in active_options[target_count:]:
            option.is_active = False
        session.flush()
        return

    inactive_options = list(
        session.scalars(
            select(Option)
            .where(Option.game_session_id == GAME_SESSION_ID, Option.is_active.is_(False))
            .order_by(Option.display_order, Option.id)
        )
    )
    while len(active_options) < target_count:
        display_order = len(active_options) + 1
        if inactive_options:
            option = inactive_options.pop(0)
            option.is_active = True
            option.display_order = display_order
        else:
            option = Option(
                game_session_id=GAME_SESSION_ID,
                option_type="Call",
                underlying_asset=default_underlying(display_order),
                strike_price=100 + (display_order - 1) * 10,
                is_active=True,
                display_order=display_order,
            )
            session.add(option)
            session.flush()
        ensure_market_rows(session, option)
        active_options.append(option)
    session.flush()


def option_setup_rows(session, display_count: int | None = None) -> pd.DataFrame:
    rows = []
    active_options = active_options_for_setup(session)
    target_count = len(active_options) if display_count is None else display_count
    for option in active_options[:target_count]:
        ensure_market_rows(session, option)
        rows.append(
            {
                "ID": str(option.id),
                "Type": option.option_type,
                "Underlying": option.underlying_asset,
                "Strike": option.strike_price,
                "Current Bid": option.market_price.bid_price,
                "Current Ask": option.market_price.ask_price,
                "Draft Bid": option.market_price_draft.draft_bid_price,
                "Draft Ask": option.market_price_draft.draft_ask_price,
            }
        )
    for display_order in range(len(rows) + 1, target_count + 1):
        rows.append(
            {
                "ID": f"New {display_order}",
                "Type": "Call",
                "Underlying": default_underlying(display_order),
                "Strike": 100 + (display_order - 1) * 10,
                "Current Bid": 9.0,
                "Current Ask": 11.0,
                "Draft Bid": 9.0,
                "Draft Ask": 11.0,
            }
        )
    return pd.DataFrame(rows)


def staged_market_change_count(rows: list[dict]) -> int:
    count = 0
    for row in rows:
        if normalize_price(row["Current Bid"]) != normalize_price(row["Draft Bid"]):
            count += 1
            continue
        if normalize_price(row["Current Ask"]) != normalize_price(row["Draft Ask"]):
            count += 1
    return count


def validate_setup_rows(rows: list[dict], definitions_locked: bool) -> list[str]:
    errors = []
    seen_options = set()
    for row in rows:
        option_id = row["ID"]
        try:
            option_type = str(row["Type"]).strip()
            underlying = "" if pd.isna(row["Underlying"]) else str(row["Underlying"]).strip()
            strike = int(row["Strike"])
            bid = normalize_price(row["Draft Bid"])
            ask = normalize_price(row["Draft Ask"])
        except (TypeError, ValueError):
            errors.append(f"Option #{option_id} has invalid numeric values.")
            continue

        if option_type not in {"Call", "Put"}:
            errors.append(f"Option #{option_id} must be Call or Put.")
        if not underlying:
            errors.append(f"Option #{option_id} needs an underlying asset.")
        if len(underlying) > 30:
            errors.append(f"Option #{option_id} underlying asset must be 30 characters or fewer.")
        if strike <= 0:
            errors.append(f"Option #{option_id} strike must be positive.")
        if bid <= 0 or ask <= 0:
            errors.append(f"Option #{option_id} bid and ask must be positive.")
        if ask <= bid:
            errors.append(f"Option #{option_id} ask must be strictly greater than bid.")

        if not definitions_locked:
            signature = (option_type, underlying.lower(), strike)
            if signature in seen_options:
                errors.append(f"Duplicate active option: {option_type} {underlying} K={strike}.")
            seen_options.add(signature)
    return errors


def apply_setup_rows(session, rows: list[dict], definitions_locked: bool) -> None:
    for row in rows:
        try:
            option_id = int(row["ID"])
        except (TypeError, ValueError):
            continue
        option = session.get(Option, option_id)
        if option is None:
            continue
        if not definitions_locked:
            option.option_type = str(row["Type"]).strip()
            option.underlying_asset = str(row["Underlying"]).strip()
            option.strike_price = int(row["Strike"])
        ensure_market_rows(session, option)
        option.market_price_draft.draft_bid_price = normalize_price(row["Draft Bid"])
        option.market_price_draft.draft_ask_price = normalize_price(row["Draft Ask"])
    session.flush()


def apply_catalog_update(session, rows: list[dict], target_count: int) -> None:
    set_active_option_count(session, target_count)
    active_options = active_options_for_setup(session)
    for option, row in zip(active_options, rows[:target_count]):
        option.option_type = str(row["Type"]).strip()
        option.underlying_asset = str(row["Underlying"]).strip()
        option.strike_price = int(row["Strike"])
        ensure_market_rows(session, option)
        option.market_price.bid_price = normalize_price(row["Current Bid"])
        option.market_price.ask_price = normalize_price(row["Current Ask"])
        option.market_price_draft.draft_bid_price = normalize_price(row["Draft Bid"])
        option.market_price_draft.draft_ask_price = normalize_price(row["Draft Ask"])
    session.flush()
    bump_session_version(session, GAME_SESSION_ID)


def publish_market_prices(rows: list[dict]) -> tuple[bool, str]:
    with get_session() as session:
        game_session = session.get(GameSession, GAME_SESSION_ID)
        if game_session is None or game_session.status != "live":
            return False, "Market prices can only be adjusted while the session is Live."
        errors = validate_setup_rows(rows, definitions_locked=True)
        if errors:
            return False, errors[0]

        for row in rows:
            option = session.get(Option, int(row["ID"]))
            ensure_market_rows(session, option)
            option.market_price.bid_price = normalize_price(row["Draft Bid"])
            option.market_price.ask_price = normalize_price(row["Draft Ask"])
            option.market_price_draft.draft_bid_price = normalize_price(row["Draft Bid"])
            option.market_price_draft.draft_ask_price = normalize_price(row["Draft Ask"])
        bump_session_version(session, GAME_SESSION_ID)
    return True, "Market prices are up to date"


def market_price_state_keys() -> tuple[str, str, str]:
    prefix = f"prof_market_prices_{GAME_SESSION_ID}"
    return f"{prefix}_source_rows", f"{prefix}_last_status", f"{prefix}_editor_nonce"


def load_market_price_source_rows(force: bool = False) -> list[dict]:
    source_key, _, editor_nonce_key = market_price_state_keys()
    if force or source_key not in st.session_state:
        with get_session() as session:
            st.session_state[source_key] = option_setup_rows(session).to_dict("records")
        st.session_state.setdefault(editor_nonce_key, 0)
    return st.session_state[source_key]


def market_price_df_from_rows(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([row.copy() for row in rows])


def refusal_reason_for_pair(first, second) -> str:
    price_mismatch = normalize_price(first["Price"]) != normalize_price(second["Price"])
    side_mismatch = first["Side"] == second["Side"]
    if price_mismatch and side_mismatch:
        return "Price and side mismatch"
    if price_mismatch:
        return "Price mismatch"
    if side_mismatch:
        return "Side mismatch"
    return "Entered terms did not match"


def stable_participants_label(rows) -> str:
    names = {row["Submitted By"] for row in rows} | {row["Counterparty"] for row in rows}
    companies = sorted(name for name in names if str(name).startswith("Company"))
    banks = sorted(name for name in names if str(name).startswith("Bank"))
    if companies and banks:
        return f"{companies[0]} ↔ {banks[0]}"
    return " ↔ ".join(sorted(names))


def refusal_cases(rejected_orders: pd.DataFrame) -> list[dict]:
    if rejected_orders.empty:
        return []

    ordered = rejected_orders.sort_values("Created", ascending=True).reset_index(drop=True)
    used_indexes = set()
    cases = []

    for index, row in ordered.iterrows():
        if index in used_indexes:
            continue

        pair_index = None
        if "Paired Order ID" in ordered.columns and not pd.isna(row["Paired Order ID"]):
            paired_rows = ordered.index[ordered["ID"] == row["Paired Order ID"]].tolist()
            pair_index = paired_rows[0] if paired_rows else None

        if pair_index is None:
            for candidate_index, candidate in ordered.iterrows():
                if candidate_index == index or candidate_index in used_indexes:
                    continue
                if (
                    row["Submitted By"] == candidate["Counterparty"]
                    and row["Counterparty"] == candidate["Submitted By"]
                    and row["Option"] == candidate["Option"]
                ):
                    pair_index = candidate_index
                    break

        used_indexes.add(index)
        rows = [row]
        reason = row.get("Refusal Reason", "Entered terms did not match")
        if pair_index is not None:
            used_indexes.add(pair_index)
            paired_row = ordered.loc[pair_index]
            rows.append(paired_row)
            reason = refusal_reason_for_pair(row, paired_row)

        cases.append(
            {
                "participants": stable_participants_label(rows),
                "option": row["Option"],
                "reason": reason,
                "rows": rows,
            }
        )

    return list(reversed(cases))


def render_refusal_cases(rejected_orders: pd.DataFrame) -> None:
    cases = refusal_cases(rejected_orders)
    if not cases:
        st.caption("No rejected declarations.")
        return

    rows = []
    for case_number, case in enumerate(cases, start=1):
        company_row = None
        bank_row = None
        for row in case["rows"]:
            if str(row["Submitted By"]).startswith("Company"):
                company_row = row
            elif str(row["Submitted By"]).startswith("Bank"):
                bank_row = row

        first_row = case["rows"][0]
        second_row = case["rows"][1] if len(case["rows"]) > 1 else None
        company_row = company_row if company_row is not None else first_row
        bank_row = bank_row if bank_row is not None and bank_row is not company_row else second_row

        company_declaration = (
            f"{company_row['Side']} · € {company_row['Price']:.1f}" if company_row is not None else "Missing"
        )
        bank_declaration = f"{bank_row['Side']} · € {bank_row['Price']:.1f}" if bank_row is not None else "Missing"
        times = [row["Created"].strftime("%H:%M:%S") for row in case["rows"]]

        rows.append(
            {
                "Participants": case["participants"],
                "Option": case["option"],
                "Issue": case["reason"],
                "Company declaration": company_declaration,
                "Bank declaration": bank_declaration,
                "Submitted": " / ".join(times),
            }
        )

    show_table(pd.DataFrame(rows), "No rejected declarations.", hide_id=False)


@st.fragment(run_every=AUTO_REFRESH_INTERVAL)
def render_trade_history() -> None:
    snapshot = professor_trade_history_snapshot(GAME_SESSION_ID, current_session_version(GAME_SESSION_ID))
    all_orders = snapshot["all_orders"]
    pending_orders = snapshot["pending_orders"]
    rejected_orders = snapshot["rejected_orders"]
    client_bank_trades = snapshot["client_bank_trades"]
    market_trades = snapshot["market_trades"]

    auto_refresh_caption()
    with st.container(border=True):
        st.subheader("Trades")
        status_chips(
            {
                "Pending": len(pending_orders),
                "Matched": int((all_orders["Status"] == "Matched").sum()) if not all_orders.empty else 0,
                "Rejected": len(rejected_orders),
            }
        )

        client_bank_tab, market_tab, all_tab = st.tabs(["Company-Bank trades", "Market trades", "All declarations"])
        with client_bank_tab:
            show_table(client_bank_trades, "No company-bank trades matched yet.")
        with market_tab:
            show_table(market_trades, "No market trades yet.")
        with all_tab:
            show_table(all_orders, "No orders submitted yet.")
        with st.expander("Troubleshooting: rejected declarations"):
            render_refusal_cases(rejected_orders)


@st.fragment
def render_professor_analytics() -> None:
    if not st.toggle("Cash balance", key="show_cash_balance_analytics"):
        return

    snapshot = professor_pnl_snapshot(GAME_SESSION_ID, current_session_version(GAME_SESSION_ID))
    pnl = snapshot["pnl"].rename(columns={"Cumulative P/L": "Cash balance"})
    pnl_history = snapshot["pnl_history"].rename(columns={"Cumulative P/L": "Cash balance"})

    if pnl_history.empty:
        st.info("No trades yet. Cash balance chart will appear after the first trade.")
    else:
        import plotly.express as px

        fig = px.line(
            pnl_history,
            x="Trade ID",
            y="Cash balance",
            color="Participant",
            markers=True,
        )
        fig.update_layout(margin=dict(l=8, r=8, t=8, b=8), height=360)
        st.plotly_chart(fig, width="stretch")
    show_table(pnl, "No participants found.")


@st.fragment
def render_option_setup(game_session_status: str | None) -> None:
    with st.container(border=True):
        st.subheader("Market prices")
        st.caption("Modify the bid and ask values shown to banks during the live session.")
        prices_locked = game_session_status != "live"

        source_key, status_key, editor_nonce_key = market_price_state_keys()
        source_rows = load_market_price_source_rows()
        setup_df = market_price_df_from_rows(source_rows)

        disabled_columns = ["ID", "Type", "Underlying", "Strike", "Current Bid", "Current Ask"]
        if prices_locked:
            disabled_columns.extend(["Draft Bid", "Draft Ask"])

        edited_df = st.data_editor(
            setup_df,
            key=f"prof_option_setup_editor_{GAME_SESSION_ID}_{st.session_state.get(editor_nonce_key, 0)}",
            hide_index=True,
            width="stretch",
            column_order=["Type", "Underlying", "Strike", "Current Bid", "Current Ask", "Draft Bid", "Draft Ask"],
            num_rows="fixed",
            disabled=disabled_columns,
            column_config={
                "ID": None,
                "Type": st.column_config.SelectboxColumn("Type", options=["Call", "Put"], required=True),
                "Underlying": st.column_config.TextColumn("Underlying", max_chars=30, required=True),
                "Strike": st.column_config.NumberColumn("Strike", min_value=1, step=1, format="%d"),
                "Current Bid": st.column_config.NumberColumn("Current bid", format="€ %.1f"),
                "Current Ask": st.column_config.NumberColumn("Current ask", format="€ %.1f"),
                "Draft Bid": st.column_config.NumberColumn("New bid", min_value=0.1, step=0.1, format="€ %.1f"),
                "Draft Ask": st.column_config.NumberColumn("New ask", min_value=0.1, step=0.1, format="€ %.1f"),
            },
        )

        rows = edited_df.to_dict("records")
        errors = validate_setup_rows(rows, definitions_locked=True)
        pending_changes = staged_market_change_count(rows) if not errors else 0
        last_status = st.session_state.pop(status_key, None)
        if last_status is not None:
            status_type, status_message = last_status
            if status_type == "success":
                st.success(status_message, icon=":material/check_circle:")
            else:
                st.error(status_message, icon=":material/error:")

        if errors:
            st.error(errors[0], icon=":material/error:")

        if errors:
            st.caption("Fix the highlighted setup problem before updating market prices.")
        elif pending_changes:
            action_col, status_col = st.columns([1, 3], vertical_alignment="center")
            if action_col.button(
                "Adjust market prices",
                type="primary",
                icon=":material/publish:",
                disabled=prices_locked,
                width="stretch",
            ):
                with st.spinner("Adjusting market prices..."):
                    success, message = publish_market_prices(rows)
                if success:
                    st.session_state[source_key] = [
                        {
                            **row,
                            "Current Bid": normalize_price(row["Draft Bid"]),
                            "Current Ask": normalize_price(row["Draft Ask"]),
                            "Draft Bid": normalize_price(row["Draft Bid"]),
                            "Draft Ask": normalize_price(row["Draft Ask"]),
                        }
                        for row in rows
                    ]
                    st.session_state[editor_nonce_key] = st.session_state.get(editor_nonce_key, 0) + 1
                    st.session_state[status_key] = ("success", message)
                    st.rerun(scope="fragment")
                else:
                    st.session_state[status_key] = ("error", message)
                    st.rerun(scope="fragment")
            status_col.warning(
                f"{pending_changes} option price row(s) staged. Banks still see the current bid/ask.",
                icon=":material/pending:",
            )
        elif prices_locked:
            st.caption("Market prices are read-only because the session is closed.")


def render_group_payoff_summary() -> None:
    with get_session() as session:
        participants = users_by_role(session, "Company", GAME_SESSION_ID) + users_by_role(
            session, "Bank", GAME_SESSION_ID
        )

    if not participants:
        st.info("No company or bank groups found.")
        return

    selected_user = st.selectbox("Group", participants, format_func=lambda item: item.username)
    with get_session() as session:
        trades = client_bank_trades_for_group(session, GAME_SESSION_ID, selected_user.id)

    if not trades:
        st.info("No matched company-bank trades for this group yet.")
        return

    underlyings = sorted({trade.option.underlying_asset for trade in trades})
    selected_underlying = st.selectbox("Underlying", underlyings)
    underlying_trades = [trade for trade in trades if trade.option.underlying_asset == selected_underlying]

    trade_rows = [
        {
            "Select": True,
            "ID": trade.id,
            "Option": option_label(trade.option),
            "Side": "Buy" if trade.buyer_id == selected_user.id else "Sell",
            "Price": trade.price,
            "Buyer": trade.buyer.username,
            "Seller": trade.seller.username,
            "Created": trade.created_at.strftime("%H:%M:%S"),
        }
        for trade in underlying_trades
    ]
    edited = st.data_editor(
        pd.DataFrame(trade_rows),
        hide_index=True,
        width="stretch",
        disabled=["ID", "Option", "Side", "Price", "Buyer", "Seller", "Created"],
        column_config={"Select": st.column_config.CheckboxColumn("Select")},
    )
    selected_ids = set(edited.loc[edited["Select"], "ID"].tolist()) if not edited.empty else set()
    selected_trades = [trade for trade in underlying_trades if trade.id in selected_ids]

    paid, received = selected_trade_totals(selected_trades, selected_user.id)
    total_cols = st.columns(2)
    total_cols[0].metric("Paid", f"{paid:.1f}")
    total_cols[1].metric("Received", f"{received:.1f}")

    curve = payoff_curve_df(selected_trades, selected_user.id)
    if curve.empty:
        st.info("Select at least one trade to show the payoff graph.")
    else:
        import plotly.express as px

        fig = px.line(
            curve,
            x="x",
            y="Payoff",
        )
        fig.update_layout(margin=dict(l=8, r=8, t=8, b=8), height=320)
        st.plotly_chart(fig, width="stretch")


@st.fragment
def render_exports(selected_session_name: str | None) -> None:
    if selected_session_name is None:
        return
    with st.container(border=True):
        st.subheader("Exports")
        export_cols = st.columns(2)

        workbook_key = f"excel_export_bytes_{GAME_SESSION_ID}"
        graph_zip_key = f"payoff_graph_zip_bytes_{GAME_SESSION_ID}"

        if export_cols[0].button(
            "Prepare Excel workbook",
            icon=":material/table:",
            width="stretch",
            key=f"prepare_excel_export_{GAME_SESSION_ID}",
        ):
            try:
                with st.spinner("Preparing Excel workbook..."):
                    with get_session() as session:
                        st.session_state[workbook_key] = export_workbook_bytes(session, GAME_SESSION_ID)
            except Exception as exc:
                st.session_state.pop(workbook_key, None)
                export_cols[0].error(f"Workbook export unavailable: {exc}")

        workbook = st.session_state.get(workbook_key)
        if workbook:
            export_cols[0].download_button(
                "Download Excel workbook",
                data=workbook,
                file_name=f"{safe_filename(selected_session_name)}_trading_game.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )

        if export_cols[1].button(
            "Prepare payoff graphs",
            icon=":material/area_chart:",
            width="stretch",
            key=f"prepare_graph_export_{GAME_SESSION_ID}",
        ):
            try:
                with st.spinner("Preparing payoff graphs..."):
                    with get_session() as session:
                        st.session_state[graph_zip_key] = payoff_graph_zip_bytes(session, GAME_SESSION_ID)
            except Exception as exc:
                st.session_state.pop(graph_zip_key, None)
                export_cols[1].error(f"Payoff graph export unavailable: {exc}")

        graph_zip = st.session_state.get(graph_zip_key)
        if graph_zip is not None:
            if graph_zip:
                export_cols[1].download_button(
                    "Download payoff graphs",
                    data=graph_zip,
                    file_name=f"{safe_filename(selected_session_name)}_payoff_graphs.zip",
                    mime="application/zip",
                    width="stretch",
                )
            else:
                export_cols[1].caption("No payoff graphs available yet.")


with get_session() as session:
    selected_session = session.get(GameSession, GAME_SESSION_ID)

st.title("Professor control room")
if selected_session is not None:
    st.markdown(
        f'<div class="role-strip">{selected_session.name} · {status_label(selected_session.status)}</div>',
        unsafe_allow_html=True,
    )
show_user_sidebar(user)

if st.button("Back to Session Manager", width="content"):
    st.switch_page("pages/session_manager.py")

top_left, top_right = st.columns(2)
with top_left:
    render_option_setup(selected_session.status if selected_session is not None else None)
with top_right:
    render_trade_history()

with st.container(border=True):
    st.subheader("Group payoff")
    render_group_payoff_summary()

render_exports(selected_session.name if selected_session is not None else None)
render_professor_analytics()
