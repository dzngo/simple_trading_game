import streamlit as st

from analytics import active_options, option_label, options_df, orders_df, trades_df, users_by_role
from db import get_session
from matching import create_trade_declaration
from ui import (
    AUTO_REFRESH_INTERVAL,
    auto_refresh_caption,
    infer_refusal_reasons,
    inject_app_styles,
    matched_trades_df,
    pending_trades_df,
    refused_transactions_df,
    render_trade_status_panel,
    require_login,
    show_table,
    show_user_sidebar,
)


st.set_page_config(page_title="Company", page_icon="office", layout="wide")

inject_app_styles()
user = require_login({"Company"})


@st.fragment(run_every=AUTO_REFRESH_INTERVAL)
def render_company_live_panel(user_id: int) -> None:
    with get_session() as session:
        option_options = active_options(session)
        bank_options = users_by_role(session, "Bank")
        visible_options = options_df(session, include_market=False)
        orders = orders_df(session, user_id=user_id)
        orders_with_reasons = infer_refusal_reasons(orders)
        pending = pending_trades_df(orders_with_reasons)
        refused = refused_transactions_df(orders_with_reasons)
        trades = trades_df(session, user_id=user_id, source="Client-Bank")
        matched = matched_trades_df(trades, user.username)

    auto_refresh_caption()
    render_trade_status_panel(orders, user_id)

    st.caption(f"{len(option_options)} active options | {len(bank_options)} available banks")

    st.subheader("Available options")
    show_table(visible_options, "No active options configured.", hide_id=False)

    st.subheader("Pending trades")
    show_table(pending, "No pending trades.")

    st.subheader("Matched trades")
    show_table(matched, "No matched trades yet.")

    with st.expander("Refused transactions"):
        show_table(refused, "No refused transactions.")


st.title("Company desk")
st.markdown(
    '<div class="role-strip">Submit negotiated trade declarations with banks and watch whether the bank confirms or refuses the same terms.</div>',
    unsafe_allow_html=True,
)
show_user_sidebar(user)

with get_session() as session:
    option_options = active_options(session)
    bank_options = users_by_role(session, "Bank")

left, right = st.columns([1, 1.35], gap="large")

with left:
    st.subheader("New trade declaration")

    if not option_options or not bank_options:
        st.info("The professor must configure active options and banks before declarations can be submitted.")
        submitted = False
    else:
        with st.form("company_trade_declaration"):
            option = st.selectbox("Option", option_options, format_func=option_label)
            side = st.segmented_control("Side", ["Buy", "Sell"], default="Buy")
            price = st.number_input(
                "Agreed price",
                min_value=0.1,
                value=10.0,
                step=0.1,
                format="%.1f",
            )
            counterparty = st.selectbox("Bank counterparty", bank_options, format_func=lambda item: item.username)
            submitted = st.form_submit_button("Submit declaration", type="primary")

with right:
    render_company_live_panel(user.id)

if submitted:
    with get_session() as session:
        order, trade = create_trade_declaration(
            session=session,
            user_id=user.id,
            counterparty_id=counterparty.id,
            option_id=option.id,
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
