import streamlit as st

from analytics import orders_df, products, trades_df, users_by_role
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


st.set_page_config(page_title="Company", page_icon="office", layout="wide")

user = require_login({"Company"})
show_user_sidebar(user)
inject_app_styles()


@st.fragment(run_every=AUTO_REFRESH_INTERVAL)
def render_company_live_panel(user_id: int) -> None:
    with get_session() as session:
        product_options = products(session)
        bank_options = users_by_role(session, "Bank")
        pending = orders_df(session, user_id=user_id, status="Pending")
        matched = orders_df(session, user_id=user_id, status="Matched")
        refused = infer_refusal_reasons(orders_df(session, user_id=user_id, status="Refused"))
        orders = infer_refusal_reasons(orders_df(session, user_id=user_id))
        trades = trades_df(session, user_id=user_id)

    auto_refresh_caption()
    status_chips({"Pending": len(pending), "Matched": len(matched), "Refused": len(refused)})

    metric_cols = st.columns(3)
    metric_cols[0].metric("Products", len(product_options))
    metric_cols[1].metric("Available Banks", len(bank_options))
    metric_cols[2].metric("Matched Trades", len(trades))

    right = st.container()
    with right:
        st.subheader("Attention Queue")
        attention_tabs = st.tabs(["Pending", "Refused"])
        with attention_tabs[0]:
            show_table(pending, "No pending declarations.")
        with attention_tabs[1]:
            show_table(refused, "No refused declarations.")

    st.divider()
    tab_trades, tab_history = st.tabs(["Matched Trades", "Declaration History"])
    with tab_trades:
        show_table(trades, "No matched trades yet.")
    with tab_history:
        show_table(orders, "No trade declarations yet.")

st.title("Company Desk")
st.markdown(
    '<div class="role-strip">Submit negotiated trade declarations with banks and watch whether the bank confirms or refuses the same terms.</div>',
    unsafe_allow_html=True,
)

with get_session() as session:
    product_options = products(session)
    bank_options = users_by_role(session, "Bank")

left, right = st.columns([1, 1.35], gap="large")

with left:
    st.subheader("New Trade Declaration")
    st.caption("A trade is recorded only when the bank submits the opposite side at the same price.")

    with st.form("company_trade_declaration"):
        product = st.selectbox("Product", product_options, format_func=lambda item: item.name)
        side = st.radio("Side", ["Buy", "Sell"], horizontal=True)
        price = st.number_input("Agreed price", min_value=0.0, value=10.0, step=0.5)
        counterparty = st.selectbox("Bank counterparty", bank_options, format_func=lambda item: item.username)
        submitted = st.form_submit_button("Submit declaration", type="primary")

    st.subheader("Trading Directory")
    st.write("Products: " + ", ".join(product.name for product in product_options))
    st.write("Banks: " + ", ".join(bank.username for bank in bank_options))

with right:
    render_company_live_panel(user.id)

if submitted:
    with get_session() as session:
        order, trade = create_trade_declaration(
            session=session,
            user_id=user.id,
            counterparty_id=counterparty.id,
            product_id=product.id,
            side=side,
            price=price,
        )
    if trade is None:
        if order.status == "Refused":
            st.error(f"Order #{order.id} was refused because the bank declaration did not match.")
        else:
            st.info(f"Order #{order.id} is pending until {counterparty.username} enters the compatible side.")
    else:
        st.success(f"Order #{order.id} matched and trade #{trade.id} was recorded.")
    st.rerun()
