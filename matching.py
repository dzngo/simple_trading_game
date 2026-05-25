from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from models import Order, Trade


def opposite_side(side: str) -> str:
    return "Sell" if side == "Buy" else "Buy"


def create_trade_declaration(
    session: Session,
    user_id: int,
    counterparty_id: int,
    product_id: int,
    side: str,
    price: float,
) -> tuple[Order, Trade | None]:
    order = Order(
        user_id=user_id,
        counterparty_id=counterparty_id,
        product_id=product_id,
        side=side,
        price=price,
        status="Pending",
    )
    session.add(order)
    session.flush()

    reciprocal_order = session.scalar(
        select(Order)
        .where(
            and_(
                Order.id != order.id,
                Order.status == "Pending",
                Order.product_id == product_id,
                Order.user_id == counterparty_id,
                Order.counterparty_id == user_id,
            )
        )
        .order_by(Order.created_at.asc())
    )

    if reciprocal_order is None:
        return order, None

    if reciprocal_order.price != price or reciprocal_order.side != opposite_side(side):
        order.status = "Refused"
        reciprocal_order.status = "Refused"
        session.flush()
        return order, None

    buyer_id = order.user_id if order.side == "Buy" else reciprocal_order.user_id
    seller_id = order.user_id if order.side == "Sell" else reciprocal_order.user_id
    trade = Trade(
        product_id=product_id,
        buyer_id=buyer_id,
        seller_id=seller_id,
        price=price,
        source="Matched",
    )
    order.status = "Matched"
    reciprocal_order.status = "Matched"
    session.add(trade)
    session.flush()
    return order, trade
