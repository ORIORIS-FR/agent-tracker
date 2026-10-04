import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from reminder_state import ReminderStore


PARIS = ZoneInfo("Europe/Paris")


class ReminderStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ReminderStore(Path(self.temp.name) / "state.sqlite3")
        self.now = datetime(2026, 10, 4, 10, 0, tzinfo=PARIS)

    def test_opt_in_one_per_day_and_expiry(self):
        self.assertFalse(self.store.claim("chat", self.now, False).allowed)
        self.store.enable("chat", self.now)
        self.assertTrue(self.store.claim("chat", self.now, False).allowed)
        self.assertFalse(self.store.claim("chat", self.now, False).allowed)
        self.assertFalse(self.store.claim("chat", self.now + timedelta(days=8), False).allowed)

    def test_log_ack_snooze_and_stop_block_reminders(self):
        self.store.enable("chat", self.now)
        self.assertEqual(self.store.claim("chat", self.now, True).status, "completed")
        self.store.acknowledge("chat", self.now)
        self.assertEqual(self.store.claim("chat", self.now, False).status, "acknowledged")
        tomorrow = self.now + timedelta(days=1)
        self.store.snooze("chat", tomorrow)
        self.assertEqual(self.store.claim("chat", tomorrow, False).status, "snoozed")
        self.store.disable("chat")
        self.assertEqual(self.store.claim("chat", tomorrow + timedelta(days=2), False).status, "disabled")

    def test_new_chat_revokes_previous_recipient(self):
        self.store.enable("old", self.now)
        self.store.enable("new", self.now)
        self.assertFalse(self.store.claim("old", self.now, False).allowed)
        self.assertTrue(self.store.claim("new", self.now, False).allowed)

    def test_no_reminder_during_quiet_hours(self):
        self.store.enable("chat", self.now)
        early = self.now.replace(hour=7)
        self.assertEqual(self.store.claim("chat", early, False).status, "snoozed")


if __name__ == "__main__":
    unittest.main()
