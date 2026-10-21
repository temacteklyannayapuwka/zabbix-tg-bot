import io
import json
import socket
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from main import main


class EndToEndTests(unittest.TestCase):
    def test_api_problem_recovery_and_deduplication(self):
        current_reads = 0
        messages = []
        problem = {"eventid": "10", "objectid": "100", "name": "Low disk space", "severity": "4", "clock": "100"}

        def zabbix_response(request, timeout):
            nonlocal current_reads
            self.assertEqual(timeout, 15)
            self.assertEqual(request.get_header("Authorization"), "Bearer fake-api-token")
            payload = json.loads(request.data)
            method, params = payload["method"], payload["params"]
            if method == "problem.get":
                current_reads += 1
                result = [problem] if current_reads == 1 else []
            elif method == "trigger.get":
                result = [{"triggerid": "100", "hosts": [{"hostid": "1", "host": "sql-01", "name": "SQL Server"}]}]
            elif method == "event.get" and params["value"] == 1:
                result = [{"eventid": "10", "clock": "100", "value": "1", "r_eventid": "0" if current_reads == 1 else "20"}]
            elif method == "event.get" and params["value"] == 0:
                self.assertEqual(params["eventids"], ["20"])
                result = [{"eventid": "20", "clock": "200", "value": "0"}]
            else:
                self.fail(f"Unexpected API method: {method}")
            return io.BytesIO(json.dumps({"jsonrpc": "2.0", "result": result, "id": 1}).encode())

        def telegram_response(request, timeout):
            self.assertEqual(timeout, 15)
            self.assertTrue(request.full_url.endswith("/sendMessage"))
            payload = json.loads(request.data)
            self.assertEqual(payload["chat_id"], "42")
            messages.append(payload["text"])
            return io.BytesIO(b'{"ok":true,"result":{"message_id":1}}')

        with TemporaryDirectory() as directory:
            settings = {
                "ZABBIX_API_URL": "https://zabbix.example.com/api_jsonrpc.php",
                "ZABBIX_API_TOKEN": "fake-api-token",
                "TELEGRAM_BOT_TOKEN": "123:fake_token",
                "TELEGRAM_CHAT_ID": "42",
                "DELIVERY_HISTORY_PATH": str(Path(directory) / "history.sqlite3"),
            }
            with patch("sys.argv", ["main.py", "--watch"]), patch.dict("os.environ", settings, clear=True), patch("zabbix.build_opener") as opener, patch("main.urlopen", side_effect=telegram_response), patch("polling.time.sleep", side_effect=[None, None, KeyboardInterrupt]), patch.object(socket, "socket", side_effect=AssertionError("Real network access is forbidden in this test")), redirect_stdout(io.StringIO()):
                opener.return_value.open.side_effect = zabbix_response
                self.assertEqual(main(), 0)
            self.assertEqual(current_reads, 3)
            self.assertEqual(len(messages), 2)
            self.assertIn("🔴 Problem", messages[0])
            self.assertIn("✅ Resolved", messages[1])
            for text in messages:
                self.assertIn("SQL Server", text)
                self.assertIn("Low disk space", text)
                self.assertIn("Event: 10", text)
            self.assertIn("Recovered: 1970-01-01T00:03:20+00:00", messages[1])

    def test_version_without_credentials(self):
        output = io.StringIO()
        with patch("sys.argv", ["main.py", "--version"]), patch.dict("os.environ", {}, clear=True), redirect_stdout(output):
            with self.assertRaises(SystemExit) as result:
                main()
        self.assertEqual(result.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), "1.0.0")


if __name__ == "__main__":
    unittest.main()
