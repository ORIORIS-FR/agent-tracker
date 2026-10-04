"""Deterministic journal operations for the personal Tracker service."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from threading import RLock


_JOURNAL_LOCK = RLock()
_T0_IN_ENTRY = re.compile(r"\(T0:([01]?\d|2[0-3])h([0-5]\d)\)")
_EXPLICIT_T0 = re.compile(
    r"\b(?:pris|prise)\s+à\s+([01]?\d|2[0-3])(?:h([0-5]\d)?|:([0-5]\d))\b",
    re.IGNORECASE,
)


class JournalUnavailable(OSError):
    """The journal could not be read or written."""


def clean_text(value: str) -> str:
    """Keep user text in one Markdown table cell without altering its meaning."""
    return " ".join(value.replace("|", "/").replace("\x00", " ").split())


def explicit_t0(message: str) -> str | None:
    """Accept a dose time only when the user explicitly says 'pris à HHhMM'."""
    match = _EXPLICIT_T0.search(message)
    if not match:
        return None
    hour = int(match.group(1))
    minute = match.group(2) or match.group(3) or "00"
    return f"{hour:02d}h{minute}"


def _read_t0_unlocked(path: Path, day: str) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise JournalUnavailable("Lecture du journal impossible") from exc

    for line in reversed(lines):
        if not line.startswith(f"| {day} "):
            continue
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) < 4:
            continue
        state = cells[2]
        if state == "CYCLE RESET":
            return None
        match = _T0_IN_ENTRY.search(state)
        if match:
            return f"{int(match.group(1)):02d}h{match.group(2)}"
    return None


def read_t0(path: Path, day: str) -> str | None:
    with _JOURNAL_LOCK:
        return _read_t0_unlocked(path, day)


def has_observation(path: Path, day: str) -> bool:
    """A reset starts a new episode; only a later log completes that episode."""
    with _JOURNAL_LOCK:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise JournalUnavailable("Lecture du journal impossible") from exc
        for line in reversed(lines):
            if not line.startswith(f"| {day} "):
                continue
            cells = [cell.strip() for cell in line.split("|")]
            if len(cells) < 4:
                continue
            return cells[2] != "CYCLE RESET"
    return False


def _append_unlocked(path: Path, line: str) -> None:
    if not path.parent.is_dir():
        raise JournalUnavailable("Dossier du journal indisponible")
    try:
        with path.open("a", encoding="utf-8", newline="\n") as journal:
            journal.write(line)
            journal.flush()
    except OSError as exc:
        raise JournalUnavailable("Écriture du journal impossible") from exc


def elapsed_label(now: datetime, t0: str | None) -> str:
    if t0 is None:
        return "T0 manquant"
    match = re.fullmatch(r"([01]?\d|2[0-3])h([0-5]\d)", t0)
    if not match:
        return "T0 manquant"
    start = now.replace(
        hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0
    )
    seconds = int((now - start).total_seconds())
    if seconds < 0:
        return f"Erreur Chrono (T0:{t0})"
    hours, remainder = divmod(seconds, 3600)
    return f"T+{hours}h{remainder // 60:02d} (T0:{t0})"


def append_reset(path: Path, now: datetime) -> None:
    line = f"| {now:%Y-%m-%d %H:%M} | CYCLE RESET | Purge manuelle | Aucune data |\n"
    with _JOURNAL_LOCK:
        _append_unlocked(path, line)


def append_observation(path: Path, now: datetime, message: str, tags: list[str]) -> str:
    """Read the current cycle and append one observation under the same lock."""
    safe_message = clean_text(message)
    with _JOURNAL_LOCK:
        t0 = explicit_t0(safe_message) or _read_t0_unlocked(path, now.strftime("%Y-%m-%d"))
        state = elapsed_label(now, t0)
        safe_tags = ", ".join(clean_text(tag)[:80] for tag in tags) if tags else "Aucune data"
        line = f"| {now:%Y-%m-%d %H:%M} | {state} | {safe_message} | {safe_tags} |\n"
        _append_unlocked(path, line)
    return state
