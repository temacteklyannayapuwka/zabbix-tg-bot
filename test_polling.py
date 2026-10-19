import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from main import main
from polling import run_polling
from test_problem_delivery import ENV, PROBLEM


class PollingTests(unittest.TestCase):
    def test_cycles_run_then_wait(self):
        operations = Mock()
        operations.cycle.side_effect = [0, 0]
        operations.sleep.side_effect = [None, KeyboardInterrupt]
        with patch("polling.time.sleep", operations.sleep), redirect_stdout(io.StringIO()):
            self.assertEqual(run_polling(operations.cycle, 12), 0)
        self.assertEqual([c[0] for c in operations.mock_calls], ["cycle", "sleep", "cycle", "sleep"])
        operations.sleep.assert_called_with(12)

    def test_failed_cycle_stops_without_wait(self):
        cycle = Mock(return_value=1)
        with patch("polling.time.sleep") as sleep:
            self.assertEqual(run_polling(cycle, 60), 1)
        cycle.assert_called_once()
        sleep.assert_not_called()

    def test_interrupt_during_cycle(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(run_polling(Mock(side_effect=KeyboardInterrupt), 60), 0)

    def test_watch_reuses_history_across_cycles(self):
        with TemporaryDirectory() as directory:
            settings = {**ENV, "DELIVERY_HISTORY_PATH": str(Path(directory) / "history.sqlite3"), "POLL_INTERVAL_SECONDS": "10"}
            with patch("sys.argv", ["main.py", "--watch"]), patch.dict("os.environ", settings, clear=True), patch("main.get_problems", return_value=[PROBLEM]) as fetch, patch("main.send_message") as send, patch("polling.time.sleep", side_effect=[None, KeyboardInterrupt]) as sleep, redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 0)
            self.assertEqual(fetch.call_count, 2)
            send.assert_called_once()
            sleep.assert_called_with(10)

    def test_watch_preview_never_sends_or_creates_history(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            settings = {"ZABBIX_API_URL": ENV["ZABBIX_API_URL"], "ZABBIX_API_TOKEN": ENV["ZABBIX_API_TOKEN"], "DELIVERY_HISTORY_PATH": str(path)}
            with patch("sys.argv", ["main.py", "--watch", "--dry-run"]), patch.dict("os.environ", settings, clear=True), patch("main.get_problems", return_value=[PROBLEM]), patch("main.send_message") as send, patch("polling.time.sleep", side_effect=KeyboardInterrupt) as sleep, redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 0)
            send.assert_not_called()
            sleep.assert_called_once_with(60)
            self.assertFalse(path.exists())

    def test_bad_interval_prevents_network_access(self):
        for value in ("", "0", "4", "86401", "nan", "10.5"):
            with self.subTest(value=value), patch("sys.argv", ["main.py", "--watch"]), patch.dict("os.environ", {"POLL_INTERVAL_SECONDS": value}, clear=True), patch("main.get_problems") as fetch, patch("main.send_message") as send, redirect_stderr(io.StringIO()):
                self.assertEqual(main(), 1)
                fetch.assert_not_called()
                send.assert_not_called()

    def test_watch_error_exits_without_wait(self):
        with patch("sys.argv", ["main.py", "--watch"]), patch.dict("os.environ", ENV, clear=True), patch("main.get_problems", side_effect=RuntimeError("offline")), patch("polling.time.sleep") as sleep, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(), 1)
        sleep.assert_not_called()

    def test_watch_is_exclusive(self):
        for option in ("--send-problems", "--list-problems", "--check-zabbix"):
            with self.subTest(option=option), patch("sys.argv", ["main.py", "--watch", option]), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
