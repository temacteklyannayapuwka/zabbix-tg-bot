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
        except Exception:
            self.connection.close()
            raise

    def close(self):
        self.connection.close()

    def send_once(self, source: str, chat_id: str, event_id: str, send) -> bool:
        key = (source, chat_id, event_id)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            with closing(self.connection.execute(
                "SELECT 1 FROM deliveries WHERE source=? AND chat_id=? AND event_id=?", key
            )) as cursor:
                delivered = cursor.fetchone() is not None
            if delivered:
                self.connection.commit()
                return False
            send()
            self.connection.execute("INSERT INTO deliveries VALUES (?, ?, ?)", key)
            self.connection.commit()
            return True
        except BaseException:
            self.connection.rollback()
            raise
