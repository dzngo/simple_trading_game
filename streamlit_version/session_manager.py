from __future__ import annotations

from datetime import datetime
import re

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from models import (
    GameSession,
    MarketPrice,
    MarketPriceDraft,
    Option,
    Order,
    Participant,
    ParticipantEmail,
    Trade,
)


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SESSION_STATUS_LABELS = {
    "preparation": "Preparation",
    "live": "Live",
    "closed": "Closed",
}


def status_label(status: str) -> str:
    return SESSION_STATUS_LABELS.get(status, status.title())


def normalize_email(email: str) -> str:
    return email.strip().lower()


def parse_emails(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    candidates = re.split(r"[\s,;]+", raw_value)
    normalized = []
    seen = set()
    for candidate in candidates:
        email = normalize_email(candidate)
        if email and email not in seen:
            normalized.append(email)
            seen.add(email)
    return normalized


def email_list_text(participant: Participant) -> str:
    return "\n".join(email.email for email in sorted(participant.emails, key=lambda item: item.email))


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email))


def session_query() -> Select[tuple[GameSession]]:
    return select(GameSession).order_by(GameSession.created_at.desc(), GameSession.id.desc())


def live_sessions_for_email(session: Session, email: str) -> list[tuple[GameSession, Participant]]:
    normalized = normalize_email(email)
    statement = (
        select(GameSession, Participant)
        .join(Participant, Participant.game_session_id == GameSession.id)
        .join(ParticipantEmail, ParticipantEmail.participant_id == Participant.id)
        .where(GameSession.status == "live", ParticipantEmail.email == normalized)
        .order_by(GameSession.created_at.desc(), Participant.role, Participant.username)
    )
    return list(session.execute(statement).all())


def professor_participants_for_email(session: Session, email: str) -> list[Participant]:
    normalized = normalize_email(email)
    statement = (
        select(Participant)
        .join(ParticipantEmail)
        .join(GameSession)
        .where(Participant.role == "Professor", ParticipantEmail.email == normalized)
        .order_by(GameSession.created_at.desc())
    )
    return list(session.scalars(statement).all())


def create_game_session(session: Session, name: str) -> GameSession:
    game_session = GameSession(name=name.strip() or "Untitled session", status="preparation")
    session.add(game_session)
    session.flush()
    professor = Participant(game_session_id=game_session.id, username="Professor", role="Professor")
    session.add(professor)
    session.flush()
    return game_session


def default_participant_name(role: str, index: int) -> str:
    return f"{role} {index}"


def next_participant_index(session: Session, game_session_id: int, role: str) -> int:
    count = session.scalar(
        select(func.count(Participant.id)).where(
            Participant.game_session_id == game_session_id,
            Participant.role == role,
        )
    )
    return int(count or 0) + 1


def add_participant(session: Session, game_session_id: int, role: str) -> Participant:
    participant = Participant(
        game_session_id=game_session_id,
        role=role,
        username=default_participant_name(role, next_participant_index(session, game_session_id, role)),
    )
    session.add(participant)
    session.flush()
    return participant


def remove_participant(session: Session, participant_id: int) -> None:
    participant = session.get(Participant, participant_id)
    if participant is None:
        return
    if participant.game_session.status != "preparation":
        raise ValueError("Participants can only be removed during Preparation.")
    session.delete(participant)
    session.flush()


def set_participant_emails(session: Session, participant: Participant, emails: list[str]) -> None:
    participant.emails.clear()
    session.flush()
    for email in emails:
        participant.emails.append(ParticipantEmail(email=email))


def participants_for_session(session: Session, game_session_id: int, role: str | None = None) -> list[Participant]:
    statement = (
        select(Participant)
        .where(Participant.game_session_id == game_session_id)
        .options(joinedload(Participant.emails))
        .order_by(Participant.role, Participant.username, Participant.id)
    )
    if role is not None:
        statement = statement.where(Participant.role == role)
    return list(session.scalars(statement).unique().all())


