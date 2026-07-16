"""Telegram delivery for the signal bot.

Push-only: sends alert text to a chat via the Telegram Bot API. No command
handling, no exchange access — this module cannot place orders.

Setup:
1. Create a bot with @BotFather on Telegram, get the bot token.
2. Message the bot once, then GET https://api.telegram.org/bot<token>/getUpdates
   to find your chat id.
3. Put both in .env (see .env.example) — never commit real values.
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set -- copy .env.example to .env "
            "and fill in your bot token and chat id (see notify/telegram_bot.py's module docstring for how to get them)."
        )
    response = requests.post(
        TELEGRAM_API_URL.format(token=token),
        data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )
    response.raise_for_status()
