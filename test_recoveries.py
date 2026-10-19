import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from main import main
from zabbix import get_recoveries


URL = "https://example.com/api_jsonrpc.php"
TOKEN = "test-token"
PROBLEM = {"eventid": "10", "r_eventid": "20", "clock": "100", "value": "1"}
RECOVERY = {"eventid": "20", "clock": "200", "value": "0"}
EXPECTED = {"eventid": "10", "r_eventid": "20", "r_clock": "200"}


class RecoveryTests(unittest.TestCase):
    def test_follows_recovery_reference(self):
        with patch("zabbix._api_request", side_effect=[[PROBLEM], [RECOVERY]]) as request:
            self.assertEqual(get_recoveries(URL, TOKEN, ["10", "10"]), [EXPECTED])
        self.assertEqual(request.call_args_list[0].args, (URL, "event.get", {
            "eventids": ["10"], "source": 0, "object": 0, "value": 1,
            "output": ["eventid", "r_eventid", "clock", "value"],
        }, TOKEN))
        self.assertEqual(request.call_args_list[1].args, (URL, "event.get", {
            "eventids": ["20"], "source": 0, "object": 0, "value": 0,
            "output": ["eventid", "clock", "value"],
        }, TOKEN))

    def test_missing_or_unresolved_event_is_not_recovery(self):
        for events in ([], [{**PROBLEM, "r_eventid": "0"}]):
            with self.subTest(events=events), patch("zabbix._api_request", return_value=events) as request:
                self.assertEqual(get_recoveries(URL, TOKEN, ["10"]), [])
                self.assertEqual(request.call_count, 1)

    def test_missing_recovery_is_not_confirmed(self):
        with patch("zabbix._api_request", side_effect=[[PROBLEM], []]):
            self.assertEqual(get_recoveries(URL, TOKEN, ["10"]), [])

    def test_results_follow_requested_problem_order(self):
        other = {**PROBLEM, "eventid": "11"}
        with patch("zabbix._api_request", side_effect=[[other, PROBLEM], [RECOVERY]]):
            result = get_recoveries(URL, TOKEN, ["10", "11"])
        self.assertEqual([p["eventid"] for p in result], ["10", "11"])

    def test_bad_arguments_do_not_connect(self):
        for ids in ([], ["0"], ["bad"], ["-1"], [1], ["1"] * 101):
            with self.subTest(ids=ids), patch("zabbix._api_request") as request:
                with self.assertRaises(ValueError):
                    get_recoveries(URL, TOKEN, ids)
                request.assert_not_called()
        with patch("zabbix._api_request") as request:
            with self.assertRaises(ValueError):
                get_recoveries(URL, "", ["10"])
            request.assert_not_called()

    def test_malformed_problem_events_fail(self):
        for events in ({}, [None], [{}], [{**PROBLEM, "r_eventid": None}], [{**PROBLEM, "clock": "bad"}], [{**PROBLEM, "value": "0"}], [{**PROBLEM, "eventid": "999"}], [PROBLEM, PROBLEM]):
            with self.subTest(events=events), patch("zabbix._api_request", return_value=events):
                with self.assertRaises(RuntimeError):
                    get_recoveries(URL, TOKEN, ["10"])

    def test_invalid_recovery_events_fail(self):
        for events in ([{**RECOVERY, "clock": "99"}], [{**RECOVERY, "value": "1"}], [{**RECOVERY, "eventid": "999"}], [RECOVERY, RECOVERY]):
            with self.subTest(events=events), patch("zabbix._api_request", side_effect=[[PROBLEM], events]):
                with self.assertRaises(RuntimeError):
                    get_recoveries(URL, TOKEN, ["10"])

    def test_api_failure_is_not_treated_as_empty_result(self):
        with patch("zabbix._api_request", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                get_recoveries(URL, TOKEN, ["10"])

    def test_cli_reads_without_telegram_or_history(self):
        output = io.StringIO()
        with patch("sys.argv", ["main.py", "--check-recovery", "10"]), patch.dict("os.environ", {"ZABBIX_API_URL": URL, "ZABBIX_API_TOKEN": TOKEN}, clear=True), patch("main.get_recoveries", return_value=[EXPECTED]) as fetch, patch("main.send_message") as send, patch("main.DeliveryHistory") as history, redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertEqual(json.loads(output.getvalue()), [EXPECTED])
        fetch.assert_called_once_with(URL, TOKEN, ["10"])
        send.assert_not_called()
        history.assert_not_called()

    def test_cli_api_error(self):
        with patch("sys.argv", ["main.py", "--check-recovery", "10"]), patch("main.get_recoveries", side_effect=RuntimeError("offline")), redirect_stderr(io.StringIO()):
            self.assertEqual(main(), 1)

    def test_cli_rejects_incompatible_options(self):
        for options in (["--dry-run"], ["--watch"], ["--send-problems"]):
            with self.subTest(options=options), patch("sys.argv", ["main.py", "--check-recovery", "10", *options]), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
