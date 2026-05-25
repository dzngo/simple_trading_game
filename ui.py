import streamlit as st

from db import get_session
from models import User

AUTO_REFRESH_SECONDS = 1
AUTO_REFRESH_INTERVAL = f"{AUTO_REFRESH_SECONDS}s"


def require_login(allowed_roles: set[str] | None = None) -> User:
    user_id = st.session_state.get("user_id")
    if user_id is None:
        st.warning("Select a user on the login page to continue.")
        st.page_link("app.py", label="Go to login")
        st.stop()

    with get_session() as session:
        user = session.get(User, user_id)
        if user is None:
            st.session_state.clear()
            st.warning("Your session user no longer exists. Please log in again.")
            st.page_link("app.py", label="Go to login")
            st.stop()

        if allowed_roles is not None and user.role not in allowed_roles:
            st.error(f"This page is for {', '.join(sorted(allowed_roles))} users.")
            st.stop()

        return user


def show_user_sidebar(user: User) -> None:
    action_col, user_col = st.columns([1, 5])
    if action_col.button("Switch user", key=f"switch_user_{user.id}", width="stretch"):
        st.session_state.clear()
        st.switch_page("app.py")
    user_col.caption(f"Signed in as {user.username} ({user.role})")


def show_table(df, empty_message: str) -> None:
    if df.empty:
        st.info(empty_message)
        return
    st.dataframe(df, hide_index=True, width="stretch")


def auto_refresh_caption() -> None:
    st.caption(f"Live sections refresh every {AUTO_REFRESH_SECONDS} seconds.")


def inject_app_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: #f6f7f9;
        }
        [data-testid="stHeader"] {
            background: rgba(246, 247, 249, 0.88);
        }
        [data-testid="stSidebar"] {
            display: none;
        }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e2e5e9;
            border-radius: 8px;
            padding: 0.85rem 1rem;
        }
        .status-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin: 0.25rem 0 1rem;
        }
        .status-chip {
            border-radius: 999px;
            color: #ffffff;
            font-size: 0.78rem;
            font-weight: 700;
            padding: 0.25rem 0.65rem;
        }
        .status-pending { background: #b7791f; }
        .status-matched { background: #2f855a; }
        .status-refused { background: #c53030; }
        .role-strip {
            border-left: 4px solid #2f5d8c;
            padding: 0.35rem 0 0.35rem 0.85rem;
            margin-bottom: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_chips(counts: dict[str, int]) -> None:
    chips = []
    for status, class_name in [
        ("Pending", "status-pending"),
        ("Matched", "status-matched"),
        ("Refused", "status-refused"),
    ]:
        chips.append(f'<span class="status-chip {class_name}">{status}: {counts.get(status, 0)}</span>')
    st.markdown(f'<div class="status-row">{"".join(chips)}</div>', unsafe_allow_html=True)


def infer_refusal_reasons(df):
    if df.empty or "Status" not in df.columns:
        return df

    refused = df[df["Status"] == "Refused"].copy()
    if refused.empty:
        df["Refusal Reason"] = ""
        return df

    reasons_by_id = {}
    grouped = refused.groupby(["Submitted By", "Counterparty", "Product"], dropna=False)
    reverse_lookup = {(row["Counterparty"], row["Submitted By"], row["Product"]): row for _, row in refused.iterrows()}

    for _, group in grouped:
        for _, row in group.iterrows():
            peer = reverse_lookup.get((row["Submitted By"], row["Counterparty"], row["Product"]))
            reason = "Counterparty mismatch"
            if peer is not None:
                price_mismatch = row["Price"] != peer["Price"]
                side_mismatch = row["Side"] == peer["Side"]
                if price_mismatch and side_mismatch:
                    reason = "Price and side mismatch"
                elif price_mismatch:
                    reason = "Price mismatch"
                elif side_mismatch:
                    reason = "Side mismatch"
            reasons_by_id[row["ID"]] = reason

    output = df.copy()
    output["Refusal Reason"] = output["ID"].map(reasons_by_id).fillna("")
    return output
