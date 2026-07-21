import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from models import MarketPrice, Option, Order, Trade, User


def users_by_role(session: Session, role: str, game_session_id: int) -> list[User]:
    return list(
        session.scalars(
            select(User)
            .where(User.role == role, User.game_session_id == game_session_id)
            .order_by(User.username)
        )
    )


def trading_started(session: Session, game_session_id: int) -> bool:
    return session.scalar(select(func.count(Order.id)).where(Order.game_session_id == game_session_id)) > 0


def active_options(session: Session, game_session_id: int) -> list[Option]:
    return list(
        session.scalars(
            select(Option)
            .where(Option.game_session_id == game_session_id, Option.is_active.is_(True))
            .order_by(Option.display_order, Option.id)
        )
    )


def option_label(option: Option) -> str:
    return f"{option.option_type} {option.underlying_asset} K={option.strike_price}"


def options_df(session: Session, game_session_id: int, include_market: bool = False) -> pd.DataFrame:
    options = session.scalars(
        select(Option)
        .where(Option.game_session_id == game_session_id, Option.is_active.is_(True))
        .options(joinedload(Option.market_price))
        .order_by(Option.display_order, Option.id)
    ).all()
    rows = []
    for option in options:
        row = {
            "ID": option.id,
            "Type": option.option_type,
            "Underlying": option.underlying_asset,
            "Strike": option.strike_price,
        }
        if include_market:
            row["Bid"] = option.market_price.bid_price if option.market_price else None
            row["Ask"] = option.market_price.ask_price if option.market_price else None
        rows.append(row)
    return pd.DataFrame(rows)


def market_prices_df(session: Session, game_session_id: int, include_drafts: bool = False) -> pd.DataFrame:
    options = session.scalars(
        select(Option)
        .where(Option.game_session_id == game_session_id, Option.is_active.is_(True))
        .options(joinedload(Option.market_price), joinedload(Option.market_price_draft))
        .order_by(Option.display_order, Option.id)
    ).all()
    rows = []
    for option in options:
        row = {
            "Option": option_label(option),
            "Type": option.option_type,
            "Underlying": option.underlying_asset,
            "Strike": option.strike_price,
            "Bid": option.market_price.bid_price if option.market_price else None,
            "Ask": option.market_price.ask_price if option.market_price else None,
            "Updated": option.market_price.updated_at if option.market_price else None,
        }
        if include_drafts:
            row["Draft Bid"] = (
                option.market_price_draft.draft_bid_price if option.market_price_draft else None
            )
            row["Draft Ask"] = (
                option.market_price_draft.draft_ask_price if option.market_price_draft else None
            )
        rows.append(row)
    return pd.DataFrame(rows)


def market_price_for_option(
    session: Session,
    option_id: int,
    game_session_id: int,
    default_bid: float = 9.0,
    default_ask: float = 11.0,
) -> tuple[float, float]:
    price = session.scalar(
        select(MarketPrice)
        .join(Option)
        .where(MarketPrice.option_id == option_id, Option.game_session_id == game_session_id)
    )
    if price is None:
        return default_bid, default_ask
    return float(price.bid_price), float(price.ask_price)


def orders_df(
    session: Session,
    game_session_id: int,
    user_id: int | None = None,
    status: str | None = None,
) -> pd.DataFrame:
    statement = (
        select(Order)
        .options(
            joinedload(Order.user),
            joinedload(Order.counterparty),
            joinedload(Order.option),
        )
        .order_by(Order.created_at.desc())
        .where(Order.game_session_id == game_session_id)
    )
    if user_id is not None:
        # Counterparty declarations remain private until a trade resolves.
        statement = statement.where(Order.user_id == user_id)
    if status is not None:
        statement = statement.where(Order.status == status)

    rows = session.scalars(statement).all()
    refusal_reasons = refusal_reasons_for_orders(session, rows) if user_id is not None else {}
    return pd.DataFrame(
        [
            {
                "ID": order.id,
                "Submitted By": order.user.username,
                "Counterparty": order.counterparty.username,
                "Option": option_label(order.option),
                "Type": order.option.option_type,
                "Underlying": order.option.underlying_asset,
                "Strike": order.option.strike_price,
                "Side": order.side,
                "Price": order.price,
                "Status": order.status,
                "Paired Order ID": order.paired_order_id,
                "Refusal Reason": refusal_reasons.get(order.id, ""),
                "Created": order.created_at,
            }
            for order in rows
        ]
    )


def refusal_reasons_for_orders(session: Session, orders: list[Order]) -> dict[int, str]:
    reasons = {}
    refused_orders = [order for order in orders if order.status == "Refused"]
    for order in refused_orders:
        peer = session.get(Order, order.paired_order_id) if order.paired_order_id is not None else None
        if peer is None:
            peer = session.scalar(
                select(Order)
                .where(
                    Order.status == "Refused",
                    Order.option_id == order.option_id,
                    Order.user_id == order.counterparty_id,
                    Order.counterparty_id == order.user_id,
                )
                .order_by(Order.created_at.desc())
            )
        if peer is None:
            reasons[order.id] = "Terms did not match"
            continue

        price_mismatch = round(float(order.price), 1) != round(float(peer.price), 1)
        side_mismatch = order.side == peer.side
        if price_mismatch and side_mismatch:
            reasons[order.id] = "Price and side mismatch"
        elif price_mismatch:
            reasons[order.id] = "Price mismatch"
        elif side_mismatch:
            reasons[order.id] = "Side mismatch"
        else:
            reasons[order.id] = "Terms did not match"
    return reasons


