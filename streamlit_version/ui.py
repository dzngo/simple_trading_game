import streamlit as st

from db import get_session
from models import GameSession, User
from session_services import status_label

AUTO_REFRESH_SECONDS = 3
AUTO_REFRESH_INTERVAL = f"{AUTO_REFRESH_SECONDS}s"

STATUS_DISPLAY_LABELS = {
    "Pending": "Pending",
    "Matched": "Matched",
    "Rejected": "Rejected",
}

SOURCE_DISPLAY_LABELS = {
    "Client-Bank": "Company-Bank",
    "Market": "Market",
}


def require_login(
    allowed_roles: set[str] | None = None,
    allowed_statuses: set[str] | None = None,
) -> User:
    user_id = st.session_state.get("user_id")
    game_session_id = st.session_state.get("game_session_id")
    if user_id is None:
        st.warning("Enter with your authorized email to continue.")
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

        if game_session_id is not None and user.game_session_id != game_session_id:
            st.session_state.clear()
            st.warning("Your selected session changed. Please log in again.")
            st.page_link("app.py", label="Go to login")
            st.stop()

        game_session = session.get(GameSession, user.game_session_id)
        if game_session is None:
            st.session_state.clear()
            st.warning("This session no longer exists. Please log in again.")
            st.page_link("app.py", label="Go to login")
            st.stop()

        if allowed_statuses is not None and game_session.status not in allowed_statuses:
            st.warning(f"{game_session.name} is {status_label(game_session.status)}.")
            st.page_link("app.py", label="Go to login")
            st.stop()

        return user


def show_user_sidebar(user: User) -> None:
    action_col, user_col = st.columns([1, 5])
    if action_col.button("Switch user", key=f"switch_user_{user.id}", width="stretch"):
        st.session_state.clear()
        st.switch_page("app.py")
    login_email = st.session_state.get("login_email")
    identity = login_email or user.username
    user_col.caption(f"Logged in as {identity} · {user.username} ({user.role})")


