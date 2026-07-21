from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

os.environ.setdefault("MPLCONFIGDIR", "/tmp/trading-game-matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/trading-game-cache")
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)

import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from analytics import (
    client_bank_trades_for_group,
    market_prices_df,
    option_label,
    orders_df,
    payoff_curve_df,
    selected_trade_totals,
    trades_df,
)
from models import GameSession, Participant, ParticipantEmail, User
from session_manager import participants_for_session, status_label


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("_") or "export"


def session_summary_df(game_session: GameSession) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Session": game_session.name,
                "Status": status_label(game_session.status),
                "Created": game_session.created_at,
                "Started": game_session.started_at,
                "Closed": game_session.closed_at,
            }
        ]
    )


def participants_df(session: Session, game_session_id: int) -> pd.DataFrame:
    participants = participants_for_session(session, game_session_id)
    return pd.DataFrame(
        [
            {
                "Role": participant.role,
                "Participant": participant.username,
                "Authorized Emails": "\n".join(
                    email.email for email in sorted(participant.emails, key=lambda item: item.email)
                ),
            }
            for participant in participants
        ]
    )


def export_workbook_bytes(session: Session, game_session_id: int) -> bytes:
    game_session = session.get(GameSession, game_session_id)
    if game_session is None:
        raise ValueError("Session not found.")

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        session_summary_df(game_session).to_excel(writer, sheet_name="Session", index=False)
        participants_df(session, game_session_id).to_excel(writer, sheet_name="Participants", index=False)
        market_prices_df(session, game_session_id, include_drafts=False).to_excel(
            writer,
            sheet_name="Options",
            index=False,
        )
        trades_df(session, game_session_id, source="Client-Bank").to_excel(
            writer,
            sheet_name="Company-Bank Trades",
            index=False,
        )
        trades_df(session, game_session_id, source="Market").to_excel(
            writer,
            sheet_name="Market Trades",
            index=False,
        )
        orders_df(session, game_session_id, status="Pending").to_excel(
            writer,
            sheet_name="Pending Declarations",
            index=False,
        )
        orders_df(session, game_session_id, status="Refused").to_excel(
            writer,
            sheet_name="Refused Diagnostics",
            index=False,
        )
    return output.getvalue()


def payoff_graph_zip_bytes(session: Session, game_session_id: int) -> bytes:
    participants = session.scalars(
        select(User)
        .where(User.game_session_id == game_session_id, User.role.in_(["Company", "Bank"]))
        .order_by(User.role, User.username)
    ).all()
    output = BytesIO()
    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as archive:
        for participant in participants:
            trades = client_bank_trades_for_group(session, game_session_id, participant.id)
            underlyings = sorted({trade.option.underlying_asset for trade in trades})
            for underlying in underlyings:
                underlying_trades = [trade for trade in trades if trade.option.underlying_asset == underlying]
                curve = payoff_curve_df(underlying_trades, participant.id)
                if curve.empty:
                    continue
                paid, received = selected_trade_totals(underlying_trades, participant.id)
                title = (
                    f"{participant.username} - {underlying} payoff "
                    f"(paid {paid:.1f}, received {received:.1f})"
                )
                figure, axis = plt.subplots(figsize=(10, 6))
                axis.plot(curve["x"], curve["Payoff"], marker="o", markersize=2, linewidth=1.8)
                axis.axhline(0, color="#666666", linewidth=0.8)
                axis.set_title(title)
                axis.set_xlabel("Final underlying price")
                axis.set_ylabel("Payoff")
                axis.grid(True, alpha=0.25)
                image_output = BytesIO()
                figure.savefig(image_output, format="png", dpi=150, bbox_inches="tight")
                plt.close(figure)
                image_bytes = image_output.getvalue()
                filename = (
                    f"{safe_filename(participant.username)}_"
                    f"{safe_filename(underlying)}_payoff.png"
                )
                archive.writestr(filename, image_bytes)
    return output.getvalue()
