import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def send_message(token: str, chat_id: str, text: str) -> None:
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(
            f"Telegram returned HTTP {error.code}. Check the token, chat ID and bot permissions."
        ) from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError("Could not connect to Telegram. Check the network connection.") from None
    except (ValueError, UnicodeError):
        raise RuntimeError("Telegram returned an invalid response.") from None

    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError("Telegram did not confirm message delivery.")


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.", file=sys.stderr)
        return 1

    try:
        send_message(token, chat_id, "Zabbix Telegram bot: test notification.")
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1

    print("Test notification sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
