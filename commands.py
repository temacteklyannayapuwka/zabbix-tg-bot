import json
import re
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from errors import TemporaryFailure


def parse_allowed_users(value: str) -> set[int]:
    parts = value.split(",")
    if any(not re.fullmatch(r"[1-9][0-9]*", part.strip()) for part in parts):
        raise ValueError("Set TELEGRAM_ALLOWED_USER_IDS to comma-separated positive numeric user IDs.")
    return {int(part.strip()) for part in parts}


def get_updates(token: str, offset: int | None) -> list[dict]:
    payload = {"timeout": 25, "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset
    request = Request(
        f"https://api.telegram.org/bot{token}/getUpdates",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urlopen(request, timeout=35) as response:
            result = json.load(response)
    except HTTPError as error:
        if error.code in (500, 502, 503, 504):
            raise TemporaryFailure(f"Telegram updates returned HTTP {error.code}.") from None
        raise RuntimeError(f"Telegram updates returned HTTP {error.code}.") from None
    except ssl.SSLCertVerificationError:
        raise RuntimeError("Telegram TLS certificate verification failed.") from None
    except URLError as error:
        if isinstance(error.reason, ssl.SSLCertVerificationError):
            raise RuntimeError("Telegram TLS certificate verification failed.") from None
        raise TemporaryFailure("Could not receive Telegram updates.") from None
    except (TimeoutError, OSError):
        raise TemporaryFailure("Could not receive Telegram updates.") from None
    except (ValueError, UnicodeError):
        raise RuntimeError("Telegram updates returned invalid JSON.") from None
    if not isinstance(result, dict) or result.get("ok") is not True or not isinstance(result.get("result"), list):
        raise RuntimeError("Telegram returned invalid updates.")
    previous = -1
    for update in result["result"]:
        if not isinstance(update, dict) or type(update.get("update_id")) is not int or update["update_id"] <= previous:
            raise RuntimeError("Telegram returned invalid update IDs.")
        previous = update["update_id"]
    return result["result"]


class CommandListener:
    def __init__(self, token: str, allowed_users: set[int], send):
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
            raise ValueError("Set TELEGRAM_BOT_TOKEN to a valid bot token.")
        if not allowed_users:
            raise ValueError("At least one Telegram user must be allowed.")
        self.token = token
        self.allowed_users = allowed_users
        self.send = send
        self.offset = None

    def poll(self) -> int:
        try:
            for update in get_updates(self.token, self.offset):
                if self.offset is not None and update["update_id"] < self.offset:
                    continue
                self.handle(update)
                self.offset = update["update_id"] + 1
        except RuntimeError as error:
            print(str(error), file=sys.stderr)
            return 2 if isinstance(error, TemporaryFailure) else 1
        return 0

    def handle(self, update: dict):
        message = update.get("message")
        if not isinstance(message, dict):
            return
        sender, chat = message.get("from"), message.get("chat")
        if not isinstance(sender, dict) or not isinstance(chat, dict):
            return
        user_id, chat_id = sender.get("id"), chat.get("id")
        if (
            type(user_id) is not int or type(chat_id) is not int
            or user_id not in self.allowed_users or chat_id != user_id
            or chat.get("type") != "private" or sender.get("is_bot") is not False
            or message.get("sender_chat") is not None
        ):
            return
        text = message.get("text")
        if isinstance(text, str) and text.split() and text.split()[0] == "/start":
            self.send(self.token, str(chat_id), "Zabbix notification bot is running. Access granted.")
