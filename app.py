import streamlit as st
from sqlalchemy import select

from db import get_session
from models import User
from seed import seed_demo_data
from ui import inject_app_styles


st.set_page_config(page_title="Trading Game", page_icon="chart_with_upwards_trend", layout="wide")

seed_demo_data()
inject_app_styles()

st.title("Options Trading Game")
st.markdown(
    '<div class="role-strip">Choose a demo seat and go directly to the right trading desk.</div>',
    unsafe_allow_html=True,
)

with get_session() as session:
    users = session.scalars(select(User).order_by(User.role, User.username)).all()

current_user_id = st.session_state.get("user_id")
current_user = next((user for user in users if user.id == current_user_id), None)

ROLE_PAGES = {
    "Company": "pages/company.py",
    "Bank": "pages/bank.py",
    "Professor": "pages/professor.py",
}

if current_user is not None:
    left, right = st.columns([2, 1])
    left.success(f"Signed in as {current_user.username} ({current_user.role})")
    if right.button("Open my dashboard", type="primary", width="stretch"):
        st.switch_page(ROLE_PAGES[current_user.role])
    if right.button("Switch user", width="stretch"):
        st.session_state.clear()
        st.rerun()
else:
    st.subheader("Enter The Simulation")
    users_by_role = {
        role: [user for user in users if user.role == role]
        for role in ["Company", "Bank", "Professor"]
    }
    role_columns = st.columns(3)
    for column, role in zip(role_columns, ["Company", "Bank", "Professor"]):
        with column:
            st.markdown(f"### {role}")
            for user in users_by_role[role]:
                if st.button(user.username, key=f"login_{user.id}", type="primary", width="stretch"):
                    st.session_state["user_id"] = user.id
                    st.session_state["role"] = user.role
                    st.switch_page(ROLE_PAGES[user.role])
