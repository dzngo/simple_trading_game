import streamlit as st

from analytics import (
    active_options,
    cumulative_pnl_history_df,
    market_prices_df,
    options_df,
    orders_df,
    pnl_df,
    trades_df,
    users_by_role,
)
from db import get_session
from ui import (
    infer_refusal_reasons,
    matched_trades_df,
    pending_trades_df,
    refused_transactions_df,
)


@st.cache_data(ttl=600, max_entries=300, show_spinner=False)
def company_live_snapshot(game_session_id: int, user_id: int, username: str, version: int) -> dict:
    with get_session() as session:
        option_count = len(active_options(session, game_session_id))
        bank_count = len(users_by_role(session, "Bank", game_session_id))
        visible_options = options_df(session, game_session_id, include_market=False)
        orders = orders_df(session, game_session_id, user_id=user_id)
        orders_with_reasons = infer_refusal_reasons(orders)
        pending = pending_trades_df(orders_with_reasons)
        refused = refused_transactions_df(orders_with_reasons)
        trades = trades_df(session, game_session_id, user_id=user_id, source="Client-Bank")
        matched = matched_trades_df(trades, username)

    return {
        "option_count": option_count,
        "bank_count": bank_count,
        "visible_options": visible_options,
        "orders": orders,
        "pending": pending,
        "matched": matched,
        "refused": refused,
        "version": version,
    }


@st.cache_data(ttl=600, max_entries=300, show_spinner=False)
def bank_live_snapshot(game_session_id: int, user_id: int, username: str, version: int) -> dict:
    with get_session() as session:
        option_count = len(active_options(session, game_session_id))
        company_count = len(users_by_role(session, "Company", game_session_id))
        market_prices = market_prices_df(session, game_session_id)
        orders = orders_df(session, game_session_id, user_id=user_id)
        orders_with_reasons = infer_refusal_reasons(orders)
        pending = pending_trades_df(orders_with_reasons)
        refused = refused_transactions_df(orders_with_reasons)
        trades = trades_df(session, game_session_id, user_id=user_id, source="Client-Bank")
        matched = matched_trades_df(trades, username)
        market_trades = trades_df(session, game_session_id, user_id=user_id, source="Market")
        market_history = matched_trades_df(market_trades, username)

    return {
        "option_count": option_count,
        "company_count": company_count,
        "market_prices": market_prices,
        "orders": orders,
        "pending": pending,
        "matched": matched,
        "market_history": market_history,
        "refused": refused,
        "version": version,
    }


@st.cache_data(ttl=600, max_entries=100, show_spinner=False)
def professor_trade_history_snapshot(game_session_id: int, version: int) -> dict:
    with get_session() as session:
        all_orders = infer_refusal_reasons(orders_df(session, game_session_id))
        pending_orders = orders_df(session, game_session_id, status="Pending")
        refused_orders = infer_refusal_reasons(orders_df(session, game_session_id, status="Refused"))
        client_bank_trades = trades_df(session, game_session_id, source="Client-Bank")
        market_trades = trades_df(session, game_session_id, source="Market")

    return {
        "all_orders": all_orders,
        "pending_orders": pending_orders,
        "refused_orders": refused_orders,
        "client_bank_trades": client_bank_trades,
        "market_trades": market_trades,
        "version": version,
    }


@st.cache_data(ttl=600, max_entries=100, show_spinner=False)
def professor_pnl_snapshot(game_session_id: int, version: int) -> dict:
    with get_session() as session:
        pnl = pnl_df(session, game_session_id)
        pnl_history = cumulative_pnl_history_df(session, game_session_id)
    return {"pnl": pnl, "pnl_history": pnl_history, "version": version}
