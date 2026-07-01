import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select

from analytics import (
    cumulative_pnl_history_df,
    option_label,
    client_bank_trades_for_group,
    payoff_curve_df,
    pnl_df,
    selected_trade_totals,
    trading_started,
    trades_df,
    orders_df,
    users_by_role,
)
from db import get_session
from matching import normalize_price
from models import MarketPrice, MarketPriceDraft, Option
from seed import seed_demo_data
from ui import (
    AUTO_REFRESH_INTERVAL,
    auto_refresh_caption,
    infer_refusal_reasons,
    inject_app_styles,
    require_login,
    show_table,
    show_user_sidebar,
    status_chips,
)

st.set_page_config(page_title="Professor", page_icon="mortar_board", layout="wide")

inject_app_styles()
user = require_login({"Professor"})


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
            select(Option).where(Option.is_active.is_(True)).order_by(Option.display_order, Option.id)
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
            select(Option).where(Option.is_active.is_(False)).order_by(Option.display_order, Option.id)
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
                "Published Bid": option.market_price.bid_price,
                "Published Ask": option.market_price.ask_price,
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
                "Published Bid": 9.0,
                "Published Ask": 11.0,
                "Draft Bid": 9.0,
                "Draft Ask": 11.0,
            }
        )
    return pd.DataFrame(rows)


def staged_market_change_count(rows: list[dict]) -> int:
    count = 0
    for row in rows:
        if normalize_price(row["Published Bid"]) != normalize_price(row["Draft Bid"]):
            count += 1
            continue
        if normalize_price(row["Published Ask"]) != normalize_price(row["Draft Ask"]):
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
        option.market_price.bid_price = normalize_price(row["Published Bid"])
        option.market_price.ask_price = normalize_price(row["Published Ask"])
        option.market_price_draft.draft_bid_price = normalize_price(row["Draft Bid"])
        option.market_price_draft.draft_ask_price = normalize_price(row["Draft Ask"])
    session.flush()


def publish_market_prices() -> tuple[bool, str]:
    with get_session() as session:
        rows = option_setup_rows(session).to_dict("records")
        errors = validate_setup_rows(rows, definitions_locked=True)
        if errors:
            return False, errors[0]

        for row in rows:
            option = session.get(Option, int(row["ID"]))
            ensure_market_rows(session, option)
            option.market_price.bid_price = normalize_price(row["Draft Bid"])
            option.market_price.ask_price = normalize_price(row["Draft Ask"])
    return True, "Market prices adjusted."


@st.fragment(run_every=AUTO_REFRESH_INTERVAL)
def render_professor_live_panel() -> None:
    with get_session() as session:
        all_orders = infer_refusal_reasons(orders_df(session))
        pending_orders = orders_df(session, status="Pending")
        refused_orders = infer_refusal_reasons(orders_df(session, status="Refused"))
        client_bank_trades = trades_df(session, source="Client-Bank")
        market_trades = trades_df(session, source="Market")
        pnl = pnl_df(session)
        pnl_history = cumulative_pnl_history_df(session)

    auto_refresh_caption()
    status_chips(
        {
            "Pending": len(pending_orders),
            "Matched": int((all_orders["Status"] == "Matched").sum()) if not all_orders.empty else 0,
            "Refused": len(refused_orders),
        }
    )

    metric_cols = st.columns(5)
    metric_cols[0].metric("Orders", len(all_orders))
    metric_cols[1].metric("Pending", len(pending_orders))
    metric_cols[2].metric("Refused", len(refused_orders))
    metric_cols[3].metric("Client-Bank Trades", len(client_bank_trades))
    metric_cols[4].metric("Market Trades", len(market_trades))

    refused_tab, client_bank_tab, market_tab, all_tab = st.tabs(
        ["Refused", "Client-Bank Trades", "Market Transactions", "All Declarations"]
    )
    with refused_tab:
        show_table(refused_orders, "No refused declarations.")
    with client_bank_tab:
        show_table(client_bank_trades, "No client-bank trades matched yet.")
    with market_tab:
        show_table(market_trades, "No market transactions yet.")
    with all_tab:
        show_table(all_orders, "No orders submitted yet.")

    st.divider()
    st.subheader("Analytics")

    if pnl_history.empty:
        st.info("No trades yet. P/L chart will appear after the first trade.")
    else:
        fig = px.line(
            pnl_history,
            x="Trade ID",
            y="Cumulative P/L",
            color="Participant",
            markers=True,
            title="Cumulative Profit / Loss",
        )
        st.plotly_chart(fig, width="stretch")
    show_table(pnl, "No participants found.")


