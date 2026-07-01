from sqlalchemy import inspect, select

from db import engine, get_session, init_db, reset_db
from models import MarketPrice, MarketPriceDraft, Option, User


DEMO_USERS = [
    ("Company A", "Company"),
    ("Company B", "Company"),
    ("Bank X", "Bank"),
    ("Bank Y", "Bank"),
    ("Professor", "Professor"),
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
    if "products" in tables:
        return True
    if "options" not in tables:
        return True
    if "orders" in tables:
        order_columns = {column["name"] for column in inspector.get_columns("orders")}
        if "option_id" not in order_columns:
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
        for username, role in DEMO_USERS:
            existing = session.scalar(select(User).where(User.username == username))
            if existing is None:
                session.add(User(username=username, role=role))

        session.flush()

        existing_options = session.scalars(select(Option)).all()
        if not existing_options:
            for index, option_data in enumerate(DEMO_OPTIONS, start=1):
                option = Option(
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
