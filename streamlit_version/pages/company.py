import streamlit as st

from analytics import active_options, option_label, users_by_role
from db import get_session
from matching import create_trade_declaration
from snapshots import company_live_snapshot
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

st.set_page_config(page_title="Company", page_icon="office", layout="wide")

inject_app_styles()
user = require_login({"Company"}, allowed_statuses={"live"})
GAME_SESSION_ID = int(st.session_state["game_session_id"])


@st.fragment(run_every=AUTO_REFRESH_INTERVAL)
def render_company_live_panel(user_id: int) -> None:
    snapshot = company_live_snapshot(GAME_SESSION_ID, user_id, user.username, current_session_version(GAME_SESSION_ID))

    auto_refresh_caption()
    render_trade_status_panel(snapshot["orders"], user_id)

    st.caption(f"{snapshot['option_count']} active options | {snapshot['bank_count']} available banks")

    st.subheader("Available options")
    show_table(snapshot["visible_options"], "No active options configured.", hide_id=False)

    st.subheader("Pending trades")
    show_table(snapshot["pending"], "No pending trades.")

    st.subheader("Matched trades")
    show_table(snapshot["matched"], "No matched trades yet.")

    with st.expander("Rejected declarations"):
        show_table(snapshot["rejected"], "No rejected declarations.")


@st.fragment
def render_company_declaration_panel(user_id: int) -> None:
    with get_session() as session:
        option_options = active_options(session, GAME_SESSION_ID)
        bank_options = users_by_role(session, "Bank", GAME_SESSION_ID)

    st.subheader("New trade declaration")

    submitted = False
    option = None
    side = None
    price = None
    counterparty = None

    if not option_options or not bank_options:
        st.info("The professor must configure active options and banks before declarations can be submitted.")
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

    if submitted and option is not None and side is not None and price is not None and counterparty is not None:
        with st.spinner("Submitting declaration..."):
            with get_session() as session:
                create_trade_declaration(
                    session=session,
                    game_session_id=GAME_SESSION_ID,
                    user_id=user_id,
                counterparty_id=counterparty.id,
                option_id=option.id,
                side=side,
                price=price,
            )
        st.rerun(scope="fragment")


st.title("Company desk")
st.markdown(
    '<div class="role-strip">Submit negotiated trade declarations with banks and watch whether the bank confirms or rejects the same terms.</div>',
    unsafe_allow_html=True,
)
show_user_sidebar(user)

left, right = st.columns([1, 1.35], gap="large")

with left:
    render_company_declaration_panel(user.id)

with right:
    render_company_live_panel(user.id)