def trades_df(
    session: Session,
    game_session_id: int,
    user_id: int | None = None,
    source: str | None = None,
) -> pd.DataFrame:
    statement = (
        select(Trade)
        .options(
            joinedload(Trade.option),
            joinedload(Trade.buyer),
            joinedload(Trade.seller),
        )
        .order_by(Trade.created_at.desc())
        .where(Trade.game_session_id == game_session_id)
    )
    if user_id is not None:
        statement = statement.where((Trade.buyer_id == user_id) | (Trade.seller_id == user_id))
    if source is not None:
        statement = statement.where(Trade.source == source)

    rows = session.scalars(statement).all()
    return pd.DataFrame(
        [
            {
                "ID": trade.id,
                "Option": option_label(trade.option),
                "Type": trade.option.option_type,
                "Underlying": trade.option.underlying_asset,
                "Strike": trade.option.strike_price,
                "Buyer": participant_name(trade.buyer_id, trade.buyer),
                "Seller": participant_name(trade.seller_id, trade.seller),
                "Price": trade.price,
                "Source": trade.source,
                "Created": trade.created_at,
            }
            for trade in rows
        ]
    )


def pnl_df(session: Session, game_session_id: int) -> pd.DataFrame:
    users = session.scalars(
        select(User)
        .where(User.game_session_id == game_session_id, User.role != "Professor")
        .order_by(User.username)
    ).all()
    balances = {user.id: {"Participant": user.username, "Cumulative P/L": 0.0} for user in users}

    trades = session.scalars(
        select(Trade).where(Trade.game_session_id == game_session_id).order_by(Trade.created_at.asc())
    ).all()
    for trade in trades:
        if trade.buyer_id in balances:
            balances[trade.buyer_id]["Cumulative P/L"] -= trade.price
        if trade.seller_id in balances:
            balances[trade.seller_id]["Cumulative P/L"] += trade.price

    return pd.DataFrame(balances.values())


def cumulative_pnl_history_df(session: Session, game_session_id: int) -> pd.DataFrame:
    users = session.scalars(
        select(User)
        .where(User.game_session_id == game_session_id, User.role != "Professor")
        .order_by(User.username)
    ).all()
    balances = {user.id: 0.0 for user in users}
    names = {user.id: user.username for user in users}
    records = []

    trades = session.scalars(
        select(Trade).where(Trade.game_session_id == game_session_id).order_by(Trade.created_at.asc())
    ).all()
    for trade in trades:
        if trade.buyer_id in balances:
            balances[trade.buyer_id] -= trade.price
        if trade.seller_id in balances:
            balances[trade.seller_id] += trade.price
        for participant_id, balance in balances.items():
            records.append(
                {
                    "Trade ID": trade.id,
                    "Created": trade.created_at,
                    "Participant": names[participant_id],
                    "Cumulative P/L": balance,
                }
            )

    return pd.DataFrame(records)


def trading_activity_df(session: Session, game_session_id: int) -> pd.DataFrame:
    df = trades_df(session, game_session_id)
    if df.empty:
        return pd.DataFrame(columns=["Option", "Source", "Trades"])
    return df.groupby(["Option", "Source"], as_index=False).size().rename(columns={"size": "Trades"})


def client_bank_trades_for_group(session: Session, game_session_id: int, user_id: int) -> list[Trade]:
    return list(
        session.scalars(
            select(Trade)
            .where(
                Trade.game_session_id == game_session_id,
                Trade.source == "Client-Bank",
                (Trade.buyer_id == user_id) | (Trade.seller_id == user_id),
            )
            .options(joinedload(Trade.option), joinedload(Trade.buyer), joinedload(Trade.seller))
            .order_by(Trade.created_at.asc())
        )
    )


def selected_trade_totals(trades: list[Trade], user_id: int) -> tuple[float, float]:
    paid = sum(trade.price for trade in trades if trade.buyer_id == user_id)
    received = sum(trade.price for trade in trades if trade.seller_id == user_id)
    return paid, received


def payoff_curve_df(trades: list[Trade], user_id: int) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(columns=["x", "Payoff"])

    max_strike = max(trade.option.strike_price for trade in trades)
    max_x = max(1, max_strike * 2)
    step = max(max_x / 100, 1)
    xs = [round(index * step, 2) for index in range(101)]
    records = []

    for x in xs:
        payoff = 0.0
        for trade in trades:
            if trade.option.option_type == "Call":
                option_payoff = max(x - trade.option.strike_price, 0)
            else:
                option_payoff = max(trade.option.strike_price - x, 0)
            direction = 1 if trade.buyer_id == user_id else -1
            payoff += direction * option_payoff
        records.append({"x": x, "Payoff": payoff})

    return pd.DataFrame(records)


def participant_name(participant_id: int | None, user: User | None) -> str:
    if participant_id is None:
        return "Market"
    return user.username if user is not None else f"User {participant_id}"
