import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from notifications import format_notification
from zabbix import get_api_version, get_problems


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
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--event", help="Path to a JSON event file")
    actions.add_argument("--check-zabbix", action="store_true", help="Check Zabbix API version")
    actions.add_argument("--list-problems", action="store_true", help="Print up to 100 unresolved Zabbix problems as JSON")
    parser.add_argument("--dry-run", action="store_true", help="Print without sending")
    args = parser.parse_args()
    if args.check_zabbix:
        if args.dry_run:
            parser.error("--check-zabbix cannot be combined with --dry-run")
        try:
            version = get_api_version(os.environ.get("ZABBIX_API_URL", "").strip())
        except (ValueError, RuntimeError) as error:
            print(str(error), file=sys.stderr)
            return 1
        print(f"Zabbix API version: {version}")
        return 0
    if args.list_problems:
        if args.dry_run:
            parser.error("--list-problems cannot be combined with --dry-run")
        try:
            problems = get_problems(
                os.environ.get("ZABBIX_API_URL", "").strip(),
                os.environ.get("ZABBIX_API_TOKEN", "").strip(),
            )
        except (ValueError, RuntimeError) as error:
            print(str(error), file=sys.stderr)
            return 1
        print(json.dumps(problems, ensure_ascii=False, indent=2))
        return 0
    text = "Zabbix Telegram bot: test notification."
    if args.event:
        try:
            with open(args.event, encoding="utf-8") as source:
                event = json.load(source)
            if not isinstance(event, dict):
                raise ValueError("Event must be a JSON object.")
            text = format_notification(event)
        except (OSError, ValueError) as error:
            print(f"Could not load event: {error}", file=sys.stderr)
            return 1
    if args.dry_run:
        print(text)
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.", file=sys.stderr)
        return 1

    try:
        send_message(token, chat_id, text)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1

    print("Notification sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
