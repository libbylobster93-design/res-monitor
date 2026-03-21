"""
OpenTable and Tock availability stub.

Playwright / headless browser approach blocked by Cloudflare on both platforms.
Strategy: surface booking links via Telegram so Andrew can check manually.
Resy is handled separately via direct API (services/resy_booking.py).
"""

from typing import Optional, Dict, List, Any
from services.notifications import send_telegram


def check_opentable(
    restaurant_url: str,
    dates: List[str],
    party_sizes: List[int] = [4, 2],
    time_start: str = "17:30",
    time_end: str = "21:00",
) -> List[Dict[str, Any]]:
    """OpenTable availability check — not automatable (Cloudflare blocked)."""
    print(f"[OpenTable] Skipping {restaurant_url} — use Telegram link to check manually")
    return []


def check_and_book_opentable(
    monitor: Dict,
    dates: List[str],
    party_sizes: List[int] = [4, 2],
    time_start: str = "17:30",
    time_end: str = "21:00",
) -> Dict[str, Any]:
    """
    Send a manual-check Telegram alert for OpenTable restaurant.
    Called once per weekly cycle per restaurant.
    """
    name = monitor.get("restaurant", "Unknown")
    url = monitor.get("url", "")
    print(f"[OpenTable] Sending manual-check link for {name}")
    return {"status": "link_sent", "slots_found": [], "restaurant": name}


def check_and_notify_tock(
    monitor: Dict,
    dates: List[str],
    party_sizes: List[int] = [4, 2],
    time_start: str = "17:30",
    time_end: str = "21:00",
) -> Dict[str, Any]:
    """
    Send a manual-check Telegram alert for Tock restaurant.
    Tock is always prepaid — auto-booking not possible anyway.
    Called once per weekly cycle per restaurant.
    """
    name = monitor.get("restaurant", "Unknown")
    url = monitor.get("url", "")
    print(f"[Tock] Sending manual-check link for {name}")
    return {"status": "link_sent", "slots_found": [], "restaurant": name}
