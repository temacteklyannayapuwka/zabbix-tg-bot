import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from history import DeliveryHistory
from main import main
from notifications import format_zabbix_recovery
from test_problem_delivery import ENV, PROBLEM


RECOVERY = {"eventid": "12345", "r_eventid": "20000", "r_clock": "120"}


class RecoveryDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / "history.sqlite3")

    def run_cycle(self, problems, recoveries, send_error=None, options=None):
        output, errors = io.StringIO(), io.StringIO()
        with patch("sys.argv", ["main.py", "--send-problems", *(options or [])]), patch.dict("os.environ", {**ENV, "DELIVERY_HISTORY_PATH": self.path}, clear=True), patch("main.get_problems", return_value=problems), patch("main.get_recoveries", return_value=recoveries) as lookup, patch("main.send_message", side_effect=send_error) as send, redirect_stdout(output), redirect_stderr(errors):
            status = main()
        return status, lookup, send, errors.getvalue()

    def test_problem_then_recovery_survives_restarts(self):
        self.assertEqual(self.run_cycle([PROBLEM], [])[0], 0)
        status, lookup, send, error = self.run_cycle([], [RECOVERY])
        self.assertEqual(status, 0, error)
        lookup.assert_called_once_with(ENV["ZABBIX_API_URL"], ENV["ZABBIX_API_TOKEN"], ["12345"])
        send.assert_called_once_with(ENV["TELEGRAM_BOT_TOKEN"], ENV["TELEGRAM_CHAT_ID"], format_zabbix_recovery(PROBLEM, RECOVERY))
        status, lookup, send, error = self.run_cycle([], [])
        self.assertEqual(status, 0, error)
        lookup.assert_not_called()
        send.assert_not_called()

    def test_disappearance_alone_does_not_send_recovery(self):
        self.run_cycle([PROBLEM], [])
        status, _, send, error = self.run_cycle([], [])
        self.assertEqual(status, 0, error)
        send.assert_not_called()

    def test_failed_recovery_can_be_retried(self):
        self.run_cycle([PROBLEM], [])
        self.assertEqual(self.run_cycle([], [RECOVERY], send_error=RuntimeError("offline"))[0], 1)
        status, _, send, error = self.run_cycle([], [RECOVERY])
        self.assertEqual(status, 0, error)
        send.assert_called_once()

    def test_dry_run_does_not_lookup_or_mark_recoveries(self):
        self.run_cycle([PROBLEM], [])
        status, lookup, send, error = self.run_cycle([], [RECOVERY], options=["--dry-run"])
        self.assertEqual(status, 0, error)
        lookup.assert_not_called()
        send.assert_not_called()
        self.assertEqual(self.run_cycle([], [RECOVERY])[2].call_count, 1)

    def test_existing_delivery_is_backfilled_without_resending(self):
        history = DeliveryHistory(self.path)
        try:
            history.send_once(ENV["ZABBIX_API_URL"], ENV["TELEGRAM_CHAT_ID"], PROBLEM["eventid"], lambda: None)
        finally:
            history.close()
        status, _, send, error = self.run_cycle([PROBLEM], [])
        self.assertEqual(status, 0, error)
        send.assert_not_called()
        self.assertEqual(self.run_cycle([], [RECOVERY])[2].call_count, 1)

    def test_recovery_lookup_is_batched(self):
        problems = [{**PROBLEM, "eventid": str(i)} for i in range(1, 102)]
        self.assertEqual(self.run_cycle(problems, [])[0], 0)
        status, lookup, send, error = self.run_cycle([], [])
        self.assertEqual(status, 0, error)
        self.assertEqual([len(c.args[2]) for c in lookup.call_args_list], [100, 1])
        send.assert_not_called()

    def test_recovery_format_keeps_original_details(self):
        text = format_zabbix_recovery(PROBLEM, RECOVERY)
        for value in ("✅ Resolved", "SQL Server", "Low disk space", "High", "1970-01-01T00:02:00+00:00", "Event: 12345"):
            self.assertIn(value, text)
        for change in ({"eventid": "other"}, {"r_clock": "bad"}, {"r_clock": "9" * 100}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                format_zabbix_recovery(PROBLEM, {**RECOVERY, **change})

    def test_recovery_for_other_event_is_rejected(self):
        self.run_cycle([PROBLEM], [])
        status, _, send, _ = self.run_cycle([], [{**RECOVERY, "eventid": "999"}])
        self.assertEqual(status, 1)
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
