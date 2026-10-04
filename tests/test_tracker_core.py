import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tracker_core import (
    JournalUnavailable,
    append_observation,
    append_reset,
    explicit_t0,
    read_t0,
)


PARIS = ZoneInfo("Europe/Paris")


class TrackerCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "journal.md"

    def test_only_explicit_valid_dose_time_sets_t0(self):
        self.assertEqual(explicit_t0("Médicament pris à 8h30"), "08h30")
        self.assertEqual(explicit_t0("prise à 09:05"), "09h05")
        self.assertIsNone(explicit_t0("RDV à 9h30, fatigue à 12h00"))
        self.assertIsNone(explicit_t0("pris à 25h00"))

    def test_cycle_reset_blocks_previous_t0(self):
        morning = datetime(2026, 10, 4, 8, 30, tzinfo=PARIS)
        append_observation(self.path, morning, "Pris à 8h00", [])
        self.assertEqual(read_t0(self.path, "2026-10-04"), "08h00")
        append_reset(self.path, datetime(2026, 10, 4, 12, 0, tzinfo=PARIS))
        self.assertIsNone(read_t0(self.path, "2026-10-04"))
        append_observation(self.path, datetime(2026, 10, 4, 13, 0, tzinfo=PARIS), "Focus 6/10", [])
        self.assertIsNone(read_t0(self.path, "2026-10-04"))

    def test_new_day_and_message_text_do_not_rearm_old_t0(self):
        append_observation(
            self.path, datetime(2026, 10, 4, 8, 30, tzinfo=PARIS), "pris à 8h00", []
        )
        state = append_observation(
            self.path,
            datetime(2026, 10, 5, 9, 0, tzinfo=PARIS),
            "Je cite CYCLE RESET et le 2026-10-05 dans mon texte",
            [],
        )
        self.assertEqual(state, "T0 manquant")
        self.assertIsNone(read_t0(self.path, "2026-10-05"))

    def test_write_failure_never_reports_success(self):
        missing = Path(self.temp.name) / "absent" / "journal.md"
        with self.assertRaises(JournalUnavailable):
            append_observation(
                missing, datetime(2026, 10, 4, 8, 30, tzinfo=PARIS), "pris à 8h00", []
            )

    def test_message_stays_in_one_table_cell(self):
        append_observation(
            self.path, datetime(2026, 10, 4, 9, 0, tzinfo=PARIS), "focus | calme\nrepos", []
        )
        line = self.path.read_text(encoding="utf-8").strip()
        self.assertIn("focus / calme repos", line)
        self.assertEqual(line.count("|"), 5)


if __name__ == "__main__":
    unittest.main()
