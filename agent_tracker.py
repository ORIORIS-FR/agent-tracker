"""Personal journal API: n8n handles channels; this service owns journal and reminder state."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from reminder_state import ReminderStore
from tracker_core import JournalUnavailable, append_observation, append_reset, clean_text, has_observation, read_t0


logger = logging.getLogger(__name__)
PARIS = ZoneInfo("Europe/Paris")
JOURNAL_PATH = Path(os.getenv("TRACKER_JOURNAL_PATH", "/data/journal.md"))
STATE_PATH = Path(os.getenv("TRACKER_STATE_DB", "/data/tracker_state.sqlite3"))
reminders = ReminderStore(STATE_PATH)
app = FastAPI(title="Agent Tracker")


class AnalyseClinique(BaseModel):
    """Short observation labels only; no diagnosis or treatment recommendation."""

    niveau_focus: int | None = Field(default=None, ge=0, le=10)
    effets_physiques: str | None = Field(default=None, max_length=80)
    analyse_mecanique: str | None = Field(default=None, max_length=80)


class UserInput(BaseModel):
    chat_id: str | int
    message: str = Field(min_length=1, max_length=4096)


def _now() -> datetime:
    return datetime.now(PARIS)


def _chat_id(value: str | int) -> str:
    chat_id = str(value).strip()
    if not chat_id or len(chat_id) > 64:
        raise HTTPException(status_code=422, detail="Identifiant de conversation invalide")
    allowed = {part.strip() for part in os.getenv("TRACKER_ALLOWED_CHAT_IDS", "").split(",") if part.strip()}
    if allowed and chat_id not in allowed:
        raise HTTPException(status_code=403, detail="Conversation non autorisée")
    return chat_id


def _journal_failure(exc: Exception) -> HTTPException:
    logger.error("Tracker journal unavailable: %s", type(exc).__name__)
    return HTTPException(status_code=503, detail="Journal indisponible ; aucune donnée enregistrée")


def _state_failure(exc: Exception) -> HTTPException:
    logger.error("Tracker reminder state unavailable: %s", type(exc).__name__)
    return HTTPException(status_code=503, detail="État des rappels indisponible")


def _extract_labels(message: str) -> AnalyseClinique | None:
    key = os.getenv("TRACKER_API_KEY")
    model_name = os.getenv("TRACKER_MODEL")
    if not key or not model_name:
        logger.warning("Tracker automatic extraction unavailable: API configuration missing")
        return None
    try:
        options = {"model": model_name, "api_key": key, "temperature": 0}
        if os.getenv("TRACKER_LLM_BASE_URL"):
            options["base_url"] = os.environ["TRACKER_LLM_BASE_URL"]
        model = ChatOpenAI(**options).with_structured_output(AnalyseClinique)
        return model.invoke([
            SystemMessage(content=(
                "Extrais seulement les observations explicitement écrites dans ce journal personnel. "
                "N'invente aucune donnée, ne donne aucun diagnostic ni conseil de traitement. "
                "Focus est une note sur 10 ; les deux autres champs sont des étiquettes de 1 à 3 mots. "
                "Ne déduis pas l'heure de prise : elle est traitée séparément par une règle stricte."
            )),
            HumanMessage(content=f"Log : '{clean_text(message)}'"),
        ])
    except Exception as exc:
        # The message and provider response may contain private information.
        logger.warning("Tracker automatic extraction failed: %s", type(exc).__name__)
        return None


def _labels(analysis: AnalyseClinique | None) -> list[str]:
    if analysis is None:
        return []
    tags = []
    if analysis.niveau_focus is not None:
        tags.append(f"Focus:{analysis.niveau_focus}/10")
    if analysis.effets_physiques:
        tags.append(f"Phys:{analysis.effets_physiques}")
    if analysis.analyse_mecanique:
        tags.append(f"Méca:{analysis.analyse_mecanique}")
    return tags


@app.get("/health")
def health() -> dict[str, str]:
    if not JOURNAL_PATH.parent.is_dir() or not STATE_PATH.parent.is_dir():
        raise HTTPException(status_code=503, detail="Stockage Tracker indisponible")
    return {"status": "ok"}


@app.post("/webhook/telegram")
def recevoir_message_n8n(data: UserInput) -> dict[str, str]:
    chat_id = _chat_id(data.chat_id)
    message = data.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message vide")
    now = _now()
    command = message.casefold()
    try:
        if command == "/rappel_on":
            until = reminders.enable(chat_id, now)
            return {"reply": f"Rappels Telegram activés jusqu'au {until:%d/%m/%Y}. Maximum un par jour ; /rappel_off pour arrêter."}
        if command == "/rappel_off":
            reminders.disable(chat_id)
            return {"reply": "Rappels Telegram arrêtés."}
        if command == "/rappel_fait":
            reminders.acknowledge(chat_id, now)
            return {"reply": "Bien reçu. Pas d'autre rappel aujourd'hui."}
        if command == "/rappel_pause":
            reminders.snooze(chat_id, now)
            return {"reply": "Rappels reportés de 24 heures."}
        if command == "/rappel_statut":
            has_log = has_observation(JOURNAL_PATH, now.date().isoformat())
            decision = reminders.status(chat_id, now, has_log)
            return {"reply": f"Rappels : {decision.status}. {decision.reason}."}
        if message.upper() == "RESET":
            append_reset(JOURNAL_PATH, now)
            return {"reply": "Cycle remis à zéro dans le journal. À quelle heure as-tu pris la dose ?"}
    except JournalUnavailable as exc:
        raise _journal_failure(exc) from exc
    except (OSError, ValueError) as exc:
        raise _state_failure(exc) from exc

    analysis = _extract_labels(message)
    try:
        state = append_observation(JOURNAL_PATH, now, message, _labels(analysis))
    except JournalUnavailable as exc:
        raise _journal_failure(exc) from exc

    time_label = now.strftime("%Hh%M")
    if state == "T0 manquant":
        reply = f"Log enregistré à {time_label}. Heure de prise manquante : écris « pris à 08h30 » si tu veux le repère T+."
    elif state.startswith("Erreur Chrono"):
        reply = f"Log enregistré à {time_label}. Vérifie l'heure de prise indiquée."
    elif analysis is None:
        reply = f"Log enregistré à {time_label}. Analyse automatique indisponible ; le texte brut est conservé."
    elif not _labels(analysis):
        reply = f"Log enregistré à {time_label}. Précise ton état (focus ou ressenti) si tu le souhaites."
    else:
        reply = f"Log enregistré à {time_label}."
    return {"reply": reply}


@app.get("/webhook/telegram/etat/{chat_id}")
def verifier_etat_pour_appel(chat_id: str) -> dict:
    """Legacy read-only route; it can no longer authorize a Twilio call."""
    _chat_id(chat_id)
    try:
        t0 = read_t0(JOURNAL_PATH, _now().date().isoformat())
    except JournalUnavailable as exc:
        raise _journal_failure(exc) from exc
    return {
        "besoin_relance": False,
        "raison": "Ancien canal vocal désactivé ; utiliser la route Telegram dédiée.",
        "derniere_heure_prise": t0,
    }


@app.post("/rappels/claim/{chat_id}")
def claim_telegram_reminder(chat_id: str) -> dict:
    """Reserve at most one notification per day, then let n8n deliver it."""
    chat_id = _chat_id(chat_id)
    now = _now()
    try:
        has_log = has_observation(JOURNAL_PATH, now.date().isoformat())
        decision = reminders.claim(chat_id, now, has_log)
    except JournalUnavailable as exc:
        raise _journal_failure(exc) from exc
    except (OSError, ValueError) as exc:
        raise _state_failure(exc) from exc
    return {
        "besoin_relance": decision.allowed,
        "reminder_allowed": decision.allowed,
        "status": decision.status,
        "reason": decision.reason,
        "next_check_after": decision.next_check_after,
        "chat_id": chat_id,
        "reminder_text": "Petit rappel : pense à noter ton suivi du jour si tu le souhaites. /rappel_fait, /rappel_pause ou /rappel_off",
    }
