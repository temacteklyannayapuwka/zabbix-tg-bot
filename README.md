# zabbix-tg-bot

Python notification tool for forwarding Zabbix problems and recoveries to Telegram.

## Current features

- Sends one test notification to a configured Telegram chat and exits.
- Reads credentials from environment variables.
- Reports missing configuration, network failures and Telegram API errors.

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

A successful run prints `Test notification sent.` and delivers a test message. Zabbix connectivity is not implemented.
