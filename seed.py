from sqlalchemy import delete, select

from db import get_session, init_db
from models import MarketPrice, Order, Product, Trade, User


DEMO_USERS = [
    ("Company A", "Company"),
    ("Company B", "Company"),
    ("Bank X", "Bank"),
    ("Bank Y", "Bank"),
    ("Professor", "Professor"),
]

DEMO_PRODUCTS = ["Call", "Put"]

INITIAL_MARKET_PRICES = {
    "Call": 10.0,
    "Put": 9.0,
}


def seed_demo_data(reset: bool = False) -> None:
    init_db()
    with get_session() as session:
        if reset:
            session.execute(delete(Trade))
            session.execute(delete(Order))
            session.execute(delete(MarketPrice))
            session.execute(delete(Product))
            session.execute(delete(User))
            session.flush()

        for username, role in DEMO_USERS:
            existing = session.scalar(select(User).where(User.username == username))
            if existing is None:
                session.add(User(username=username, role=role))

        session.flush()

        for product_name in DEMO_PRODUCTS:
            product = session.scalar(select(Product).where(Product.name == product_name))
            if product is None:
                product = Product(name=product_name)
                session.add(product)
                session.flush()

            market_price = session.scalar(
                select(MarketPrice).where(MarketPrice.product_id == product.id)
            )
            if market_price is None:
                session.add(
                    MarketPrice(
                        product_id=product.id,
                        market_price=INITIAL_MARKET_PRICES[product_name],
                    )
                )


if __name__ == "__main__":
    seed_demo_data(reset=True)
    print("Database reset and seeded with demo data.")
