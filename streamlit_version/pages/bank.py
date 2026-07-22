import streamlit as st

from analytics import (
    active_options,
    market_price_for_option,
    option_label,
    users_by_role,
)
from db import get_session
from matching import create_market_trade, create_trade_declaration
from snapshots import bank_live_snapshot
from state import current_session_version
from ui import (
    AUTO_REFRESH_INTERVAL,
    auto_refresh_caption,
    inject_app_styles,
    render_trade_status_panel,
    require_login,
    show_table,
    show_user_sidebar,
)

st.set_page_config(page_title="Bank", page_icon="bank", layout="wide")

inject_app_styles()
user = require_login({"Bank"}, allowed_statuses={"live"})
GAME_SESSION_ID = int(st.session_state["game_session_id"])


def get_market_prices(option_id: int) -> tuple[float, float]:
    with get_session() as session:
        return market_price_for_option(session, option_id, GAME_SESSION_ID)


def format_market_trade_confirmation(trade_id: int, option_text: str, side: str, price: float, created_at) -> str:
    direction = "from Market" if side == "Buy" else "to Market"
    executed_at = created_at.strftime("%H:%M:%S")
    return f"Trade #{trade_id}: {side} {option_text} {direction} at € {price:.1f} at {executed_at}."


@st.fragment(run_every=AUTO_REFRESH_INTERVAL)
def render_bank_live_panel(user_id: int) -> None:
    snapshot = bank_live_snapshot(GAME_SESSION_ID, user_id, user.username, current_session_version(GAME_SESSION_ID))

    auto_refresh_caption()
    render_trade_status_panel(snapshot["orders"], user_id)

    st.caption(f"{snapshot['option_count']} active options | {snapshot['company_count']} companies")

    st.subheader("Market prices")
    show_table(snapshot["market_prices"], "No market prices configured.")

    st.subheader("Pending trades")
    show_table(snapshot["pending"], "No pending trades.")

    st.subheader("Matched trades")
    show_table(snapshot["matched"], "No matched trades yet.")

    with st.expander("Market trades history"):
        show_table(snapshot["market_history"], "No market trades yet.")

    with st.expander("Rejected declarations"):
        show_table(snapshot["rejected"], "No rejected declarations.")


@st.fragment
def render_bank_declaration_panel(user_id: int) -> None:
    with st.container(border=True):
        st.subheader("Client trade declaration")

        with get_session() as session:
            option_options = active_options(session, GAME_SESSION_ID)
            company_options = users_by_role(session, "Company", GAME_SESSION_ID)

        if not option_options or not company_options:
            st.info("The professor must configure active options and companies before declarations can be submitted.")
        else:
            option = st.selectbox("Option", option_options, format_func=option_label, key="bank_client_option")
            side = st.segmented_control("Side", ["Buy", "Sell"], default="Buy", key="bank_declaration_side")
            st.number_input(
                "Agreed price",
                min_value=0.1,
                value=10.0,
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
                with st.spinner("Submitting declaration..."):
                    with get_session() as session:
                        create_trade_declaration(
                            session=session,
                            game_session_id=GAME_SESSION_ID,
                            user_id=user_id,
                            counterparty_id=counterparty.id,
                            option_id=option.id,
                            side=side,
                            price=submitted_price,
                        )
                st.rerun(scope="fragment")


@st.fragment
def render_bank_market_trade_panel(user_id: int) -> None:
    with st.container(border=True):
        st.subheader("Market trade")
        st.caption("Market trades execute immediately at the current professor-set bid/ask.")
        market_confirmation = st.session_state.pop("market_trade_confirmation", None)
        if market_confirmation is not None:
            st.success(market_confirmation, icon=":material/check_circle:")

        with get_session() as session:
            option_options = active_options(session, GAME_SESSION_ID)

        if not option_options:
            st.info("No active options configured.")
        else:
            market_option = st.selectbox("Market option", option_options, format_func=option_label, key="market_option")
            market_side = st.segmented_control("Market side", ["Buy", "Sell"], default="Buy", key="market_side")
            market_bid, market_ask = get_market_prices(market_option.id)
            execution_price = market_ask if market_side == "Buy" else market_bid
            st.metric("Execution Price", f"{execution_price:.1f}")
            if st.button("Execute market trade", type="primary", width="stretch"):
                with st.spinner("Executing market trade..."):
                    with get_session() as session:
                        trade = create_market_trade(
                            session=session,
                            game_session_id=GAME_SESSION_ID,
                            bank_id=user_id,
                            option_id=market_option.id,
                            side=market_side,
                        )
                        st.session_state["market_trade_confirmation"] = format_market_trade_confirmation(
                            trade.id,
                            option_label(trade.option),
                            market_side,
                            trade.price,
                            trade.created_at,
                        )
                st.rerun(scope="fragment")


st.title("Bank desk")
st.markdown(
    '<div class="role-strip">Confirm verbal trades with companies, or trade directly with the professor-set market.</div>',
    unsafe_allow_html=True,
)
show_user_sidebar(user)

left, right = st.columns([1, 1.35], gap="large")

with left:
    render_bank_declaration_panel(user.id)
    render_bank_market_trade_panel(user.id)

with right:
    render_bank_live_panel(user.id)
