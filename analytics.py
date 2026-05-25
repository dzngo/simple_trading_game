import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from models import MarketPrice, Order, Product, Trade, User


def users_by_role(session: Session, role: str) -> list[User]:
    return list(session.scalars(select(User).where(User.role == role).order_by(User.username)))


def products(session: Session) -> list[Product]:
    return list(session.scalars(select(Product).order_by(Product.name)))


def market_prices_df(session: Session) -> pd.DataFrame:
    prices = session.scalars(
        select(MarketPrice).options(joinedload(MarketPrice.product)).order_by(MarketPrice.id)
    ).all()
    return pd.DataFrame(
        [
            {
                "Product": price.product.name,
                "Market Price": price.market_price,
                "Updated": price.updated_at,
            }
            for price in prices
        ]
    )


def market_price_for_product(session: Session, product_id: int, default: float = 10.0) -> float:
    price = session.scalar(select(MarketPrice).where(MarketPrice.product_id == product_id))
    return float(price.market_price) if price is not None else default


def orders_df(session: Session, user_id: int | None = None, status: str | None = None) -> pd.DataFrame:
    statement = (
        select(Order)
        .options(
            joinedload(Order.user),
            joinedload(Order.counterparty),
            joinedload(Order.product),
        )
        .order_by(Order.created_at.desc())
    )
    if user_id is not None:
        statement = statement.where((Order.user_id == user_id) | (Order.counterparty_id == user_id))
    if status is not None:
        statement = statement.where(Order.status == status)

    rows = session.scalars(statement).all()
    return pd.DataFrame(
        [
            {
                "ID": order.id,
                "Submitted By": order.user.username,
                "Counterparty": order.counterparty.username,
                "Product": order.product.name,
                "Side": order.side,
                "Price": order.price,
                "Status": order.status,
                "Created": order.created_at,
            }
            for order in rows
        ]
    )


def trades_df(session: Session, user_id: int | None = None) -> pd.DataFrame:
    statement = (
        select(Trade)
        .options(
            joinedload(Trade.product),
            joinedload(Trade.buyer),
            joinedload(Trade.seller),
        )
        .order_by(Trade.created_at.desc())
    )
    if user_id is not None:
        statement = statement.where((Trade.buyer_id == user_id) | (Trade.seller_id == user_id))

    rows = session.scalars(statement).all()
    return pd.DataFrame(
        [
            {
                "ID": trade.id,
                "Product": trade.product.name,
                "Buyer": participant_name(trade.buyer_id, trade.buyer),
                "Seller": participant_name(trade.seller_id, trade.seller),
                "Price": trade.price,
                "Source": trade.source,
                "Created": trade.created_at,
            }
            for trade in rows
        ]
    )


def pnl_df(session: Session) -> pd.DataFrame:
    users = session.scalars(select(User).where(User.role != "Professor").order_by(User.username)).all()
    balances = {user.id: {"Participant": user.username, "Cumulative P/L": 0.0} for user in users}

    trades = session.scalars(select(Trade).order_by(Trade.created_at.asc())).all()
    for trade in trades:
        if trade.buyer_id in balances:
            balances[trade.buyer_id]["Cumulative P/L"] -= trade.price
        if trade.seller_id in balances:
            balances[trade.seller_id]["Cumulative P/L"] += trade.price

    return pd.DataFrame(balances.values())


def cumulative_pnl_history_df(session: Session) -> pd.DataFrame:
    users = session.scalars(select(User).where(User.role != "Professor").order_by(User.username)).all()
    balances = {user.id: 0.0 for user in users}
    names = {user.id: user.username for user in users}
    records = []

    trades = session.scalars(select(Trade).order_by(Trade.created_at.asc())).all()
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


def trading_activity_df(session: Session) -> pd.DataFrame:
    df = trades_df(session)
    if df.empty:
        return pd.DataFrame(columns=["Product", "Source", "Trades"])
    return df.groupby(["Product", "Source"], as_index=False).size().rename(columns={"size": "Trades"})


def participant_name(participant_id: int, user: User | None) -> str:
    return user.username if user is not None else f"User {participant_id}"