def render_option_setup() -> None:
    with st.container(border=True):
        header_col, status_col = st.columns([3, 2], vertical_alignment="center")
        header_col.subheader("Option setup and market prices")

        with get_session() as session:
            definitions_locked = trading_started(session)
            current_count = len(active_options_for_setup(session))

        if definitions_locked:
            status_col.badge("Definitions locked", icon=":material/lock:", color="orange")
        else:
            status_col.badge("Definitions editable", icon=":material/edit:", color="green")

        if "prof_option_count_draft" not in st.session_state:
            st.session_state["prof_option_count_draft"] = max(current_count, 1)

        count_col, note_col = st.columns([1, 3], vertical_alignment="bottom")
        requested_count = count_col.number_input(
            "Active options",
            min_value=1,
            max_value=20,
            step=1,
            disabled=definitions_locked,
            key="prof_option_count_draft",
        )
        catalog_count_changed = int(requested_count) != current_count
        if definitions_locked:
            note_col.caption("Option definitions and count are locked after the first declaration.")
        elif catalog_count_changed:
            note_col.warning(
                f"Catalog update staged: desks still see {current_count} active option(s).",
                icon=":material/pending:",
            )
        else:
            note_col.caption("Edit option definitions and staged market prices in the table below.")

        with get_session() as session:
            setup_df = option_setup_rows(
                session,
                display_count=int(requested_count) if not definitions_locked else None,
            )

        disabled_columns = ["ID", "Published Bid", "Published Ask"]
        if definitions_locked:
            disabled_columns.extend(["Type", "Underlying", "Strike"])

        edited_df = st.data_editor(
            setup_df,
            key="prof_option_setup_editor",
            hide_index=True,
            width="stretch",
            num_rows="fixed",
            disabled=disabled_columns,
            column_config={
                "ID": st.column_config.TextColumn("ID", disabled=True),
                "Type": st.column_config.SelectboxColumn("Type", options=["Call", "Put"], required=True),
                "Underlying": st.column_config.TextColumn("Underlying", max_chars=30, required=True),
                "Strike": st.column_config.NumberColumn("Strike", min_value=1, step=1, format="%d"),
                "Published Bid": st.column_config.NumberColumn("Published bid", format="€ %.1f"),
                "Published Ask": st.column_config.NumberColumn("Published ask", format="€ %.1f"),
                "Draft Bid": st.column_config.NumberColumn("New bid", min_value=0.1, step=0.1, format="€ %.1f"),
                "Draft Ask": st.column_config.NumberColumn("New ask", min_value=0.1, step=0.1, format="€ %.1f"),
            },
        )

        rows = edited_df.to_dict("records")
        errors = validate_setup_rows(rows, definitions_locked)
        pending_changes = staged_market_change_count(rows) if not errors else 0
        if errors:
            st.error(errors[0], icon=":material/error:")
        else:
            with get_session() as session:
                apply_setup_rows(session, rows, definitions_locked)

        if not definitions_locked and catalog_count_changed:
            if st.button(
                "Update option catalog",
                type="primary",
                icon=":material/sync:",
                disabled=bool(errors),
                width="stretch",
            ):
                with get_session() as session:
                    apply_catalog_update(session, rows, int(requested_count))
                st.toast("Option catalog updated.")
                st.rerun()

        action_col, status_col = st.columns([1, 3], vertical_alignment="center")
        if action_col.button(
            "Adjust market prices",
            type="primary",
            icon=":material/publish:",
            disabled=bool(errors) or catalog_count_changed,
            width="stretch",
        ):
            success, message = publish_market_prices()
            if success:
                st.success(message, icon=":material/check_circle:")
                st.rerun()
            else:
                st.error(message, icon=":material/error:")

        if errors:
            status_col.caption("Fix the highlighted setup problem before publishing market prices.")
        elif catalog_count_changed:
            status_col.caption("Update the option catalog before publishing market price changes.")
        elif pending_changes:
            status_col.warning(
                f"{pending_changes} option price row(s) staged. Banks still see the published bid/ask.",
                icon=":material/pending:",
            )
        else:
            status_col.success("Published prices are up to date.", icon=":material/check_circle:")


def render_group_payoff_summary() -> None:
    with get_session() as session:
        participants = users_by_role(session, "Company") + users_by_role(session, "Bank")

    if not participants:
        st.info("No company or bank groups found.")
        return

    selected_user = st.selectbox("Group", participants, format_func=lambda item: item.username)
    with get_session() as session:
        trades = client_bank_trades_for_group(session, selected_user.id)

    if not trades:
        st.info("No matched client-bank trades for this group yet.")
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
            "Created": trade.created_at,
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
    total_cols[0].metric("Prices Paid", f"{paid:.1f}")
    total_cols[1].metric("Prices Received", f"{received:.1f}")

    curve = payoff_curve_df(selected_trades, selected_user.id)
    if curve.empty:
        st.info("Select at least one trade to show the payoff graph.")
    else:
        fig = px.line(
            curve,
            x="x",
            y="Payoff",
            title=f"Selected Position Payoff - {selected_user.username} / {selected_underlying}",
        )
        st.plotly_chart(fig, width="stretch")


st.title("Professor Control Room")
st.markdown(
    '<div class="role-strip">Configure options, publish market prices, monitor declarations, and review group outcomes.</div>',
    unsafe_allow_html=True,
)
show_user_sidebar(user)

with st.expander("Reset game state"):
    st.warning("This clears all orders and trades and restores demo users, options, and market prices.")
    if st.button("Reset game", type="primary"):
        seed_demo_data(reset=True)
        st.session_state.pop("prof_option_count", None)
        st.session_state.pop("prof_option_count_draft", None)
        st.success("Game state reset.")
        st.rerun()

render_option_setup()

st.divider()
st.subheader("Group Payoff Summary")
render_group_payoff_summary()

st.divider()
render_professor_live_panel()
