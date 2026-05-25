import plotly.express as px
import streamlit as st
from sqlalchemy import select

from analytics import (
    cumulative_pnl_history_df,
    market_prices_df,
    orders_df,
    pnl_df,
    trades_df,
)
from db import get_session
from models import MarketPrice
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


@st.fragment(run_every=AUTO_REFRESH_INTERVAL)
def render_professor_live_panel() -> None:
    with get_session() as session:
        all_orders = infer_refusal_reasons(orders_df(session))
        pending_orders = orders_df(session, status="Pending")
        refused_orders = infer_refusal_reasons(orders_df(session, status="Refused"))
        all_trades = trades_df(session)
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

    metric_cols = st.columns(4)
    metric_cols[0].metric("Orders", len(all_orders))
    metric_cols[1].metric("Pending", len(pending_orders))
    metric_cols[2].metric("Refused", len(refused_orders))
    metric_cols[3].metric("Trades", len(all_trades))

    refused_tab, trades_tab, all_tab = st.tabs(["Refused", "Matched Trades", "All Declarations"])
    with refused_tab:
        show_table(refused_orders, "No refused declarations.")
    with trades_tab:
        show_table(all_trades, "No trades matched yet.")
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


@st.fragment(run_every=AUTO_REFRESH_INTERVAL)
def render_market_snapshot() -> None:
    with get_session() as session:
        market_snapshot = market_prices_df(session)

    st.subheader("Current Market Snapshot")
    show_table(market_snapshot, "No market prices configured.")


st.title("Professor Control Room")
st.markdown(
    '<div class="role-strip">Control Market Prices, monitor failed negotiations, and keep the live trading session moving.</div>',
    unsafe_allow_html=True,
)
show_user_sidebar(user)

with st.expander("Reset game state"):
    st.warning("This clears all orders and trades and restores demo users, products, and market prices.")
    if st.button("Reset game", type="primary"):
        seed_demo_data(reset=True)
        st.success("Game state reset.")
        st.rerun()

st.divider()
st.subheader("Market Prices")

with get_session() as session:
    prices = [
        {
            "id": price.id,
            "product_name": price.product.name,
            "market_price": price.market_price,
        }
        for price in session.scalars(select(MarketPrice).join(MarketPrice.product).order_by(MarketPrice.id)).all()
    ]

price_columns = st.columns(len(prices)) if prices else []
for column, price in zip(price_columns, prices):
    with column:
        with st.form(f"market_price_{price['id']}"):
            st.markdown(f"**{price['product_name']}**")
            market_price = st.number_input(
                "Market Price",
                min_value=0.0,
                value=float(price["market_price"]),
                step=0.5,
                key=f"market_price_{price['id']}",
            )
            saved = st.form_submit_button("Save")
        if saved:
            with get_session() as session:
                editable_price = session.get(MarketPrice, price["id"])
                editable_price.market_price = market_price
            st.success(f"{price['product_name']} Market Price updated.")
            st.rerun()

render_market_snapshot()

st.divider()
render_professor_live_panel()
