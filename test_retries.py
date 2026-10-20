import io
import ssl
import unittest
from contextlib import redirect_stderr, redirect_stdout
from urllib.error import HTTPError, URLError
from unittest.mock import Mock, patch
from tempfile import TemporaryDirectory
from pathlib import Path

from errors import TemporaryFailure
from main import main, send_message
from polling import run_polling
from zabbix import get_api_version
from test_problem_delivery import ENV, PROBLEM
from test_recovery_delivery import RECOVERY


class RetryTests(unittest.TestCase):
    def test_retry_delays_and_limit(self):
        cycle = Mock(return_value=2)
        with patch("polling.time.sleep") as sleep, redirect_stderr(io.StringIO()):
            self.assertEqual(run_polling(cycle, 60), 2)
        self.assertEqual(cycle.call_count, 4)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [60, 120, 240])

    def test_delay_is_capped(self):
        with patch("polling.time.sleep") as sleep, redirect_stderr(io.StringIO()):
            self.assertEqual(run_polling(Mock(return_value=2), 86400), 2)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [300, 300, 300])

    def test_success_resets_consecutive_failures(self):
        cycle = Mock(side_effect=[2, 0, 2, 1])
        with patch("polling.time.sleep") as sleep, redirect_stderr(io.StringIO()):
            self.assertEqual(run_polling(cycle, 10), 1)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [10, 10, 10])

    def test_interrupt_during_backoff(self):
        with patch("polling.time.sleep", side_effect=KeyboardInterrupt), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.assertEqual(run_polling(Mock(return_value=2), 60), 0)

    def test_http_status_classification(self):
        for status in (400, 401, 403, 429, 500, 502, 503, 504):
            temporary = status in (500, 502, 503, 504)
            for target, invoke in (
                ("main.urlopen", lambda: send_message("fake-token", "1", "test")),
                ("zabbix.urlopen", lambda: get_api_version("https://example.com/api_jsonrpc.php")),
            ):
                with self.subTest(status=status, target=target), patch(target, side_effect=HTTPError("https://example.com", status, "private details", {}, None)):
                    with self.assertRaises(RuntimeError) as error:
                        invoke()
                    self.assertEqual(isinstance(error.exception, TemporaryFailure), temporary)
                    self.assertNotIn("private details", str(error.exception))

    def test_network_errors_are_temporary_but_certificate_failures_are_not(self):
        for failure in (TimeoutError(), URLError("offline"), URLError(ssl.SSLCertVerificationError("untrusted")), ssl.SSLCertVerificationError("untrusted")):
            temporary = not isinstance(failure, ssl.SSLCertVerificationError) and not isinstance(getattr(failure, "reason", None), ssl.SSLCertVerificationError)
            for target, invoke in (
                ("main.urlopen", lambda: send_message("fake", "1", "test")),
                ("zabbix.urlopen", lambda: get_api_version("https://example.com/api_jsonrpc.php")),
            ):
                with self.subTest(target=target, failure=type(failure)), patch(target, side_effect=failure):
                    with self.assertRaises(RuntimeError) as error:
                        invoke()
                    self.assertEqual(isinstance(error.exception, TemporaryFailure), temporary)

    def test_watch_recovers_after_temporary_api_failure(self):
        with patch("sys.argv", ["main.py", "--watch", "--dry-run"]), patch.dict("os.environ", ENV, clear=True), patch("main.get_problems", side_effect=[TemporaryFailure("offline"), []]) as fetch, patch("polling.time.sleep", side_effect=[None, KeyboardInterrupt]) as sleep, redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(sleep.call_count, 2)

    def test_one_shot_does_not_retry(self):
        with patch("sys.argv", ["main.py", "--list-problems"]), patch.dict("os.environ", ENV, clear=True), patch("main.get_problems", side_effect=TemporaryFailure("offline")) as fetch, patch("polling.time.sleep") as sleep, redirect_stderr(io.StringIO()):
            self.assertEqual(main(), 2)
        fetch.assert_called_once()
        sleep.assert_not_called()

    def test_recovery_retry_preserves_delivered_problem_history(self):
        with TemporaryDirectory() as directory:
            settings = {**ENV, "DELIVERY_HISTORY_PATH": str(Path(directory) / "history.sqlite3")}
            with patch("sys.argv", ["main.py", "--watch"]), patch.dict("os.environ", settings, clear=True), patch("main.get_problems", side_effect=[[PROBLEM], [], []]), patch("main.get_recoveries", side_effect=[[], [RECOVERY], [RECOVERY]]), patch("main.send_message", side_effect=[None, TemporaryFailure("offline"), None]) as send, patch("polling.time.sleep", side_effect=[None, None, KeyboardInterrupt]), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 0)
            self.assertEqual(send.call_count, 3)
            messages = [c.args[2] for c in send.call_args_list]
            self.assertIn("🔴 Problem", messages[0])
            self.assertIn("✅ Resolved", messages[1])
            self.assertEqual(messages[1], messages[2])


if __name__ == "__main__":
    unittest.main()
