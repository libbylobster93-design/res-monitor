"""Telegram notification service via openclaw CLI or HTTP API."""

import subprocess
import httpx
from typing import Optional

TELEGRAM_CHAT_ID = "8773861980"
OPENCLAW_TOKEN = "6e0deaef33df03239e01107afa625f6c7bf830a28131cba3"
OPENCLAW_HTTP_URL = "http://localhost:18789/send"


def send_telegram(message: str) -> bool:
    """Send a Telegram message via openclaw CLI or HTTP fallback."""
    # Try CLI first
    try:
        result = subprocess.run(
            [
                "openclaw", "message", "send",
                "--channel", "telegram",
                "--target", TELEGRAM_CHAT_ID,
                "--message", message
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print(f"[Telegram] Sent via CLI: {message[:50]}...")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"[Telegram] CLI failed: {e}, trying HTTP...")

    # Fallback to HTTP
    try:
        resp = httpx.post(
            OPENCLAW_HTTP_URL,
            json={
                "channel": "telegram",
                "target": TELEGRAM_CHAT_ID,
                "message": message,
                "token": OPENCLAW_TOKEN
            },
            timeout=30
        )
        if resp.status_code == 200:
            print(f"[Telegram] Sent via HTTP: {message[:50]}...")
            return True
        else:
            print(f"[Telegram] HTTP failed with status {resp.status_code}")
    except Exception as e:
        print(f"[Telegram] HTTP failed: {e}")

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
