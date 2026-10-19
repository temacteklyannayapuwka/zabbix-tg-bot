# zabbix-tg-bot

Python notification tool for forwarding Zabbix problems and recoveries to Telegram.

## Current features

- Formats problem and recovery notifications from a local JSON event file.
- Previews messages from local event files without network access or credentials.
- Previews Zabbix problems as notification text with UTC timestamps.
- Sends one test notification to a configured Telegram chat and exits.
- Sends current Zabbix problems to the configured Telegram chat in one run.
- Polls Zabbix continuously at a configurable interval.
- Remembers confirmed problem deliveries in SQLite and skips them on later send runs.
- Reads credentials from environment variables.
- Reports missing configuration, network failures and Telegram API errors.
- Lists up to 100 unresolved trigger problems with their hosts as JSON, newest event IDs first.
- Sends recovery notifications for tracked, previously delivered problems.
- Checks recovery references and recovery times for specified problem event IDs.
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

A successful run prints `Notification sent.` and delivers a test message.

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

To preview current Zabbix problems as notification text:

```bash
python3 main.py --list-problems --dry-run
```

This reads Zabbix through the API using the configured URL and token, but does not contact Telegram or require Telegram credentials. Each preview contains the event ID, problem name, severity, UTC time, and host display names (falling back to technical names). Problems without accessible hosts show `Unknown host`. An empty result prints `No unresolved problems.`. Messages longer than 4096 characters produce an error. Without `--dry-run`, `--list-problems` continues to print JSON.

To send the current problems to the configured Telegram chat once, load the Zabbix and Telegram credentials from `.env` and run:

```bash
python3 main.py --send-problems --dry-run
python3 main.py --send-problems
```

The dry run previews notification text and requires only Zabbix credentials. It does not open or change delivery history and shows all fetched problems, including previously sent ones. The send command validates Telegram configuration, fetches up to 100 problems, formats all messages, and sends only events without a recorded delivery. It exits after printing `Notifications sent: N.`; an empty current-problem result may still produce recovery notifications for tracked problems. On a delivery error it stops with a nonzero exit code and reports the number of confirmed sends in that run. Use manual runs with test events first.

Delivery history is stored in `delivery.sqlite3` beside `main.py` by default. Set `DELIVERY_HISTORY_PATH` in `.env` to use another persistent file; its parent directory must already exist and be writable. Keep custom history files outside Git. The default database and its journal files are ignored by Git. SQLite is included with Python, so no additional package is required.

Deliveries are keyed by Zabbix API URL, Telegram chat ID, and event ID. The database stores these identifiers and snapshots of delivered problems (name, severity, original time, and host data), but no bot or API tokens. Use a stable API URL and history path between runs. History applies to `--send-problems` and `--watch`, not local event sends or test messages. Preserve the database: losing it allows old problems to be sent again.

Each event is recorded immediately after a successful Telegram response. Earlier confirmed events remain recorded if a later send fails. A database lock prevents two processes using the same history file from sending the same event simultaneously; a busy or invalid database causes the command to stop without silently clearing history. A timeout, process crash, or database failure after Telegram accepts a message but before its delivery is saved can still cause a duplicate on the next run. A failed send is not retried automatically, and there is no exactly-once delivery guarantee.

To continuously poll Zabbix and send unseen current problems:

```bash
python3 -u main.py --watch
```

Set `POLL_INTERVAL_SECONDS` in `.env` to an integer from 5 to 86400 (default: 60). The first cycle runs immediately; the interval is measured after each completed cycle, so cycles do not overlap. SQLite history is reused on every cycle and after restarts. Existing unresolved problems without a recorded delivery are sent on the first cycle. Stop with Ctrl+C; the process exits with code 0 and closes database resources.

For continuous preview without Telegram credentials or history changes, use `python3 -u main.py --watch --dry-run`. Preview output includes all current problems on every cycle. Any API, formatting, configuration, delivery, or database error stops polling with a nonzero exit code; there is no automatic retry loop. This mode reads only the 100 newest unresolved problems per cycle: a short-lived problem that starts and resolves between cycles, or an older problem outside that limit, can be missed. Recoveries of tracked, delivered problems are checked separately even when the current-problem list is empty.

To check whether specific problem events have recovered:

```bash
python3 main.py --check-recovery 12345 12346
```

This requires `ZABBIX_API_URL`, `ZABBIX_API_TOKEN`, and permission to call `event.get`. Supply 1–100 positive problem event IDs. The command reads those original events, follows their `r_eventid` references, and returns JSON objects containing the original `eventid`, recovery `r_eventid`, and recovery Unix timestamp `r_clock`. It does not infer recovery from a problem disappearing from a list. Unresolved, deleted, inaccessible, or not-yet-visible events are omitted; `[]` means no recovery was confirmed, not that every requested event is still active. No Telegram messages are sent and delivery history is unchanged. This manual lookup is also used internally by `--send-problems` and `--watch` to confirm recoveries of tracked deliveries.

Automatic recovery delivery requires API permission for `event.get` in addition to `problem.get` and `trigger.get`. After problem delivery, each non-preview send cycle checks all tracked problems without a recorded recovery delivery in batches of up to 100 IDs. A confirmed recovery produces a `Resolved` message with the original host, problem, severity, event ID, occurrence time, and recovery time in UTC. `Notifications sent: N.` counts both problem and recovery messages in that cycle.

Recovery messages have separate delivery records and are skipped after successful delivery, including after restart. Failed deliveries remain pending. Problems missing from API responses are retained as pending and do not produce a false recovery. Event retention or lost API permissions can prevent recovery confirmation. Dry-run modes preview only current problem messages and do not read recovery history.

Existing history files are extended automatically with a snapshot table. Previously sent problems that are still fetched acquire a snapshot without being resent. Events already resolved before this upgrade and absent from the current-problem list have no snapshot and are not automatically tracked for recovery. Keep the database private because snapshots include infrastructure details. Existing crash-window duplicate limitations apply to recovery messages too.
