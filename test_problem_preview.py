import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from main import main
from notifications import format_zabbix_problem


PROBLEM = {
    "eventid": "12345", "name": "Low disk space", "severity": "4", "clock": "0",
    "hosts": [{"hostid": "10084", "host": "sql-01", "name": "SQL Server"}],
}


class ProblemPreviewTests(unittest.TestCase):
    def test_problem_conversion(self):
        text = format_zabbix_problem(PROBLEM)
        for value in ("🔴 Problem", "Host: SQL Server", "Low disk space", "Severity: High", "Occurred: 1970-01-01T00:00:00+00:00", "Event: 12345"):
            self.assertIn(value, text)

    def test_multiple_hosts_and_technical_name_fallback(self):
        hosts = [*PROBLEM["hosts"], {"host": "app-01", "name": " "}, *PROBLEM["hosts"]]
        self.assertIn("Host: SQL Server, app-01\n", format_zabbix_problem({**PROBLEM, "hosts": hosts}))

    def test_unknown_host(self):
        self.assertIn("Host: Unknown host\n", format_zabbix_problem({**PROBLEM, "hosts": []}))

    def test_bad_problem_fields(self):
        for change in ({"clock": "yesterday"}, {"clock": "9" * 100}, {"severity": "6"}, {"severity": True}, {"eventid": None}, {"hosts": None}, {"hosts": [None]}, {"hosts": [{"host": "", "name": ""}]}, {"name": ""}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                format_zabbix_problem({**PROBLEM, **change})

    def test_oversized_preview(self):
        with self.assertRaisesRegex(ValueError, "4096"):
            format_zabbix_problem({**PROBLEM, "name": "x" * 4096})

    def run_preview(self, problems):
        output = io.StringIO()
        errors = io.StringIO()
        with patch("sys.argv", ["main.py", "--list-problems", "--dry-run"]), patch.dict("os.environ", {"ZABBIX_API_URL": "https://example.com/api_jsonrpc.php", "ZABBIX_API_TOKEN": "test-token"}, clear=True), patch("main.get_problems", return_value=problems) as fetch, patch("main.send_message") as send, redirect_stdout(output), redirect_stderr(errors):
            result = main()
        fetch.assert_called_once()
        send.assert_not_called()
        return result, output.getvalue(), errors.getvalue()

    def test_cli_preview_without_telegram_credentials(self):
        result, output, errors = self.run_preview([PROBLEM])
        self.assertEqual(result, 0, errors)
        self.assertIn("Host: SQL Server", output)
        self.assertNotIn("test-token", output)

    def test_cli_empty_preview(self):
        result, output, errors = self.run_preview([])
        self.assertEqual(result, 0, errors)
        self.assertEqual(output, "No unresolved problems.\n")

    def test_cli_invalid_problem_has_no_partial_output(self):
        result, output, errors = self.run_preview([PROBLEM, {**PROBLEM, "clock": "bad"}])
        self.assertEqual(result, 1)
        self.assertEqual(output, "")
        self.assertIn("clock", errors)


if __name__ == "__main__":
    unittest.main()
