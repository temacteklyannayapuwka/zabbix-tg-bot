# zabbix-tg-bot

Python notification tool for forwarding Zabbix problems and recoveries to Telegram.

## Current features

- Formats problem and recovery notifications from a local JSON event file.
- Supports previewing messages without network access or credentials.
- Sends one test notification to a configured Telegram chat and exits.
- Reads credentials from environment variables.
- Reports missing configuration, network failures and Telegram API errors.
- Lists up to 100 unresolved trigger problems with their hosts as JSON, newest event IDs first.
- Checks Zabbix API connectivity and prints its version without authentication.

## Run on Linux

Requires Python 3.10 or newer. No third-party packages are required.

```bash
git clone https://github.com/temacteklyannayapuwka/zabbix-tg-bot.git
cd zabbix-tg-bot
cp .env.example .env
chmod 600 .env
```

Create a bot using [@BotFather](https://t.me/BotFather), open your new bot and press Start. Set its token and the target numeric chat ID in `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

To find your private chat ID, send a message to your bot and use Telegram's [getUpdates](https://core.telegram.org/bots/api#getupdates) method locally. The ID is in `result[].message.chat.id`. Keep the token private.

Load the configuration and run:

```bash
set -a
source .env
set +a
python3 main.py
```

Only source your own trusted configuration file. The `.env` file is excluded from Git.

A successful run prints `Notification sent.` and delivers a test message. Continuous polling and automatic forwarding of Zabbix events are not implemented.

To preview a local test event without sending it:

```bash
python3 main.py --event examples/problem.json --dry-run
python3 main.py --event examples/recovery.json --dry-run
```

To send it to the configured chat, omit `--dry-run`.

Run checks with `python3 -m unittest discover -v`.

To check Zabbix API connectivity, set `ZABBIX_API_URL` in `.env` to the full API endpoint, for example `https://zabbix.example.com/zabbix/api_jsonrpc.php`. Reload the environment as shown above, then run:

```bash
python3 main.py --check-zabbix
```

This calls the read-only `apiinfo.version` method and prints `Zabbix API version: 7.0.3` for that version. It does not require Telegram credentials or a Zabbix API token, send Telegram messages, or change Zabbix configuration. HTTPS certificates are verified; use a trusted certificate for your server.

To list unresolved problems, set `ZABBIX_API_TOKEN` in your local `.env` to an existing API token with permission to call `problem.get` and `trigger.get` and read the required hosts. Reload the environment, then run:

```bash
python3 main.py --list-problems
```

The command makes a read-only problem request followed by one batched trigger request when problems exist and prints a JSON array containing event IDs, trigger IDs (`objectid`), names, severity values (0–5), and Unix timestamps (`clock`). It prints `[]` when no problems are visible to that token. The output is limited to the 100 newest unresolved trigger problems and includes a `hosts` array with host IDs, technical names (`host`), and display names (`name`). Missing or inaccessible triggers have an empty `hosts` array; their problems remain in the output. This command does not send Telegram messages or change Zabbix. Use HTTPS to protect the API token in transit. Tokens are sent in the Authorization header and are never printed by the application.