def show_table(df, empty_message: str, hide_id: bool = True) -> None:
    if df.empty:
        st.caption(empty_message)
        return

    display_df = df.copy()
    if "Status" in display_df.columns:
        display_df["Status"] = display_df["Status"].replace(STATUS_DISPLAY_LABELS)
    if "Source" in display_df.columns:
        display_df["Source"] = display_df["Source"].replace(SOURCE_DISPLAY_LABELS)
    if "Refusal Reason" in display_df.columns and "Issue" not in display_df.columns:
        display_df = display_df.rename(columns={"Refusal Reason": "Issue"})

    column_config = {
        "ID": None if hide_id else st.column_config.NumberColumn("ID", format="%d"),
        "Paired Order ID": None,
        "Source": None,
        "Price": st.column_config.NumberColumn("Price", format="€ %.1f"),
        "Bid": st.column_config.NumberColumn("Bid", format="€ %.1f"),
        "Ask": st.column_config.NumberColumn("Ask", format="€ %.1f"),
        "Draft Bid": st.column_config.NumberColumn("Draft bid", format="€ %.1f"),
        "Draft Ask": st.column_config.NumberColumn("Draft ask", format="€ %.1f"),
        "Strike": st.column_config.NumberColumn("Strike", format="%d"),
        "Created": st.column_config.DatetimeColumn("Created", format="HH:mm:ss"),
        "Submitted at": st.column_config.DatetimeColumn("Submitted at", format="HH:mm:ss"),
        "Updated": st.column_config.DatetimeColumn("Updated", format="HH:mm:ss"),
    }
    st.dataframe(display_df, hide_index=True, width="stretch", column_config=column_config)


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
            display: none;
            height: 0;
        }
        [data-testid="stSidebar"] {
            display: none;
        }
        [data-testid="stSidebarNav"] {
            display: none;
        }
        [data-testid="stToolbar"] {
            display: none;
        }
        #MainMenu {
            visibility: hidden;
        }
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 3rem;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.login-panel-title) {
            background: #ffffff;
            border: 1px solid #e0e5ec;
            border-radius: 8px;
            box-shadow: 0 12px 32px rgba(31, 41, 55, 0.08);
            padding: 1.4rem 1.45rem 1.55rem;
        }
        .login-panel-title {
            color: #2f3442;
            font-size: 1.2rem;
            font-weight: 700;
            line-height: 1.25;
            margin: 0.7rem 0 0.65rem;
            text-align: center;
        }
        .login-divider {
            border-top: 1px solid #e8ebf0;
            margin: 1rem 0 0.9rem;
        }
        .login-empty-state {
            color: #6b7280;
            font-size: 0.95rem;
            padding: 0.45rem 0 0.2rem;
            text-align: center;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.login-panel-title) h1 {
            font-size: 2.15rem;
            letter-spacing: 0;
            margin-bottom: 0.25rem;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.login-panel-title) h3 {
            font-size: 1.05rem;
            margin-top: 0.1rem;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.login-panel-title) button {
            min-height: 3rem;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] h3 {
            font-size: 1.2rem;
            line-height: 1.25;
            margin-bottom: 0.45rem;
        }
        div[data-testid="stAlert"] {
            padding: 0.45rem 0.65rem;
            margin-bottom: 0.35rem;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e2e5e9;
            border-radius: 8px;
            padding: 0.55rem 0.7rem;
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
        .status-rejected { background: #c53030; }
        .session-header-name {
            color: #2f3442;
            font-size: 1.45rem;
            font-weight: 750;
            line-height: 1.2;
            margin: 0.2rem 0 0.15rem;
        }
        .session-status-inline {
            align-items: center;
            display: flex;
            gap: 0.5rem;
            justify-content: flex-start;
            margin-top: 0.25rem;
            white-space: nowrap;
        }
        .session-status-label {
            color: #4b5563;
            font-size: 0.88rem;
            font-weight: 650;
        }
        .session-status-pill {
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 750;
            line-height: 1;
            padding: 0.32rem 0.62rem;
        }
        .session-status-pill-preparation {
            background: #dbeafe;
            color: #1d4ed8;
        }
        .session-status-pill-live {
            background: #dcfce7;
            color: #15803d;
        }
        .session-status-pill-closed {
            background: #e5e7eb;
            color: #374151;
        }
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
        ("Rejected", "status-rejected"),
    ]:
        label = STATUS_DISPLAY_LABELS.get(status, status)
        chips.append(f'<span class="status-chip {class_name}">{label}: {counts.get(status, 0)}</span>')
    st.markdown(f'<div class="status-row">{"".join(chips)}</div>', unsafe_allow_html=True)


def render_trade_status_panel(orders, user_id: int) -> None:
    """Surface declaration status changes without duplicating the full history table."""
    state_key = f"known_trade_statuses_{user_id}"
    if orders.empty:
        st.session_state.setdefault(state_key, {})
        st.caption("No trade declarations submitted yet.")
        return

    orders = infer_refusal_reasons(orders)

    current_statuses = {int(row["ID"]): row["Status"] for _, row in orders.iterrows()}
    previous_statuses = st.session_state.get(state_key)
    if previous_statuses is None:
        st.session_state[state_key] = current_statuses
    else:
        notification_statuses = {"Pending", "Matched", "Rejected"}
        for order_id, status in current_statuses.items():
            if status in notification_statuses and previous_statuses.get(order_id) != status:
                matching_row = orders.loc[orders["ID"] == order_id].iloc[0]
                declared_price = f"€ {matching_row['Price']:.1f}"
                if status == "Pending":
                    st.toast(
                        f":blue[Trade pending:] {matching_row['Option']} with {matching_row['Counterparty']}.",
                        icon=":material/hourglass_top:",
                    )
                elif status == "Matched":
                    st.toast(
                        f":green[Trade confirmed:] {matching_row['Option']} with {matching_row['Counterparty']} at {declared_price}.",
                        icon=":material/check_circle:",
                    )
                else:
                    reason = matching_row.get("Refusal Reason") or "Entered terms did not match"
                    st.toast(
                        f":red[Declaration rejected ({reason}):] {matching_row['Option']} with {matching_row['Counterparty']} at {declared_price}.",
                        icon=":material/error:",
                    )
        st.session_state[state_key] = current_statuses

    counts = orders["Status"].value_counts().to_dict()
    status_chips(counts)


def pending_trades_df(orders):
    if orders.empty or "Status" not in orders.columns:
        return orders

    pending = orders[orders["Status"] == "Pending"].copy()
    if pending.empty:
        return pending

    columns = ["Status", "Option", "Side", "Price", "Counterparty", "Created"]
    return pending[columns]


def rejected_transactions_df(orders):
    if orders.empty or "Status" not in orders.columns:
        return orders

    rejected = orders[orders["Status"] == "Rejected"].copy()
    if rejected.empty:
        return rejected

    if "Refusal Reason" in rejected.columns:
        rejected["Issue"] = rejected["Refusal Reason"].replace("", "Entered terms did not match")
    columns = ["Status", "Issue", "Option", "Side", "Price", "Counterparty", "Created"]
    return rejected[[column for column in columns if column in rejected.columns]]


def matched_trades_df(trades, current_username: str):
    if trades.empty:
        return trades

    output = trades.copy()
    output["Side"] = output["Buyer"].apply(lambda buyer: "Buy" if buyer == current_username else "Sell")
    output["Counterparty"] = output.apply(
        lambda row: row["Seller"] if row["Buyer"] == current_username else row["Buyer"],
        axis=1,
    )
    columns = ["Type", "Underlying", "Strike", "Side", "Counterparty", "Price", "Created"]
    return output[[column for column in columns if column in output.columns]]


def infer_refusal_reasons(df):
    if df.empty or "Status" not in df.columns:
        return df

    rejected = df[df["Status"] == "Rejected"].copy()
    if rejected.empty:
        df["Refusal Reason"] = ""
        return df

    reasons_by_id = {}
    instrument_column = "Option" if "Option" in rejected.columns else "Product"
    grouped = rejected.groupby(["Submitted By", "Counterparty", instrument_column], dropna=False)
    reverse_lookup = {
        (row["Counterparty"], row["Submitted By"], row[instrument_column]): row for _, row in rejected.iterrows()
    }

    for _, group in grouped:
        for _, row in group.iterrows():
            peer = reverse_lookup.get((row["Submitted By"], row["Counterparty"], row[instrument_column]))
            reason = row.get("Refusal Reason") or "Entered terms did not match"
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
    existing_reasons = output["Refusal Reason"] if "Refusal Reason" in output.columns else ""
    output["Refusal Reason"] = output["ID"].map(reasons_by_id).fillna(existing_reasons)
    return output
