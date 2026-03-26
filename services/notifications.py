"""Telegram notification service — direct Bot API (Railway-compatible)."""

import httpx
from typing import Optional
import os

# Direct Bot API — works from Railway (no openclaw CLI or localhost needed)
TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN", "8536904842:AAGhsh3CJ7vHgG7nnABcQErbE6c7sDqgoX0"
)
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8773861980")


def send_telegram(message: str) -> bool:
    """Send a Telegram message directly via Bot API."""
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            print(f"[Telegram] Sent: {message[:60]}...")
            return True
        else:
            print(f"[Telegram] API error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[Telegram] Request failed: {e}")
    return False


def notify_slot_found(restaurant: str, date: str, time: str, party_size: int, platform: str) -> bool:
    """Notify when a slot is found."""
    message = (
        f"🍽️ SLOT FOUND!\n\n"
        f"Restaurant: {restaurant}\n"
        f"Date: {date}\n"
        f"Time: {time}\n"
        f"Party: {party_size}\n"
        f"Platform: {platform}"
    )
    return send_telegram(message)


def notify_booking_made(
    restaurant: str,
    date: str,
    time: str,
    party_size: int,
    confirmation: Optional[str] = None
) -> bool:
    """Notify when a booking is successfully made."""
    message = (
        f"✅ BOOKED!\n\n"
        f"Restaurant: {restaurant}\n"
        f"Date: {date}\n"
        f"Time: {time}\n"
        f"Party: {party_size}"
    )
    if confirmation:
        message += f"\nConfirmation: {confirmation}"
    return send_telegram(message)


def notify_cc_required(
    restaurant: str,
    date: str,
    time: str,
    party_size: int,
    url: Optional[str] = None
) -> bool:
    """Notify when a slot requires credit card — manual booking needed."""
    message = (
        f"💳 CC REQUIRED - Book manually!\n\n"
        f"Restaurant: {restaurant}\n"
        f"Date: {date}\n"
        f"Time: {time}\n"
        f"Party: {party_size}"
    )
    if url:
        message += f"\n\nBook here: {url}"
    return send_telegram(message)


def notify_error(restaurant: str, error: str) -> bool:
    """Notify when an error occurs during booking."""
    message = (
        f"❌ BOOKING ERROR\n\n"
        f"Restaurant: {restaurant}\n"
        f"Error: {error}"
    )
    return send_telegram(message)
