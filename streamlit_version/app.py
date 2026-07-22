import os

# pylint: disable=not-callable

import streamlit as st
from sqlalchemy import select

from db import get_session, init_db
from models import GameSession, ParticipantEmail, User
from session_services import (
    create_game_session,
    live_sessions_for_email,
    normalize_email,
    participants_for_session,
    valid_email,
)
from state import bump_session_version
from ui import inject_app_styles

st.set_page_config(page_title="Trading Game", page_icon="💰", layout="wide")


@st.cache_resource(show_spinner=False)
def ensure_database_initialized() -> bool:
    init_db()
    return True


with st.spinner("Game loading..."):
    ensure_database_initialized()
inject_app_styles()

ROLE_PAGES = {
    "Company": "pages/company.py",
    "Bank": "pages/bank.py",
    "Professor": "pages/session_manager.py",
}


def professor_password() -> str | None:
    try:
        value = st.secrets.get("PROFESSOR_PASSWORD")
    except Exception:
        value = None
    return value or os.getenv("PROFESSOR_PASSWORD")


def configured_professor_emails() -> set[str]:
    try:
        raw_value = st.secrets.get("PROFESSOR_EMAILS")
    except Exception:
        raw_value = None

    raw_value = raw_value or os.getenv("PROFESSOR_EMAILS")
    if raw_value is None:
        return set()
    if isinstance(raw_value, str):
        values = raw_value.replace(";", ",").replace("\n", ",").split(",")
    else:
        values = list(raw_value)
    return {normalize_email(str(value)) for value in values if str(value).strip()}


def professor_for_bootstrap_email(session, email: str) -> User:
    game_session = session.scalar(select(GameSession).order_by(GameSession.created_at.desc()))
    if game_session is None:
        game_session = create_game_session(session, "First Session")

    professors = participants_for_session(session, game_session.id, "Professor")
    professor = (
        professors[0]
        if professors
        else User(
            game_session_id=game_session.id,
            username="Professor",
            role="Professor",
        )
    )
    if not professors:
        session.add(professor)
        session.flush()

    existing_emails = {participant_email.email for participant_email in professor.emails}
    if email not in existing_emails:
        professor.emails.append(ParticipantEmail(email=email))
        session.flush()
        bump_session_version(session, game_session.id)
    return professor


def sign_in(participant: User, professor_authenticated: bool = False, login_email: str | None = None) -> None:
    st.session_state["user_id"] = participant.id
    st.session_state["role"] = participant.role
    st.session_state["game_session_id"] = participant.game_session_id
    if login_email:
        st.session_state["login_email"] = login_email
    if professor_authenticated:
        st.session_state["professor_authenticated"] = True
    st.switch_page(ROLE_PAGES[participant.role])


def set_access_path(path: str) -> None:
    st.session_state["access_path"] = path


def render_student_login() -> None:
    st.subheader("Student access", anchor=False)
    email = st.text_input("Authorized email", key="student_email").strip()
    if st.button("Enter game", type="primary", width="stretch"):
        normalized = normalize_email(email)
        if not valid_email(normalized):
            st.error("Enter a valid authorized email.")
            return
        target_participant = None
        with st.spinner("Finding your session..."):
            with get_session() as session:
                matches = live_sessions_for_email(session, normalized)
                if not matches:
                    st.error("No live session is available for this email.")
                    return
                if len(matches) == 1:
                    _, target_participant = matches[0]
                else:
                    st.session_state["student_login_matches"] = [participant.id for _, participant in matches]
                    st.session_state["student_login_email"] = normalized
                    st.rerun()
        if target_participant is not None:
            sign_in(target_participant, login_email=normalized)


def render_student_session_choice() -> None:
    participant_ids = st.session_state.get("student_login_matches", [])
    if not participant_ids:
        return

    with get_session() as session:
        participants = [session.get(User, participant_id) for participant_id in participant_ids]
        participants = [participant for participant in participants if participant is not None]
        labels = {
            participant.id: f"{participant.game_session.name} - {participant.username}" for participant in participants
        }

    if not participants:
        st.session_state.pop("student_login_matches", None)
        return

    st.subheader("Choose session", anchor=False)
    selected = st.radio(
        "Your email is authorized in more than one live session.",
        participants,
        format_func=lambda item: labels[item.id],
    )
    if st.button("Continue", type="primary", width="stretch"):
        with st.spinner("Opening session..."):
            sign_in(selected, login_email=st.session_state.get("student_login_email"))


def render_professor_login() -> None:
    st.subheader("Professor access", anchor=False)
    configured_password = professor_password()
    email = st.text_input("Professor email", key="professor_email").strip()
    password = st.text_input("Professor password", type="password", key="professor_password")

    if configured_password is None:
        st.error("PROFESSOR_PASSWORD is not configured in Streamlit secrets.")
        return

    if st.button("Open professor tools", type="primary", width="stretch"):
        normalized = normalize_email(email)
        if not valid_email(normalized):
            st.error("Enter a valid professor email.")
            return
        if password != configured_password:
            st.error("Professor password is incorrect.")
            return
        if normalized not in configured_professor_emails():
            st.error("This email is not authorized as a professor.")
            return

        target_professor = None
        with st.spinner("Opening professor tools..."):
            with get_session() as session:
                target_professor = professor_for_bootstrap_email(session, normalized)

        if target_professor is not None:
            sign_in(target_professor, professor_authenticated=True, login_email=normalized)


def render_access_choice() -> str | None:
    st.markdown('<div class="login-panel-title">How are you joining?</div>', unsafe_allow_html=True)
    student_col, professor_col = st.columns(2, gap="small")
    selected_path = st.session_state.get("access_path")
    with student_col:
        st.button(
            "Student",
            icon=":material/school:",
            type="primary" if selected_path == "Student" else "secondary",
            width="stretch",
            on_click=set_access_path,
            args=("Student",),
        )
    with professor_col:
        st.button(
            "Professor",
            icon=":material/admin_panel_settings:",
            type="primary" if selected_path == "Professor" else "secondary",
            width="stretch",
            on_click=set_access_path,
            args=("Professor",),
        )
    return st.session_state.get("access_path")


if st.session_state.get("user_id"):
    st.title("Trading Game")
    role = st.session_state.get("role")
    st.success(f"Signed in as {role}.")
    col1, col2 = st.columns(2)
    if col1.button("Continue", type="primary", width="stretch"):
        st.switch_page(ROLE_PAGES[role])
    if col2.button("Switch user", width="stretch"):
        st.session_state.clear()
        st.rerun()
else:
    left_margin, login_col, right_margin = st.columns([1, 1.1, 1])
    with login_col:
        with st.container(border=True):
            st.title("Trading Game", text_alignment="center")
            st.caption("Choose your access type to continue.", unsafe_allow_html=False)
            access_path = render_access_choice()
            st.markdown('<div class="login-divider"></div>', unsafe_allow_html=True)
            if access_path == "Student" or st.session_state.get("student_login_matches"):
                render_student_session_choice()
                render_student_login()
            elif access_path == "Professor":
                render_professor_login()
            else:
                st.markdown('<div class="login-empty-state">Select Student or Professor.</div>', unsafe_allow_html=True)
