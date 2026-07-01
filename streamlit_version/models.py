from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)


class Option(Base):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(primary_key=True)
    option_type: Mapped[str] = mapped_column(String(10), nullable=False)
    underlying_asset: Mapped[str] = mapped_column(String(30), nullable=False)
    strike_price: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    market_price: Mapped["MarketPrice"] = relationship(back_populates="option", uselist=False)
    market_price_draft: Mapped["MarketPriceDraft"] = relationship(back_populates="option", uselist=False)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    counterparty_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    option_id: Mapped[int] = mapped_column(ForeignKey("options.id"), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    counterparty: Mapped[User] = relationship(foreign_keys=[counterparty_id])
    option: Mapped[Option] = relationship()


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    option_id: Mapped[int] = mapped_column(ForeignKey("options.id"), nullable=False)
    buyer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    seller_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    option: Mapped[Option] = relationship()
    buyer: Mapped[User | None] = relationship(foreign_keys=[buyer_id])
    seller: Mapped[User | None] = relationship(foreign_keys=[seller_id])


class MarketPrice(Base):
    __tablename__ = "market_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    option_id: Mapped[int] = mapped_column(ForeignKey("options.id"), unique=True, nullable=False)
    bid_price: Mapped[float] = mapped_column(Float, nullable=False)
    ask_price: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    option: Mapped[Option] = relationship(back_populates="market_price")


class MarketPriceDraft(Base):
    __tablename__ = "market_price_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    option_id: Mapped[int] = mapped_column(ForeignKey("options.id"), unique=True, nullable=False)
    draft_bid_price: Mapped[float] = mapped_column(Float, nullable=False)
    draft_ask_price: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    option: Mapped[Option] = relationship(back_populates="market_price_draft")
