from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from models import MarketPrice, Order, Trade


def normalize_price(price: float) -> float:
    return round(float(price), 1)


def opposite_side(side: str) -> str:
    return "Sell" if side == "Buy" else "Buy"


def create_trade_declaration(
    session: Session,
    user_id: int,
    counterparty_id: int,
    option_id: int,
    side: str,
    price: float,
) -> tuple[Order, Trade | None]:
    submitted_price = normalize_price(price)
    if submitted_price <= 0:
        raise ValueError("Trade price must be positive.")

    order = Order(
        user_id=user_id,
        counterparty_id=counterparty_id,
        option_id=option_id,
        side=side,
        price=submitted_price,
        status="Pending",
    )
    session.add(order)
    session.flush()

    reciprocal_orders = session.scalars(
        select(Order)
        .where(
            and_(
                Order.id != order.id,
                Order.status == "Pending",
                Order.option_id == option_id,
                Order.user_id == counterparty_id,
                Order.counterparty_id == user_id,
            )
        )
        .order_by(Order.created_at.asc())
    ).all()

    compatible_order = next(
        (
            reciprocal_order
            for reciprocal_order in reciprocal_orders
            if normalize_price(reciprocal_order.price) == submitted_price
            and reciprocal_order.side == opposite_side(side)
        ),
        None,
    )

    if compatible_order is not None:
        buyer_id = order.user_id if order.side == "Buy" else compatible_order.user_id
        seller_id = order.user_id if order.side == "Sell" else compatible_order.user_id
        trade = Trade(
            option_id=option_id,
            buyer_id=buyer_id,
            seller_id=seller_id,
            price=submitted_price,
            source="Client-Bank",
        )
        order.status = "Matched"
        compatible_order.status = "Matched"
        session.add(trade)
        session.flush()
        return order, trade

    if reciprocal_orders:
        order.status = "Refused"
        refused_peer = reciprocal_orders[0]
        refused_peer.status = "Refused"
        order.paired_order_id = refused_peer.id
        refused_peer.paired_order_id = order.id
        session.flush()

    return order, None


def create_market_trade(session: Session, bank_id: int, option_id: int, side: str) -> Trade:
    market_price = session.scalar(select(MarketPrice).where(MarketPrice.option_id == option_id))
    if market_price is None:
        raise ValueError("No published market price exists for this option.")

    if side == "Buy":
        price = normalize_price(market_price.ask_price)
        trade = Trade(
            option_id=option_id,
            buyer_id=bank_id,
            seller_id=None,
            price=price,
            source="Market",
        )
    else:
        price = normalize_price(market_price.bid_price)
        trade = Trade(
            option_id=option_id,
            buyer_id=None,
            seller_id=bank_id,
            price=price,
            source="Market",
        )

    session.add(trade)
    session.flush()
    return trade
