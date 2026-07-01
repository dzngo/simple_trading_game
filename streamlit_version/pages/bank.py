import streamlit as st

from analytics import (
    active_options,
    market_price_for_option,
    market_prices_df,
    option_label,
    orders_df,
    trades_df,
    users_by_role,
)
from db import get_session
from matching import create_market_trade, create_trade_declaration
from ui import (
    AUTO_REFRESH_INTERVAL,
    attention_queue_df,
    auto_refresh_caption,
    infer_refusal_reasons,
    inject_app_styles,
    render_trade_status_panel,
    require_login,
    show_table,
    show_user_sidebar,
)


st.set_page_config(page_title="Bank", page_icon="bank", layout="wide")

inject_app_styles()
user = require_login({"Bank"})


def get_market_prices(option_id: int) -> tuple[float, float]:
    with get_session() as session:
        return market_price_for_option(session, option_id)


@st.fragment(run_every=AUTO_REFRESH_INTERVAL)
def render_bank_live_panel(user_id: int) -> None:
    with get_session() as session:
        option_options = active_options(session)
        company_options = users_by_role(session, "Company")
        market_prices = market_prices_df(session)
        orders = orders_df(session, user_id=user_id)
        orders_with_reasons = infer_refusal_reasons(orders)
        attention = attention_queue_df(orders_with_reasons)
        trades = trades_df(session, user_id=user_id, source="Client-Bank")

    auto_refresh_caption()
    render_trade_status_panel(orders, user_id)

    st.caption(f"{len(option_options)} active options | {len(company_options)} companies")

    st.subheader("Market prices")
    show_table(market_prices, "No market prices configured.")

    st.subheader("Needs attention")
    show_table(attention, "No pending or refused declarations.")

    st.subheader("Confirmed trades")
    show_table(trades, "No matched trades yet.")

    with st.expander("Declaration log"):
        show_table(orders_with_reasons, "No trade declarations yet.")


st.title("Bank desk")
st.markdown(
    '<div class="role-strip">Confirm verbal trades with companies, or trade directly with the professor-set market.</div>',
    unsafe_allow_html=True,
)
show_user_sidebar(user)

with get_session() as session:
    option_options = active_options(session)
    company_options = users_by_role(session, "Company")

left, right = st.columns([1, 1.35], gap="large")

with left:
    with st.container(border=True):
        st.subheader("Client trade declaration")

        if not option_options or not company_options:
            st.info("The professor must configure active options and companies before declarations can be submitted.")
        else:
            option = st.selectbox("Option", option_options, format_func=option_label, key="bank_client_option")
            side = st.segmented_control("Side", ["Buy", "Sell"], default="Buy", key="bank_declaration_side")
            bid_price, ask_price = get_market_prices(option.id)
            suggested_price = ask_price if side == "Sell" else bid_price

            if (
                st.session_state.get("bank_price_option_id") != option.id
                or st.session_state.get("bank_price_side") != side
            ):
                st.session_state["bank_agreed_price"] = suggested_price
                st.session_state["bank_price_option_id"] = option.id
                st.session_state["bank_price_side"] = side

            price_col, button_col = st.columns([1, 1])
            price_col.metric("Suggested Price", f"{suggested_price:.1f}")
            if button_col.button("Use bid/ask", width="stretch"):
                st.session_state["bank_agreed_price"] = suggested_price
                st.rerun()

            st.number_input(
                "Agreed price",
                min_value=0.1,
                step=0.1,
                format="%.1f",
                key="bank_agreed_price",
            )
            counterparty = st.selectbox(
                "Company counterparty",
                company_options,
                format_func=lambda item: item.username,
                key="bank_counterparty",
            )
            submitted = st.button("Submit declaration", type="primary", width="stretch")

            if submitted:
                submitted_price = float(st.session_state["bank_agreed_price"])
                with get_session() as session:
                    order, trade = create_trade_declaration(
                        session=session,
                        user_id=user.id,
                        counterparty_id=counterparty.id,
                        option_id=option.id,
                        side=side,
                        price=submitted_price,
                    )
                if trade is None:
                    if order.status == "Refused":
                        st.error(f"Order #{order.id} was refused because the company declaration did not match.")
                    else:
                        st.info(
                            f"Order #{order.id} is pending until {counterparty.username} enters the compatible side."
                        )
                else:
                    st.success(f"Order #{order.id} matched and trade #{trade.id} was recorded.")
                st.rerun()

    with st.container(border=True):
        st.subheader("Market trade")
        st.caption("Market trades execute immediately at the published professor-set bid/ask.")

        if not option_options:
            st.info("No active options configured.")
        else:
            market_option = st.selectbox(
                "Market option", option_options, format_func=option_label, key="market_option"
            )
            market_side = st.segmented_control("Market side", ["Buy", "Sell"], default="Buy", key="market_side")
            market_bid, market_ask = get_market_prices(market_option.id)
            execution_price = market_ask if market_side == "Buy" else market_bid
            st.metric("Execution Price", f"{execution_price:.1f}")
            if st.button("Execute market trade", type="primary", width="stretch"):
                with get_session() as session:
                    trade = create_market_trade(
                        session=session,
                        bank_id=user.id,
                        option_id=market_option.id,
                        side=market_side,
                    )
                st.success(f"Market trade #{trade.id} executed at {trade.price:.1f}.")
                st.rerun()

with right:
    render_bank_live_panel(user.id)
