import streamlit as st

from analytics import (
    market_price_for_product,
    market_prices_df,
    orders_df,
    products,
    trades_df,
    users_by_role,
)
from db import get_session
from matching import create_trade_declaration
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


st.set_page_config(page_title="Bank", page_icon="bank", layout="wide")

user = require_login({"Bank"})
show_user_sidebar(user)
inject_app_styles()


def get_market_price(product_id: int) -> float:
    with get_session() as session:
        return market_price_for_product(session, product_id)


@st.fragment(run_every=AUTO_REFRESH_INTERVAL)
def render_selected_market_price(product_id: int) -> None:
    st.metric("Market Price", get_market_price(product_id))


@st.fragment(run_every=AUTO_REFRESH_INTERVAL)
def render_bank_live_panel(user_id: int) -> None:
    with get_session() as session:
        product_options = products(session)
        company_options = users_by_role(session, "Company")
        market_prices = market_prices_df(session)
        pending = orders_df(session, user_id=user_id, status="Pending")
        matched = orders_df(session, user_id=user_id, status="Matched")
        refused = infer_refusal_reasons(orders_df(session, user_id=user_id, status="Refused"))
        orders = infer_refusal_reasons(orders_df(session, user_id=user_id))
        trades = trades_df(session, user_id=user_id)

    auto_refresh_caption()
    status_chips({"Pending": len(pending), "Matched": len(matched), "Refused": len(refused)})

    metric_cols = st.columns(4)
    metric_cols[0].metric("Companies", len(company_options))
    metric_cols[1].metric("Products", len(product_options))
    metric_cols[2].metric("Pending", len(pending))
    metric_cols[3].metric("Matched Trades", len(trades))

    st.subheader("Attention Queue")
    attention_tabs = st.tabs(["Pending", "Refused"])
    with attention_tabs[0]:
        show_table(pending, "No pending declarations.")
    with attention_tabs[1]:
        show_table(refused, "No refused declarations.")

    st.subheader("Market Prices")
    show_table(market_prices, "No market prices configured.")

    st.divider()
    tab_trades, tab_history = st.tabs(["Matched Trades", "Declaration History"])
    with tab_trades:
        show_table(trades, "No matched trades yet.")
    with tab_history:
        show_table(orders, "No trade declarations yet.")

st.title("Bank Desk")
st.markdown(
    '<div class="role-strip">Quote companies using the professor-set Market Price, then confirm trades through matching declarations.</div>',
    unsafe_allow_html=True,
)

with get_session() as session:
    product_options = products(session)
    company_options = users_by_role(session, "Company")

left, right = st.columns([1, 1.35], gap="large")

with left:
    st.subheader("Client Trade Declaration")
    st.caption("Use the professor-set Market Price as a quick quote, or type a negotiated price.")
    product = st.selectbox("Product", product_options, format_func=lambda item: item.name)
    selected_market_price = get_market_price(product.id)
    if st.session_state.get("bank_price_product_id") != product.id:
        st.session_state["bank_agreed_price"] = selected_market_price
        st.session_state["bank_price_product_id"] = product.id

    price_col, button_col = st.columns([1, 1])
    with price_col:
        render_selected_market_price(product.id)
    if button_col.button("Use market price", width="stretch"):
        st.session_state["bank_agreed_price"] = get_market_price(product.id)
        st.rerun()

    side = st.radio("Side", ["Buy", "Sell"], horizontal=True, key="bank_declaration_side")
    st.number_input(
        "Agreed price",
        min_value=0.0,
        step=0.5,
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
                product_id=product.id,
                side=side,
                price=submitted_price,
            )
        if trade is None:
            if order.status == "Refused":
                st.error(f"Order #{order.id} was refused because the company declaration did not match.")
            else:
                st.info(f"Order #{order.id} is pending until {counterparty.username} enters the compatible side.")
        else:
            st.success(f"Order #{order.id} matched and trade #{trade.id} was recorded.")
        st.rerun()

with right:
    render_bank_live_panel(user.id)
