import json
import sqlite3
from contextlib import closing


class DeliveryHistory:
    def __init__(self, path: str):
        self.connection = sqlite3.connect(path, timeout=5, isolation_level=None)
        try:
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS deliveries ("
                "source TEXT NOT NULL, chat_id TEXT NOT NULL, event_id TEXT NOT NULL, "
                "PRIMARY KEY (source, chat_id, event_id))"
            )
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS problem_snapshots ("
                "source TEXT NOT NULL, chat_id TEXT NOT NULL, event_id TEXT NOT NULL, "
                "problem TEXT NOT NULL, PRIMARY KEY (source, chat_id, event_id))"
            )
        except Exception:
            self.connection.close()
            raise

    def close(self):
        self.connection.close()

    def pending_problems(self, source: str, chat_id: str) -> list[dict]:
        with closing(self.connection.execute(
            "SELECT p.problem FROM problem_snapshots p "
            "WHERE p.source=? AND p.chat_id=? AND NOT EXISTS ("
            "SELECT 1 FROM deliveries d WHERE d.source=p.source AND d.chat_id=p.chat_id "
            "AND d.event_id='recovery:' || p.event_id) ORDER BY p.event_id",
            (source, chat_id),
        )) as cursor:
            return [json.loads(row[0]) for row in cursor]

    def send_once(self, source: str, chat_id: str, event_id: str, send, problem=None) -> bool:
        key = (source, chat_id, event_id)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            with closing(self.connection.execute(
                "SELECT 1 FROM deliveries WHERE source=? AND chat_id=? AND event_id=?", key
            )) as cursor:
                delivered = cursor.fetchone() is not None
            if delivered:
                if problem is not None:
                    self._save_problem(key, problem)
                self.connection.commit()
                return False
            send()
            self.connection.execute("INSERT INTO deliveries VALUES (?, ?, ?)", key)
            if problem is not None:
                self._save_problem(key, problem)
            self.connection.commit()
            return True
        except BaseException:
            self.connection.rollback()
            raise

    def _save_problem(self, key, problem):
        snapshot = {field: problem[field] for field in ("eventid", "name", "severity", "clock", "hosts")}
        self.connection.execute(
            "INSERT OR IGNORE INTO problem_snapshots VALUES (?, ?, ?, ?)",
            (*key, json.dumps(snapshot, ensure_ascii=False)),
        )
