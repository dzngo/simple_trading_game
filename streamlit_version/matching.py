from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from models import GameSession, MarketPrice, Option, Order, Trade, User
from state import bump_session_version


def normalize_price(price: float) -> float:
    return round(float(price), 1)


def opposite_side(side: str) -> str:
    return "Sell" if side == "Buy" else "Buy"


def create_trade_declaration(
    session: Session,
    game_session_id: int,
    user_id: int,
    counterparty_id: int,
    option_id: int,
    side: str,
    price: float,
) -> tuple[Order, Trade | None]:
    game_session = session.get(GameSession, game_session_id)
    if game_session is None:
        raise ValueError("Session not found.")
    if game_session.status != "live":
        raise ValueError("Trade declarations are only allowed in Live sessions.")

    option = session.get(Option, option_id)
    if option is None or option.game_session_id != game_session_id:
        raise ValueError("Option does not belong to this session.")
    user = session.get(User, user_id)
    counterparty = session.get(User, counterparty_id)
    if (
        user is None
        or counterparty is None
        or user.game_session_id != game_session_id
        or counterparty.game_session_id != game_session_id
    ):
        raise ValueError("Participants do not belong to this session.")

    submitted_price = normalize_price(price)
    if submitted_price <= 0:
        raise ValueError("Trade price must be positive.")

    order = Order(
        game_session_id=game_session_id,
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
                Order.game_session_id == game_session_id,
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
            game_session_id=game_session_id,
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
        bump_session_version(session, game_session_id)
        return order, trade

    if reciprocal_orders:
        order.status = "Rejected"
        rejected_peer = reciprocal_orders[0]
        rejected_peer.status = "Rejected"
        order.paired_order_id = rejected_peer.id
        rejected_peer.paired_order_id = order.id
        session.flush()

    bump_session_version(session, game_session_id)
    return order, None


def create_market_trade(session: Session, game_session_id: int, bank_id: int, option_id: int, side: str) -> Trade:
    game_session = session.get(GameSession, game_session_id)
    if game_session is None:
        raise ValueError("Session not found.")
    if game_session.status != "live":
        raise ValueError("Market trades are only allowed in Live sessions.")

    market_price = session.scalar(
        select(MarketPrice)
        .join(Option)
        .where(MarketPrice.option_id == option_id, Option.game_session_id == game_session_id)
    )
    bank = session.get(User, bank_id)
    if bank is None or bank.game_session_id != game_session_id or bank.role != "Bank":
        raise ValueError("Bank does not belong to this session.")
    if market_price is None:
        raise ValueError("No current market price exists for this option.")

    if side == "Buy":
        price = normalize_price(market_price.ask_price)
        trade = Trade(
            game_session_id=game_session_id,
            option_id=option_id,
            buyer_id=bank_id,
            seller_id=None,
            price=price,
            source="Market",
        )
    else:
        price = normalize_price(market_price.bid_price)
        trade = Trade(
            game_session_id=game_session_id,
            option_id=option_id,
            buyer_id=None,
            seller_id=bank_id,
            price=price,
            source="Market",
        )

    session.add(trade)
    session.flush()
    bump_session_version(session, game_session_id)
    return trade
