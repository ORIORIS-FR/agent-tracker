import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo


HAS_API = importlib.util.find_spec("fastapi") is not None and importlib.util.find_spec("langchain_openai") is not None
if HAS_API:
    from fastapi.testclient import TestClient
    import agent_tracker
    from reminder_state import ReminderStore


@unittest.skipUnless(HAS_API, "API dependencies are installed in the Tracker image")
class TrackerApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.client = TestClient(agent_tracker.app)
        self.now = datetime(2026, 10, 4, 10, 0, tzinfo=ZoneInfo("Europe/Paris"))
        self.patches = [
            patch.object(agent_tracker, "JOURNAL_PATH", root / "journal.md"),
            patch.object(agent_tracker, "STATE_PATH", root / "state.sqlite3"),
            patch.object(agent_tracker, "reminders", ReminderStore(root / "state.sqlite3")),
            patch.object(agent_tracker, "_now", return_value=self.now),
            patch.object(agent_tracker, "_extract_labels", return_value=None),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_logging_and_telegram_reminder_lifecycle(self):
        self.assertEqual(self.client.post("/webhook/telegram", json={"chat_id": "42", "message": "/rappel_on"}).status_code, 200)
        first = self.client.post("/rappels/claim/42").json()
        self.assertTrue(first["reminder_allowed"])
        self.assertEqual(first["chat_id"], "42")
        self.assertFalse(self.client.post("/rappels/claim/42").json()["reminder_allowed"])
        logged = self.client.post("/webhook/telegram", json={"chat_id": "42", "message": "pris à 08h30, focus 6/10"})
        self.assertEqual(logged.status_code, 200)
        self.assertIn("Log enregistré", logged.json()["reply"])
        self.assertEqual(self.client.post("/rappels/claim/42").json()["status"], "completed")
        self.assertEqual(self.client.get("/webhook/telegram/etat/42").json()["besoin_relance"], False)
        self.assertEqual(self.client.post("/webhook/telegram", json={"chat_id": "42", "message": "/rappel_off"}).status_code, 200)

    def test_failed_write_returns_503(self):
        with patch.object(agent_tracker, "JOURNAL_PATH", Path(self.temp.name) / "missing" / "journal.md"):
            response = self.client.post("/webhook/telegram", json={"chat_id": "42", "message": "focus 6/10"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("aucune donnée enregistrée", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
