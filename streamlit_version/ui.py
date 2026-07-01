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
        st.caption(empty_message)
        return

    column_config = {
        "ID": None,
        "Source": None,
        "Price": st.column_config.NumberColumn("Price", format="€ %.1f"),
        "Bid": st.column_config.NumberColumn("Bid", format="€ %.1f"),
        "Ask": st.column_config.NumberColumn("Ask", format="€ %.1f"),
        "Draft Bid": st.column_config.NumberColumn("Draft bid", format="€ %.1f"),
        "Draft Ask": st.column_config.NumberColumn("Draft ask", format="€ %.1f"),
        "Strike": st.column_config.NumberColumn("Strike", format="%d"),
        "Created": st.column_config.DatetimeColumn("Created", format="HH:mm:ss"),
        "Updated": st.column_config.DatetimeColumn("Updated", format="HH:mm:ss"),
    }
    st.dataframe(df, hide_index=True, width="stretch", column_config=column_config)


def auto_refresh_caption() -> None:
    return None


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
            margin: 0.25rem 0 0.65rem;
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


def render_trade_status_panel(orders, user_id: int) -> None:
    """Surface declaration status changes without duplicating the full history table."""
    if orders.empty:
        st.caption("No trade declarations submitted yet.")
        return

    current_statuses = {int(row["ID"]): row["Status"] for _, row in orders.iterrows()}
    state_key = f"known_trade_statuses_{user_id}"
    previous_statuses = st.session_state.get(state_key)
    if previous_statuses is None:
        st.session_state[state_key] = current_statuses
    else:
        resolved_statuses = {"Matched", "Refused"}
        for order_id, status in current_statuses.items():
            if status in resolved_statuses and previous_statuses.get(order_id) != status:
                matching_row = orders.loc[orders["ID"] == order_id].iloc[0]
                if status == "Matched":
                    st.toast(f"Trade confirmed: {matching_row['Option']} with {matching_row['Counterparty']}.")
                else:
                    st.toast(
                        f"Trade refused: {matching_row['Option']} with {matching_row['Counterparty']}."
                    )
        st.session_state[state_key] = current_statuses

    resolved = orders[orders["Status"].isin(["Matched", "Refused"])]
    if not resolved.empty:
        latest = resolved.sort_values("Created", ascending=False).iloc[0]
        detail = f"{latest['Option']} with {latest['Counterparty']} at {latest['Price']:.1f}."
        if latest["Status"] == "Matched":
            st.success(f"Trade confirmed: {detail}")
        else:
            st.error(
                "Trade terms did not match. Renegotiate verbally and submit new declarations. " + detail
            )

    pending = orders[orders["Status"] == "Pending"]
    if not pending.empty:
        latest_pending = pending.sort_values("Created", ascending=False).iloc[0]
        st.info(
            f"Awaiting response from {latest_pending['Counterparty']}: "
            f"{latest_pending['Option']} at {latest_pending['Price']:.1f}."
        )

    counts = orders["Status"].value_counts().to_dict()
    status_chips(counts)


def attention_queue_df(orders):
    if orders.empty or "Status" not in orders.columns:
        return orders

    actionable = orders[orders["Status"].isin(["Pending", "Refused"])].copy()
    if actionable.empty:
        return actionable

    columns = ["Status", "Option", "Side", "Price", "Counterparty", "Created"]
    if "Refusal Reason" in actionable.columns:
        columns.insert(1, "Refusal Reason")
    return actionable[columns]


def infer_refusal_reasons(df):
    if df.empty or "Status" not in df.columns:
        return df

    refused = df[df["Status"] == "Refused"].copy()
    if refused.empty:
        df["Refusal Reason"] = ""
        return df

    reasons_by_id = {}
    instrument_column = "Option" if "Option" in refused.columns else "Product"
    grouped = refused.groupby(["Submitted By", "Counterparty", instrument_column], dropna=False)
    reverse_lookup = {
        (row["Counterparty"], row["Submitted By"], row[instrument_column]): row
        for _, row in refused.iterrows()
    }

    for _, group in grouped:
        for _, row in group.iterrows():
            peer = reverse_lookup.get((row["Submitted By"], row["Counterparty"], row[instrument_column]))
            reason = "Terms did not match"
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
