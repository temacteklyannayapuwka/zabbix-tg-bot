import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from history import DeliveryHistory


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / "history.sqlite3")

    def test_history_survives_reopening(self):
        send = Mock()
        with closing(DeliveryHistory(self.path)) as history:
            self.assertTrue(history.send_once("source", "chat", "1", send))
        with closing(DeliveryHistory(self.path)) as history:
            self.assertFalse(history.send_once("source", "chat", "1", send))
            self.assertTrue(history.send_once("source", "chat", "2", send))
        self.assertEqual(send.call_count, 2)

    def test_source_and_destination_have_separate_history(self):
        send = Mock()
        with closing(DeliveryHistory(self.path)) as history:
            for source, chat in (("a", "1"), ("a", "2"), ("b", "1")):
                self.assertTrue(history.send_once(source, chat, "100", send))
        self.assertEqual(send.call_count, 3)

    def test_failed_send_can_be_retried(self):
        with closing(DeliveryHistory(self.path)) as history:
            with self.assertRaises(RuntimeError):
                history.send_once("a", "1", "100", Mock(side_effect=RuntimeError("offline")))
            self.assertTrue(history.send_once("a", "1", "100", Mock()))

    def test_corrupted_history_is_not_reset(self):
        path = Path(__file__).with_name("examples") / "problem.json"
        contents = path.read_bytes()
        from shutil import copyfile
        copyfile(path, self.path)
        with self.assertRaises(sqlite3.Error):
            DeliveryHistory(self.path)
        self.assertEqual(Path(self.path).read_bytes(), contents)

    def test_two_connections_share_committed_history(self):
        send = Mock()
        with closing(DeliveryHistory(self.path)) as first, closing(DeliveryHistory(self.path)) as second:
            self.assertTrue(first.send_once("a", "1", "100", send))
            self.assertFalse(second.send_once("a", "1", "100", send))
        send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
