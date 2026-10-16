import json
import subprocess
import sys
import unittest
from pathlib import Path

from notifications import format_notification


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.event = json.loads(Path("examples/problem.json").read_text())

    def test_problem_contains_event_details(self):
        text = format_notification(self.event)
        for value in ("🔴 Problem", "TEST-SERVER-01", "Low disk space", "High", "12345", self.event["occurred_at"]):
            self.assertIn(value, text)

    def test_recovery_retains_problem_identity(self):
        event = {**self.event, "status": "recovery", "recovered_at": "2026-10-16T15:48:00+03:00"}
        text = format_notification(event)
        for value in ("✅ Resolved", "Event: 12345", "Recovered: 2026-10-16T15:48:00+03:00"):
            self.assertIn(value, text)

    def test_invalid_recovery_times_are_rejected(self):
        for value in (None, "invalid", "2026-10-16T15:48:00", "2026-10-16T15:40:00+03:00"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    format_notification({**self.event, "status": "recovery", "recovered_at": value})

    def test_recovery_compares_timezones(self):
        text = format_notification({**self.event, "status": "recovery", "recovered_at": "2026-10-16T12:48:00+00:00"})
        self.assertIn("✅ Resolved", text)

    def test_invalid_fields_are_rejected(self):
        for field, value in (("status", "unknown"), ("host", ""), ("severity", 6), ("severity", True), ("occurred_at", "yesterday"), ("occurred_at", "2026-10-16T15:42:00")):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    format_notification({**self.event, field: value})

    def test_oversized_message_is_rejected(self):
        with self.assertRaises(ValueError):
            format_notification({**self.event, "name": "x" * 4096})

    def test_dry_run_without_secrets(self):
        result = subprocess.run(
            [sys.executable, "main.py", "--event", "examples/problem.json", "--dry-run"],
            capture_output=True, text=True, env={},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("TEST-SERVER-01", result.stdout)


if __name__ == "__main__":
    unittest.main()
