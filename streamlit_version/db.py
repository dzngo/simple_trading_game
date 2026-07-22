from contextlib import contextmanager
import os
from pathlib import Path

import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from streamlit.runtime.scriptrunner_utils.exceptions import ScriptControlException

from models import Base


DATABASE_PATH = Path(__file__).resolve().parent / "trading_game.db"


def configured_database_url() -> str:
    if os.getenv("TRADING_GAME_FORCE_SQLITE") == "1":
        return f"sqlite:///{DATABASE_PATH}"

    try:
        database_url = st.secrets.get("DATABASE_URL")
    except Exception:
        database_url = None

    database_url = database_url or os.getenv("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return database_url

    return f"sqlite:///{DATABASE_PATH}"


DATABASE_URL = configured_database_url()

engine_options = {
    "connect_args": {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    "future": True,
}
if not DATABASE_URL.startswith("sqlite"):
    engine_options.update(
        {
            "pool_pre_ping": True,
            "pool_recycle": 300,
            "pool_use_lifo": True,
        }
    )

try:
    engine = create_engine(DATABASE_URL, **engine_options)
except ModuleNotFoundError as exc:
    if DATABASE_URL.startswith("postgresql") and exc.name == "psycopg":
        raise RuntimeError(
            "Postgres is configured through DATABASE_URL, but the psycopg driver is not installed. "
            "Install dependencies with `pip install -r requirements.txt` from the repository root, "
            "or remove DATABASE_URL locally to use SQLite fallback."
        ) from exc
    raise
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO game_session_states (game_session_id, version, updated_at)
                SELECT id, 1, CURRENT_TIMESTAMP
                FROM game_sessions
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM game_session_states
                    WHERE game_session_states.game_session_id = game_sessions.id
                )
                """
            )
        )
        if not DATABASE_URL.startswith("sqlite"):
            return
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
        "participant_emails",
        "participants",
        "game_session_states",
        "game_sessions",
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
    except ScriptControlException:
        session.commit()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
