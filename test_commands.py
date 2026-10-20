import copy
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from commands import CommandListener, get_updates, parse_allowed_users
from errors import TemporaryFailure
from main import main


TOKEN = "123:fake_token"
UPDATE = {"update_id": 10, "message": {"from": {"id": 42, "is_bot": False}, "chat": {"id": 42, "type": "private"}, "text": "/start"}}


class CommandTests(unittest.TestCase):
    def test_allowlist_parsing(self):
        self.assertEqual(parse_allowed_users("42, 43,42"), {42, 43})
        for value in ("", "42,", "-42", "0", "name", "42.0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_allowed_users(value)

    def test_listener_rejects_missing_configuration(self):
        for token, users in (("", {42}), (TOKEN, set()), ("bad/token", {42})):
            with self.subTest(token=token), self.assertRaises(ValueError):
                CommandListener(token, users, Mock())

    def test_start_reply(self):
        send = Mock()
        CommandListener(TOKEN, {42}, send).handle(UPDATE)
        send.assert_called_once_with(TOKEN, "42", "Zabbix notification bot is running. Access granted.")

    def test_access_is_denied_by_default(self):
        changes = (
            ("from", {"id": 99, "is_bot": False}),
            ("from", {"id": 42, "is_bot": True}),
            ("from", {"id": "42", "is_bot": False}),
            ("chat", {"id": -100, "type": "group"}),
            ("chat", {"id": 99, "type": "private"}),
            ("chat", {"id": 42, "type": "supergroup"}),
            ("sender_chat", {"id": 42}),
        )
        for field, value in changes:
            send = Mock()
            update = copy.deepcopy(UPDATE)
            update["message"][field] = value
            CommandListener(TOKEN, {42}, send).handle(update)
            send.assert_not_called()

    def test_noncommands_and_other_updates_are_ignored(self):
        send = Mock()
        listener = CommandListener(TOKEN, {42}, send)
        for text in (None, "hello", "", "/unknown", "/start@other_bot", "/help@other_bot"):
            listener.handle({**UPDATE, "message": {**UPDATE["message"], "text": text}})
        for update in ({}, {"edited_message": UPDATE["message"]}, {"message": {}}, {"message": None}):
            listener.handle(update)
        send.assert_not_called()

    def test_help_lists_available_commands(self):
        send = Mock()
        listener = CommandListener(TOKEN, {42}, send)
        listener.handle({**UPDATE, "message": {**UPDATE["message"], "text": "/help"}})
        send.assert_called_once()
        token, chat, text = send.call_args.args
        self.assertEqual((token, chat), (TOKEN, "42"))
        self.assertIn("/start -", text)
        self.assertIn("/help -", text)
        self.assertNotIn("/ping", text)

    def test_help_is_not_available_to_other_users_or_groups(self):
        for sender, chat in (
            ({"id": 99, "is_bot": False}, {"id": 99, "type": "private"}),
            ({"id": 42, "is_bot": False}, {"id": -100, "type": "group"}),
        ):
            with self.subTest(chat=chat):
                send = Mock()
                listener = CommandListener(TOKEN, {42}, send)
                listener.handle({"message": {"from": sender, "chat": chat, "text": "/help"}})
                send.assert_not_called()

    def test_updates_request(self):
        body = {"ok": True, "result": [UPDATE]}
        with patch("commands.urlopen", return_value=io.BytesIO(json.dumps(body).encode())) as transport:
            self.assertEqual(get_updates(TOKEN, 10), [UPDATE])
        request = transport.call_args.args[0]
        self.assertEqual(json.loads(request.data), {"timeout": 25, "allowed_updates": ["message"], "offset": 10})
        self.assertEqual(transport.call_args.kwargs["timeout"], 35)

    def test_initial_request_omits_offset(self):
        with patch("commands.urlopen", return_value=io.BytesIO(b'{"ok":true,"result":[]}')) as transport:
            self.assertEqual(get_updates(TOKEN, None), [])
        self.assertNotIn("offset", json.loads(transport.call_args.args[0].data))

    def test_invalid_responses_are_rejected(self):
        for body in (b"bad", b"[]", b'{"ok":false,"description":"secret"}', b'{"ok":true,"result":[{}]}', b'{"ok":true,"result":[{"update_id":true}]}', b'{"ok":true,"result":[{"update_id":2},{"update_id":1}]}'):
            with self.subTest(body=body), patch("commands.urlopen", return_value=io.BytesIO(body)):
                with self.assertRaises(RuntimeError) as error:
                    get_updates(TOKEN, None)
                self.assertNotIn("secret", str(error.exception))

    def test_transport_errors_are_sanitized(self):
        for failure, temporary in ((URLError("secret"), True), (HTTPError("https://example.com", 503, "secret", {}, None), True), (HTTPError("https://example.com", 409, "secret", {}, None), False)):
            with self.subTest(temporary=temporary), patch("commands.urlopen", side_effect=failure):
                with self.assertRaises(RuntimeError) as error:
                    get_updates(TOKEN, None)
                self.assertEqual(isinstance(error.exception, TemporaryFailure), temporary)
                self.assertNotIn("secret", str(error.exception))

    def test_offset_advances_for_ignored_users_and_skips_duplicates(self):
        send = Mock()
        listener = CommandListener(TOKEN, {42}, send)
        denied = {**UPDATE, "update_id": 11, "message": {**UPDATE["message"], "from": {"id": 99, "is_bot": False}}}
        with patch("commands.get_updates", side_effect=[[UPDATE, denied], [UPDATE]]) as fetch:
            self.assertEqual(listener.poll(), 0)
            self.assertEqual(listener.offset, 12)
            self.assertEqual(listener.poll(), 0)
        self.assertEqual(fetch.call_args.args, (TOKEN, 12))
        send.assert_called_once()

    def test_failed_reply_remains_pending(self):
        listener = CommandListener(TOKEN, {42}, Mock(side_effect=TemporaryFailure("offline")))
        with patch("commands.get_updates", return_value=[UPDATE]), redirect_stderr(io.StringIO()):
            self.assertEqual(listener.poll(), 2)
        self.assertIsNone(listener.offset)

    def test_cli_bad_access_list_does_not_connect(self):
        with patch("sys.argv", ["main.py", "--listen"]), patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": TOKEN}, clear=True), patch("commands.get_updates") as fetch, redirect_stderr(io.StringIO()):
            self.assertEqual(main(), 1)
        fetch.assert_not_called()

    def test_cli_listener_does_not_read_zabbix(self):
        with patch("sys.argv", ["main.py", "--listen"]), patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_ALLOWED_USER_IDS": "42"}, clear=True), patch("commands.get_updates", side_effect=KeyboardInterrupt), patch("main.get_problems") as fetch, redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)
        fetch.assert_not_called()

    def test_cli_exclusive_flags(self):
        for flag in ("--watch", "--dry-run", "--send-problems"):
            with self.subTest(flag=flag), patch("sys.argv", ["main.py", "--listen", flag]), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
