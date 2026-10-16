import unittest
from unittest.mock import patch

from zabbix import get_problems
from test_problems import API_URL, TOKEN, PROBLEM


HOST = {"hostid": "10084", "host": "sql-01", "name": "SQL Server"}
TRIGGER = {"triggerid": "15112", "hosts": [HOST]}


class ProblemHostTests(unittest.TestCase):
    def test_batched_lookup_preserves_order_and_shared_trigger(self):
        problems = [PROBLEM, {**PROBLEM, "eventid": "12344"}, {**PROBLEM, "eventid": "12343", "objectid": "15113"}]
        second_host = {"hostid": "10085", "host": "app-01", "name": "Application"}
        triggers = [{"triggerid": "15113", "hosts": [second_host]}, TRIGGER]
        with patch("zabbix._api_request", side_effect=[problems, triggers]) as request:
            result = get_problems(API_URL, TOKEN)
        self.assertEqual([p["eventid"] for p in result], ["12345", "12344", "12343"])
        self.assertEqual([p["hosts"] for p in result], [[HOST], [HOST], [second_host]])
        self.assertNotIn("hosts", PROBLEM)
        self.assertEqual(request.call_count, 2)
        request.assert_called_with(API_URL, "trigger.get", {
            "triggerids": ["15112", "15113"], "output": ["triggerid"],
            "selectHosts": ["hostid", "host", "name"],
        }, TOKEN)

    def test_multiple_hosts_are_preserved(self):
        other = {"hostid": "10085", "host": "app-01", "name": ""}
        with patch("zabbix._api_request", side_effect=[[PROBLEM], [{**TRIGGER, "hosts": [HOST, other]}]]):
            self.assertEqual(get_problems(API_URL, TOKEN)[0]["hosts"], [HOST, other])

    def test_missing_trigger_keeps_problem(self):
        with patch("zabbix._api_request", side_effect=[[PROBLEM], []]):
            self.assertEqual(get_problems(API_URL, TOKEN), [{**PROBLEM, "hosts": []}])

    def test_empty_problems_skip_trigger_lookup(self):
        with patch("zabbix._api_request", return_value=[]) as request:
            self.assertEqual(get_problems(API_URL, TOKEN), [])
        self.assertEqual(request.call_count, 1)

    def test_invalid_trigger_results_fail(self):
        results = (None, {}, [None], [{}], [{**TRIGGER, "triggerid": "999"}], [TRIGGER, TRIGGER], [{**TRIGGER, "hosts": None}], [{**TRIGGER, "hosts": [None]}], [{**TRIGGER, "hosts": [{**HOST, "hostid": "invalid"}]}], [{**TRIGGER, "hosts": [{**HOST, "host": ""}]}], [{**TRIGGER, "hosts": [{**HOST, "name": None}]}])
        for triggers in results:
            with self.subTest(triggers=triggers), patch("zabbix._api_request", side_effect=[[PROBLEM], triggers]):
                with self.assertRaises(RuntimeError):
                    get_problems(API_URL, TOKEN)

    def test_trigger_request_failure_is_not_silenced(self):
        with patch("zabbix._api_request", side_effect=[[PROBLEM], RuntimeError("API permission denied")]):
            with self.assertRaisesRegex(RuntimeError, "API permission denied"):
                get_problems(API_URL, TOKEN)


if __name__ == "__main__":
    unittest.main()
