import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import call, patch

from main import main
from notifications import format_zabbix_problem


PROBLEM = {
    "eventid": "12345", "name": "Low disk space", "severity": "4", "clock": "0",
    "hosts": [{"host": "sql-01", "name": "SQL Server"}],
}
ENV = {
    "ZABBIX_API_URL": "https://example.com/api_jsonrpc.php",
    "ZABBIX_API_TOKEN": "zabbix-test-token",
    "TELEGRAM_BOT_TOKEN": "telegram-test-token",
    "TELEGRAM_CHAT_ID": "123",
}


class ProblemDeliveryTests(unittest.TestCase):
    def run_delivery(self, problems, env=None, options=None, send_error=None, fetch_error=None):
        output, errors = io.StringIO(), io.StringIO()
        with patch("sys.argv", ["main.py", "--send-problems", *(options or [])]), patch.dict("os.environ", ENV if env is None else env, clear=True), patch("main.get_problems", return_value=problems, side_effect=fetch_error) as fetch, patch("main.send_message", side_effect=send_error) as send, redirect_stdout(output), redirect_stderr(errors):
            status = main()
        return status, output.getvalue(), errors.getvalue(), fetch, send

    def test_sends_formatted_messages_in_order(self):
        problems = [PROBLEM, {**PROBLEM, "eventid": "12344"}]
        status, output, errors, fetch, send = self.run_delivery(problems)
        self.assertEqual(status, 0, errors)
        self.assertEqual(output, "Notifications sent: 2.\n")
        fetch.assert_called_once_with(ENV["ZABBIX_API_URL"], ENV["ZABBIX_API_TOKEN"])
        self.assertEqual(send.call_args_list, [call(ENV["TELEGRAM_BOT_TOKEN"], "123", format_zabbix_problem(p)) for p in problems])
        self.assertNotIn("test-token", output + errors)

    def test_empty_result_sends_nothing(self):
        status, output, errors, _, send = self.run_delivery([])
        self.assertEqual(status, 0, errors)
        self.assertEqual(output, "Notifications sent: 0.\n")
        send.assert_not_called()

    def test_missing_credentials_skip_all_network_calls(self):
        for field in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            with self.subTest(field=field):
                status, _, errors, fetch, send = self.run_delivery([PROBLEM], env={**ENV, field: ""})
                self.assertEqual(status, 1)
                self.assertIn("TELEGRAM", errors)
                fetch.assert_not_called()
                send.assert_not_called()

    def test_dry_run_needs_no_telegram_credentials(self):
        env = {key: value for key, value in ENV.items() if key.startswith("ZABBIX")}
        status, output, errors, _, send = self.run_delivery([PROBLEM], env=env, options=["--dry-run"])
        self.assertEqual(status, 0, errors)
        self.assertIn("Host: SQL Server", output)
        send.assert_not_called()

    def test_all_messages_are_validated_before_sending(self):
        status, output, errors, _, send = self.run_delivery([PROBLEM, {**PROBLEM, "name": "x" * 4096}])
        self.assertEqual(status, 1)
        self.assertEqual(output, "")
        self.assertIn("4096", errors)
        send.assert_not_called()

    def test_api_failure_sends_nothing(self):
        status, _, errors, _, send = self.run_delivery([], fetch_error=RuntimeError("API unavailable"))
        self.assertEqual(status, 1)
        self.assertIn("API unavailable", errors)
        send.assert_not_called()

    def test_delivery_failure_stops_without_retry(self):
        problems = [PROBLEM, {**PROBLEM, "eventid": "12344"}, {**PROBLEM, "eventid": "12343"}]
        status, output, errors, _, send = self.run_delivery(problems, send_error=[None, RuntimeError("Telegram unavailable")])
        self.assertEqual(status, 1)
        self.assertEqual(output, "")
        self.assertEqual(send.call_count, 2)
        self.assertIn("after 1 confirmed notification(s)", errors)
        self.assertIn("Telegram unavailable", errors)

    def test_send_action_is_exclusive(self):
        for options in (["--list-problems"], ["--check-zabbix"], ["--event", "examples/problem.json"]):
            with self.subTest(options=options), patch("sys.argv", ["main.py", "--send-problems", *options]), patch("main.get_problems") as fetch, patch("main.send_message") as send, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)
                fetch.assert_not_called()
                send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
