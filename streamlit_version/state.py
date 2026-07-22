from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from db import get_session
from models import GameSessionState


def current_session_version(game_session_id: int) -> int:
    with get_session() as session:
        version = session.scalar(
            select(GameSessionState.version).where(GameSessionState.game_session_id == game_session_id)
        )
    return int(version or 0)


def create_session_state(session: Session, game_session_id: int) -> GameSessionState:
    state = session.get(GameSessionState, game_session_id)
    if state is None:
        state = GameSessionState(game_session_id=game_session_id, version=1)
        session.add(state)
        session.flush()
    return state


def bump_session_version(session: Session, game_session_id: int) -> int:
    result = session.execute(
        update(GameSessionState)
        .where(GameSessionState.game_session_id == game_session_id)
        .values(
            version=GameSessionState.version + 1,
            updated_at=datetime.utcnow(),
        )
    )
    if result.rowcount == 0:
        create_session_state(session, game_session_id)
        result = session.execute(
            update(GameSessionState)
            .where(GameSessionState.game_session_id == game_session_id)
            .values(
                version=GameSessionState.version + 1,
                updated_at=datetime.utcnow(),
            )
        )
    session.flush()
    version = session.scalar(
        select(GameSessionState.version).where(GameSessionState.game_session_id == game_session_id)
    )
    return int(version or 0)