def validate_session_setup(session: Session, game_session_id: int) -> list[str]:
    errors = []
    participants = participants_for_session(session, game_session_id)
    companies = [participant for participant in participants if participant.role == "Company"]
    banks = [participant for participant in participants if participant.role == "Bank"]
    professors = [participant for participant in participants if participant.role == "Professor"]

    if not companies:
        errors.append("Add at least one company.")
    if not banks:
        errors.append("Add at least one bank.")
    if not professors or not any(professor.emails for professor in professors):
        errors.append("Add at least one professor email.")

    names_by_role = set()
    all_emails = {}
    for participant in participants:
        name = participant.username.strip()
        if not name:
            errors.append(f"{participant.role} #{participant.id} needs a name.")
        name_key = (participant.role, name.lower())
        if name_key in names_by_role:
            errors.append(f"Duplicate {participant.role.lower()} name: {name}.")
        names_by_role.add(name_key)

        if participant.role in {"Company", "Bank"} and not participant.emails:
            errors.append(f"{participant.username} needs at least one authorized email.")

        for participant_email in participant.emails:
            email = normalize_email(participant_email.email)
            if not valid_email(email):
                errors.append(f"{participant.username} has an invalid email: {participant_email.email}.")
            if email in all_emails:
                errors.append(
                    f"Email {email} is assigned to both {all_emails[email]} and {participant.username}."
                )
            all_emails[email] = participant.username

    active_options = session.scalar(
        select(func.count(Option.id)).where(
            Option.game_session_id == game_session_id,
            Option.is_active.is_(True),
        )
    )
    if not active_options:
        errors.append("Add at least one active option.")

    return errors


def start_session(session: Session, game_session_id: int) -> list[str]:
    game_session = session.get(GameSession, game_session_id)
    if game_session is None:
        return ["Session not found."]
    if game_session.status != "preparation":
        return ["Only Preparation sessions can be started."]

    errors = validate_session_setup(session, game_session_id)
    if errors:
        return errors

    game_session.status = "live"
    game_session.started_at = datetime.utcnow()
    session.flush()
    return []


def close_session(session: Session, game_session_id: int) -> None:
    game_session = session.get(GameSession, game_session_id)
    if game_session is None:
        raise ValueError("Session not found.")
    if game_session.status != "live":
        raise ValueError("Only Live sessions can be closed.")
    game_session.status = "closed"
    game_session.closed_at = datetime.utcnow()
    session.flush()


def delete_preparation_session(session: Session, game_session_id: int) -> None:
    game_session = session.get(GameSession, game_session_id)
    if game_session is None:
        return
    if game_session.status != "preparation":
        raise ValueError("Only Preparation sessions can be deleted.")
    session.delete(game_session)
    session.flush()


def duplicate_session(
    session: Session,
    source_session_id: int,
    new_name: str,
    copy_student_emails: bool = False,
    copy_professor_emails: bool = True,
) -> GameSession:
    source = session.get(GameSession, source_session_id)
    if source is None:
        raise ValueError("Source session not found.")

    target = create_game_session(session, new_name)
    target_professor = participants_for_session(session, target.id, "Professor")[0]

    source_participants = participants_for_session(session, source_session_id)
    for participant in source_participants:
        if participant.role == "Professor":
            if copy_professor_emails:
                set_participant_emails(
                    session,
                    target_professor,
                    [participant_email.email for participant_email in participant.emails],
                )
            continue
        copied = Participant(
            game_session_id=target.id,
            role=participant.role,
            username=participant.username,
        )
        session.add(copied)
        session.flush()
        if copy_student_emails:
            set_participant_emails(
                session,
                copied,
                [participant_email.email for participant_email in participant.emails],
            )

    source_options = list(
        session.scalars(
            select(Option)
            .where(Option.game_session_id == source_session_id, Option.is_active.is_(True))
            .options(joinedload(Option.market_price), joinedload(Option.market_price_draft))
            .order_by(Option.display_order, Option.id)
        )
    )
    for source_option in source_options:
        copied_option = Option(
            game_session_id=target.id,
            option_type=source_option.option_type,
            underlying_asset=source_option.underlying_asset,
            strike_price=source_option.strike_price,
            is_active=True,
            display_order=source_option.display_order,
        )
        session.add(copied_option)
        session.flush()
        bid = source_option.market_price.bid_price if source_option.market_price else 9.0
        ask = source_option.market_price.ask_price if source_option.market_price else 11.0
        session.add(MarketPrice(option_id=copied_option.id, bid_price=bid, ask_price=ask))
        session.add(MarketPriceDraft(option_id=copied_option.id, draft_bid_price=bid, draft_ask_price=ask))

    session.flush()
    return target


def session_has_activity(session: Session, game_session_id: int) -> bool:
    order_count = session.scalar(select(func.count(Order.id)).where(Order.game_session_id == game_session_id))
    trade_count = session.scalar(select(func.count(Trade.id)).where(Trade.game_session_id == game_session_id))
    return bool(order_count or trade_count)
