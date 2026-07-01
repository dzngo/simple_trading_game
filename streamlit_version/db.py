from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from models import Base


DATABASE_PATH = Path(__file__).resolve().parent / "trading_game.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        order_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(orders)")).fetchall()
        }
        if "paired_order_id" not in order_columns:
            connection.execute(text("ALTER TABLE orders ADD COLUMN paired_order_id INTEGER"))


def reset_db() -> None:
    table_names = [
        "market_price_drafts",
        "market_prices",
        "trades",
        "orders",
        "options",
        "products",
        "users",
    ]
    with engine.begin() as connection:
        for table_name in table_names:
            connection.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
    init_db()


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
