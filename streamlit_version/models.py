from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="preparation", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    participants: Mapped[list["Participant"]] = relationship(
        back_populates="game_session",
        cascade="all, delete-orphan",
    )
    options: Mapped[list["Option"]] = relationship(
        back_populates="game_session",
        cascade="all, delete-orphan",
    )
    state: Mapped["GameSessionState"] = relationship(
        back_populates="game_session",
        cascade="all, delete-orphan",
        uselist=False,
    )


class GameSessionState(Base):
    __tablename__ = "game_session_states"

    game_session_id: Mapped[int] = mapped_column(ForeignKey("game_sessions.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    game_session: Mapped[GameSession] = relationship(back_populates="state")


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("game_session_id", "role", "username"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_session_id: Mapped[int] = mapped_column(ForeignKey("game_sessions.id"), nullable=False)
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)

    game_session: Mapped[GameSession] = relationship(back_populates="participants")
    emails: Mapped[list["ParticipantEmail"]] = relationship(
        back_populates="participant",
        cascade="all, delete-orphan",
    )


class ParticipantEmail(Base):
    __tablename__ = "participant_emails"
    __table_args__ = (UniqueConstraint("participant_id", "email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)

    participant: Mapped[Participant] = relationship(back_populates="emails")


class Option(Base):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_session_id: Mapped[int] = mapped_column(ForeignKey("game_sessions.id"), nullable=False)
    option_type: Mapped[str] = mapped_column(String(10), nullable=False)
    underlying_asset: Mapped[str] = mapped_column(String(30), nullable=False)
    strike_price: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    game_session: Mapped[GameSession] = relationship(back_populates="options")
    market_price: Mapped["MarketPrice"] = relationship(
        back_populates="option",
        cascade="all, delete-orphan",
        uselist=False,
    )
    market_price_draft: Mapped["MarketPriceDraft"] = relationship(
        back_populates="option",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_session_id: Mapped[int] = mapped_column(ForeignKey("game_sessions.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), nullable=False)
    counterparty_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), nullable=False)
    option_id: Mapped[int] = mapped_column(ForeignKey("options.id"), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Pending")
    paired_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    game_session: Mapped[GameSession] = relationship()
    user: Mapped[Participant] = relationship(foreign_keys=[user_id])
    counterparty: Mapped[Participant] = relationship(foreign_keys=[counterparty_id])
    option: Mapped[Option] = relationship()


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_session_id: Mapped[int] = mapped_column(ForeignKey("game_sessions.id"), nullable=False)
    option_id: Mapped[int] = mapped_column(ForeignKey("options.id"), nullable=False)
    buyer_id: Mapped[int | None] = mapped_column(ForeignKey("participants.id"), nullable=True)
    seller_id: Mapped[int | None] = mapped_column(ForeignKey("participants.id"), nullable=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    game_session: Mapped[GameSession] = relationship()
    option: Mapped[Option] = relationship()
    buyer: Mapped[Participant | None] = relationship(foreign_keys=[buyer_id])
    seller: Mapped[Participant | None] = relationship(foreign_keys=[seller_id])


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


# Backward-compatible import name used by the existing pages.
User = Participant
