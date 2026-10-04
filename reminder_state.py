"""Persistent, opt-in and rate-limited reminder state for one personal chat."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class ReminderDecision:
    status: str
    reason: str
    allowed: bool = False
    next_check_after: str | None = None


class ReminderStore:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        if not self.path.parent.is_dir():
            raise OSError("Dossier d'état des rappels indisponible")
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS reminder_state ("
            "chat_id TEXT PRIMARY KEY, enabled_until TEXT, "
            "last_claim_day TEXT, snoozed_until TEXT, acknowledged_day TEXT)"
        )
        return connection

    def enable(self, chat_id: str, now: datetime, days: int = 7) -> datetime:
        until = now + timedelta(days=days)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            # This is a personal tool: opting in a new chat revokes older recipients.
            db.execute("UPDATE reminder_state SET enabled_until=NULL WHERE chat_id<>?", (chat_id,))
            db.execute(
                "INSERT INTO reminder_state(chat_id, enabled_until, last_claim_day, snoozed_until, acknowledged_day) "
                "VALUES (?, ?, NULL, NULL, NULL) ON CONFLICT(chat_id) DO UPDATE SET "
                "enabled_until=excluded.enabled_until, snoozed_until=NULL, acknowledged_day=NULL",
                (chat_id, until.isoformat()),
            )
        return until

    def disable(self, chat_id: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute("UPDATE reminder_state SET enabled_until=NULL WHERE chat_id=?", (chat_id,))

    def acknowledge(self, chat_id: str, now: datetime) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "UPDATE reminder_state SET acknowledged_day=? WHERE chat_id=?",
                (now.date().isoformat(), chat_id),
            )

    def snooze(self, chat_id: str, now: datetime) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "UPDATE reminder_state SET snoozed_until=? WHERE chat_id=?",
                ((now + timedelta(days=1)).isoformat(), chat_id),
            )

    def _decision(self, row: tuple | None, now: datetime, has_log: bool) -> ReminderDecision:
        if row is None or row[0] is None:
            return ReminderDecision("disabled", "Rappels désactivés")
        enabled_until, last_claim_day, snoozed_until, acknowledged_day = row
        if now >= datetime.fromisoformat(enabled_until):
            return ReminderDecision("disabled", "Période d'essai expirée")
        if has_log:
            return ReminderDecision("completed", "Journal déjà rempli aujourd'hui")
        if acknowledged_day == now.date().isoformat():
            return ReminderDecision("acknowledged", "Rappel acquitté aujourd'hui")
        if snoozed_until and now < datetime.fromisoformat(snoozed_until):
            return ReminderDecision("snoozed", "Rappel reporté", next_check_after=snoozed_until)
        if last_claim_day == now.date().isoformat():
            return ReminderDecision("acknowledged", "Rappel déjà envoyé aujourd'hui")
        if not 8 <= now.hour < 21:
            return ReminderDecision("snoozed", "Plage calme", next_check_after=now.date().isoformat())
        return ReminderDecision("due", "Aucun log aujourd'hui", allowed=True)

    def status(self, chat_id: str, now: datetime, has_log: bool) -> ReminderDecision:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT enabled_until,last_claim_day,snoozed_until,acknowledged_day "
                "FROM reminder_state WHERE chat_id=?",
                (chat_id,),
            ).fetchone()
        return self._decision(row, now, has_log)

    def claim(self, chat_id: str, now: datetime, has_log: bool) -> ReminderDecision:
        """Reserve today's only reminder before sending it to Telegram."""
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT enabled_until,last_claim_day,snoozed_until,acknowledged_day "
                "FROM reminder_state WHERE chat_id=?",
                (chat_id,),
            ).fetchone()
            decision = self._decision(row, now, has_log)
            if decision.allowed:
                db.execute(
                    "UPDATE reminder_state SET last_claim_day=? WHERE chat_id=?",
                    (now.date().isoformat(), chat_id),
                )
        return decision
