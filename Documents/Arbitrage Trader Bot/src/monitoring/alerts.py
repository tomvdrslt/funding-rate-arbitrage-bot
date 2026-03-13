"""Telegram alerts — no-op if not configured."""
import logging
import os
import requests

logger = logging.getLogger(__name__)

_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def send_alert(message: str) -> None:
    """Send a Telegram alert. No-op if token not set."""
    token = _BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = _CHAT_ID or os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.debug(f"Telegram not configured — skipping alert: {message}")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=5)
        resp.raise_for_status()
        logger.info(f"Telegram alert sent: {message[:80]}")
    except Exception as e:
        logger.warning(f"Failed to send Telegram alert: {e}")
