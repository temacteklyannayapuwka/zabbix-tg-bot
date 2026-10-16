import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
from urllib.error import HTTPError

from main import main
from zabbix import _NoRedirect, get_problems


API_URL = "https://zabbix.example.com/zabbix/api_jsonrpc.php"
TOKEN = "test-token"
PROBLEM = {
    "eventid": "12345", "objectid": "15112", "name": "Недостаточно места",
    "severity": "4", "clock": "1792154520",
}


class ProblemTests(unittest.TestCase):
    def test_problem_request_and_authentication(self):
        body = {"jsonrpc": "2.0", "result": [PROBLEM], "id": 1}
        with patch("zabbix.build_opener") as opener:
            opener.return_value.open.side_effect = [
                io.BytesIO(json.dumps(body).encode()),
                io.BytesIO(json.dumps({"jsonrpc": "2.0", "result": [], "id": 1}).encode()),
            ]
            self.assertEqual(get_problems(API_URL, TOKEN), [{**PROBLEM, "hosts": []}])
        self.assertIsInstance(opener.call_args.args[0], _NoRedirect)
        call = opener.return_value.open.call_args_list[0]
        request = call.args[0]
        self.assertEqual(request.full_url, API_URL)
        self.assertEqual(request.get_header("Authorization"), "Bearer " + TOKEN)
        self.assertEqual(call.kwargs, {"timeout": 15})
        payload = json.loads(request.data)
        self.assertEqual(payload["method"], "problem.get")
        self.assertEqual(payload["params"], {
            "output": ["eventid", "objectid", "name", "severity", "clock"],
            "source": 0, "object": 0, "recent": False,
            "sortfield": ["eventid"], "sortorder": "DESC", "limit": 100,
        })
        self.assertNotIn(TOKEN, request.data.decode())

    def test_empty_list(self):
        with patch("zabbix._api_request", return_value=[]):
            self.assertEqual(get_problems(API_URL, TOKEN), [])

    def test_missing_or_invalid_token_does_not_connect(self):
        with patch("zabbix._api_request") as request:
            for token in ("", "bad\nheader", " "):
                with self.subTest(token=token), self.assertRaises(ValueError):
                    get_problems(API_URL, token)
            request.assert_not_called()

    def test_invalid_problem_list(self):
        for result in (None, {}, [None], [{}], [{**PROBLEM, "severity": "6"}], [{**PROBLEM, "eventid": 123}], [{**PROBLEM, "clock": "yesterday"}]):
            with self.subTest(result=result), patch("zabbix._api_request", return_value=result):
                with self.assertRaises(RuntimeError):
                    get_problems(API_URL, TOKEN)

    def test_api_error_does_not_expose_details(self):
        body = {"jsonrpc": "2.0", "error": {"data": TOKEN}, "id": 1}
        with patch("zabbix.build_opener") as opener:
            opener.return_value.open.return_value = io.BytesIO(json.dumps(body).encode())
            with self.assertRaises(RuntimeError) as error:
                get_problems(API_URL, TOKEN)
        self.assertNotIn(TOKEN, str(error.exception))

    def test_redirect_is_rejected(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 307, "redirect", {}, "https://other.example"))
        with patch("zabbix.build_opener") as opener:
            opener.return_value.open.side_effect = HTTPError(API_URL, 302, TOKEN, {}, None)
            with self.assertRaises(RuntimeError) as error:
                get_problems(API_URL, TOKEN)
        self.assertEqual(str(error.exception), "Zabbix returned HTTP 302.")

    def test_cli_lists_without_sending(self):
        output = io.StringIO()
        with patch("sys.argv", ["main.py", "--list-problems"]), patch.dict("os.environ", {"ZABBIX_API_URL": API_URL, "ZABBIX_API_TOKEN": TOKEN}, clear=True), patch("main.get_problems", return_value=[PROBLEM]) as fetch, patch("main.send_message") as send, redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertEqual(json.loads(output.getvalue()), [PROBLEM])
        self.assertNotIn(TOKEN, output.getvalue())
        fetch.assert_called_once_with(API_URL, TOKEN)
        send.assert_not_called()

    def test_cli_error(self):
        output = io.StringIO()
        with patch("sys.argv", ["main.py", "--list-problems"]), patch.dict("os.environ", {}, clear=True), patch("zabbix.build_opener") as opener, redirect_stderr(output):
            self.assertEqual(main(), 1)
        opener.assert_not_called()
        self.assertIn("ZABBIX_API_TOKEN", output.getvalue())

    def test_cli_rejects_incompatible_options(self):
        for options in (["--dry-run"], ["--check-zabbix"], ["--event", "examples/problem.json"]):
            with self.subTest(options=options), patch("sys.argv", ["main.py", "--list-problems", *options]), patch("main.get_problems") as fetch, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)
                fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
