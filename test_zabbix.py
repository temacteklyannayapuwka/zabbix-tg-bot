import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from main import main
from zabbix import get_api_version


API_URL = "https://zabbix.example.com/zabbix/api_jsonrpc.php"


class ZabbixTests(unittest.TestCase):
    def test_version_request(self):
        body = {"jsonrpc": "2.0", "result": "7.0.3", "id": 1}
        with patch("zabbix.urlopen", return_value=io.BytesIO(json.dumps(body).encode())) as transport:
            self.assertEqual(get_api_version(API_URL), "7.0.3")
        request = transport.call_args.args[0]
        self.assertEqual(request.full_url, API_URL)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(request.data), {
            "jsonrpc": "2.0", "method": "apiinfo.version", "params": [], "id": 1,
        })
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(transport.call_args.kwargs["timeout"], 15)

    def test_invalid_urls_do_not_connect(self):
        with patch("zabbix.urlopen") as transport:
            for url in ("", "file:///api_jsonrpc.php", "https://example.com", "https://user:secret@example.com/api_jsonrpc.php", API_URL + "?token=secret", API_URL + "#fragment", "https://example.com:bad/api_jsonrpc.php"):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    get_api_version(url)
            transport.assert_not_called()

    def test_transport_errors(self):
        for error in (HTTPError(API_URL, 403, "Forbidden", {}, None), URLError("offline"), TimeoutError()):
            with self.subTest(error=type(error)), patch("zabbix.urlopen", side_effect=error):
                with self.assertRaises(RuntimeError):
                    get_api_version(API_URL)

    def test_invalid_response(self):
        for body in (b"<html>Login</html>", b"\xff", b"[]", b"null", b"{}"):
            with self.subTest(body=body), patch("zabbix.urlopen", return_value=io.BytesIO(body)):
                with self.assertRaises(RuntimeError):
                    get_api_version(API_URL)

    def test_invalid_envelopes(self):
        base = {"jsonrpc": "2.0", "result": "7.0.3", "id": 1}
        for change in ({"id": 2}, {"id": True}, {"jsonrpc": "1.0"}, {"result": None}, {"result": ""}, {"result": "not a version"}, {"error": {"data": "private server details"}}):
            body = json.dumps({**base, **change}).encode()
            with self.subTest(change=change), patch("zabbix.urlopen", return_value=io.BytesIO(body)):
                with self.assertRaises(RuntimeError) as error:
                    get_api_version(API_URL)
                self.assertNotIn("private server details", str(error.exception))

    def test_check_cli_without_telegram_credentials(self):
        output = io.StringIO()
        with patch("sys.argv", ["main.py", "--check-zabbix"]), patch.dict("os.environ", {"ZABBIX_API_URL": API_URL}, clear=True), patch("main.get_api_version", return_value="7.0.3") as check, patch("main.send_message") as send, redirect_stdout(output):
            self.assertEqual(main(), 0)
        check.assert_called_once_with(API_URL)
        send.assert_not_called()
        self.assertEqual(output.getvalue(), "Zabbix API version: 7.0.3\n")

    def test_check_cli_missing_url(self):
        with patch("sys.argv", ["main.py", "--check-zabbix"]), patch.dict("os.environ", {}, clear=True), patch("zabbix.urlopen") as transport, redirect_stderr(io.StringIO()):
            self.assertEqual(main(), 1)
        transport.assert_not_called()

    def test_check_cli_network_error(self):
        with patch("sys.argv", ["main.py", "--check-zabbix"]), patch("main.get_api_version", side_effect=RuntimeError("offline")), patch("main.send_message") as send, redirect_stderr(io.StringIO()):
            self.assertEqual(main(), 1)
        send.assert_not_called()

    def test_incompatible_cli_options(self):
        for options in (["--check-zabbix", "--dry-run"], ["--check-zabbix", "--event", "examples/problem.json"]):
            with self.subTest(options=options), patch("sys.argv", ["main.py", *options]), patch("main.get_api_version") as check, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)
                check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
