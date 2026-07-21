from sqlalchemy import inspect, select

from db import engine, get_session, init_db, reset_db
from models import GameSession, MarketPrice, MarketPriceDraft, Option, ParticipantEmail, User


DEMO_USERS = [
    ("Company 1", "Company", ["company1@example.com"]),
    ("Company 2", "Company", ["company2@example.com"]),
    ("Bank 1", "Bank", ["bank1@example.com"]),
    ("Bank 2", "Bank", ["bank2@example.com"]),
    ("Professor", "Professor", ["professor@example.com"]),
]

DEMO_OPTIONS = [
    {
        "option_type": "Call",
        "underlying_asset": "Asset A",
        "strike_price": 100,
        "bid_price": 9.0,
        "ask_price": 11.0,
    },
    {
        "option_type": "Put",
        "underlying_asset": "Asset A",
        "strike_price": 100,
        "bid_price": 8.0,
        "ask_price": 10.0,
    },
]


def schema_needs_reset() -> bool:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not tables:
        return False
    if "game_sessions" not in tables or "participants" not in tables:
        return True
    if "products" in tables:
        return True
    if "users" in tables:
        return True
    if "options" not in tables:
        return True
    option_columns = {column["name"] for column in inspector.get_columns("options")}
    if "game_session_id" not in option_columns:
        return True
    if "orders" in tables:
        order_columns = {column["name"] for column in inspector.get_columns("orders")}
        if "option_id" not in order_columns or "game_session_id" not in order_columns:
            return True
    if "market_prices" in tables:
        price_columns = {column["name"] for column in inspector.get_columns("market_prices")}
        if not {"bid_price", "ask_price"}.issubset(price_columns):
            return True
    return False


def seed_demo_data(reset: bool = False) -> None:
    if reset or schema_needs_reset():
        reset_db()
    else:
        init_db()

    with get_session() as session:
        existing_session = session.scalar(select(GameSession).where(GameSession.name == "Demo Session"))
        if existing_session is not None:
            return

        game_session = GameSession(name="Demo Session", status="live")
        session.add(game_session)
        session.flush()

        for username, role, emails in DEMO_USERS:
            participant = User(game_session_id=game_session.id, username=username, role=role)
            session.add(participant)
            session.flush()
            for email in emails:
                session.add(ParticipantEmail(participant_id=participant.id, email=email))

        for index, option_data in enumerate(DEMO_OPTIONS, start=1):
            option = Option(
                game_session_id=game_session.id,
                option_type=option_data["option_type"],
                underlying_asset=option_data["underlying_asset"],
                strike_price=option_data["strike_price"],
                is_active=True,
                display_order=index,
            )
            session.add(option)
            session.flush()
            session.add(
                MarketPrice(
                    option_id=option.id,
                    bid_price=option_data["bid_price"],
                    ask_price=option_data["ask_price"],
                )
            )
            session.add(
                MarketPriceDraft(
                    option_id=option.id,
                    draft_bid_price=option_data["bid_price"],
                    draft_ask_price=option_data["ask_price"],
                )
            )


if __name__ == "__main__":
    seed_demo_data(reset=True)
    print("Database reset and seeded with demo data.")
