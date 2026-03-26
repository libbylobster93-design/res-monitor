"""Resy authentication and booking service."""

import os
import time
from datetime import datetime
from typing import Optional, Dict, List, Any

import httpx

RESY_API_KEY = "VbWk7s3L4KiK5fzlO7JD3Q5EYolJI7n5"
RESY_EMAIL = "andrewren3@gmail.com"
RESY_USER_ID = 1773145

BASE_HEADERS = {
    "Authorization": f'ResyAPI api_key="{RESY_API_KEY}"',
    "Origin": "https://resy.com",
    "X-Origin": "https://resy.com",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
}


def auth() -> Optional[str]:
    """
    Return Resy auth token from environment variable.
    Token is extracted from browser session (RESY_AUTH_TOKEN env var).
    Resy uses phone/magic-link auth — no password-based login.
    """
    token = os.environ.get("RESY_AUTH_TOKEN")
    if token:
        print("[Resy] Using RESY_AUTH_TOKEN from environment")
        return token
    print("[Resy] RESY_AUTH_TOKEN env var not set")
    return None

    return None


def find_slots(
    venue_id: int,
    date: str,
    party_size: int,
    lat: float = 37.7749,
    lng: float = -122.4194,
) -> List[Dict[str, Any]]:
    """
    Find available slots for a venue.
    GET https://api.resy.com/4/find
    Returns list of slot dicts with config_id, time, etc.
    """
    try:
        token = os.environ.get("RESY_AUTH_TOKEN", "")
        headers = {**BASE_HEADERS}
        if token:
            headers["x-resy-auth-token"] = token
            headers["x-resy-universal-auth"] = token
        resp = httpx.get(
            "https://api.resy.com/4/find",
            params={
                "lat": lat,
                "long": lng,
                "day": date,
                "party_size": party_size,
                "venue_id": venue_id,
            },
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[Resy] Find failed with status {resp.status_code}")
            return []

        data = resp.json()
        venues = data.get("results", {}).get("venues", [])
        slots = []
        for venue in venues:
            for slot in venue.get("slots", []):
                config = slot.get("config", {})
                date_info = slot.get("date", {})
                # token field: try both "token" and "id"
                config_id = config.get("token") or config.get("id") or config.get("config_id")
                if not config_id:
                    print(f"[Resy] Slot config keys: {list(config.keys())}")
                slots.append({
                    "config_id": config_id,
                    "time": date_info.get("start"),
                    "date": date,
                    "type": config.get("type"),
                    "raw": slot,
                })
        return slots
    except Exception as e:
        print(f"[Resy] Find request failed: {e}")
        return []


def get_details(config_id: str, party_size: int, token: str) -> Optional[Dict[str, Any]]:
    """
    Get slot details including payment requirements.
    POST https://api.resy.com/3/details
    Returns details dict with payment_method_required flag.
    """
    headers = {**BASE_HEADERS, "X-Resy-Auth-Token": token}
    try:
        resp = httpx.post(
            "https://api.resy.com/3/details",
            headers=headers,
            data={
                "config_id": config_id,
                "party_size": party_size,
                "day": datetime.now().strftime("%Y-%m-%d"),
            },
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[Resy] Details failed with status {resp.status_code}")
            return None

        data = resp.json()
        # Check if payment method is required
        payment = data.get("user", {}).get("payment_methods", [])
        book_token = data.get("book_token", {}).get("value")
        requires_payment = data.get("payment", {}).get("deposit_required", False)

        return {
            "book_token": book_token,
            "requires_payment": requires_payment,
            "payment_methods": payment,
            "raw": data,
        }
    except Exception as e:
        print(f"[Resy] Details request failed: {e}")
        return None


def book(book_token: str, token: str) -> Optional[Dict[str, Any]]:
    """
    Complete the booking.
    POST https://api.resy.com/3/book
    Returns confirmation details.
    """
    headers = {**BASE_HEADERS, "X-Resy-Auth-Token": token}
    try:
        resp = httpx.post(
            "https://api.resy.com/3/book",
            headers=headers,
            data={
                "book_token": book_token,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            resy_token = data.get("resy_token")
            print(f"[Resy] Booking successful! Confirmation: {resy_token}")
            return {
                "confirmation": resy_token,
                "raw": data,
            }
        else:
            print(f"[Resy] Book failed with status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[Resy] Book request failed: {e}")

    return None


def check_and_book(
    monitor: Dict[str, Any],
    dates: List[str],
    party_sizes: List[int] = [4, 2],
    time_start: str = "17:30",
    time_end: str = "21:00",
) -> Dict[str, Any]:
    """
    Full flow: authenticate, find slots, check CC requirement, book if possible.

    Args:
        monitor: Monitor dict from database
        dates: List of dates to check (YYYY-MM-DD)
        party_sizes: Party sizes to try in order (default [4, 2])
        time_start: Earliest acceptable time (HH:MM)
        time_end: Latest acceptable time (HH:MM)

    Returns:
        Dict with status, slot info, and booking result
    """
    from services.notifications import notify_booking_made, notify_cc_required, notify_slot_found
    from database import get_db

    result = {
        "status": "no_slots",
        "restaurant": monitor.get("restaurant"),
        "slots_found": [],
        "booking": None,
        "error": None,
    }

    venue_id = monitor.get("venue_id")
    if not venue_id:
        result["status"] = "error"
        result["error"] = "No venue_id configured"
        return result

    try:
        venue_id = int(venue_id)
    except ValueError:
        result["status"] = "error"
        result["error"] = f"Invalid venue_id: {venue_id}"
        return result

    # Authenticate
    token = auth()
    if not token:
        result["status"] = "error"
        result["error"] = "Authentication failed"
        return result

    # Search for slots
    for party_size in party_sizes:
        for date in dates:
            print(f"[Resy] Checking {monitor['restaurant']} for {date}, party of {party_size}")
            slots = find_slots(venue_id, date, party_size)

            # Filter by time window
            for slot in slots:
                slot_time = slot.get("time", "")
                if not slot_time:
                    continue

                # Extract time portion (format: "2026-03-21 19:00:00")
                try:
                    time_part = slot_time.split(" ")[1][:5] if " " in slot_time else slot_time[:5]
                except (IndexError, TypeError):
                    continue

                if time_start <= time_part <= time_end:
                    result["slots_found"].append({
                        "date": date,
                        "time": time_part,
                        "party_size": party_size,
                        "config_id": slot.get("config_id"),
                    })

            time.sleep(1)  # Rate limiting

        if result["slots_found"]:
            break  # Found slots for this party size, don't try smaller

    if not result["slots_found"]:
        result["status"] = "no_slots"
        return result

    # Try to book the first available slot
    slot = result["slots_found"][0]
    config_id = slot.get("config_id")

    if not config_id:
        # config_id (token) missing from slot — still alert Andrew since we have real availability
        result["status"] = "available"
        result["error"] = "No config_id in slot — manual booking needed"
        notify_slot_found(
            monitor["restaurant"],
            slot["date"],
            slot["time"],
            slot["party_size"],
            "Resy",
        )
        return result

    # Get details and check payment requirement
    details = get_details(config_id, slot["party_size"], token)
    if not details:
        # Details API failed (token expired or Resy API issue).
        # We still have real slots — alert Andrew to book manually.
        result["status"] = "available"
        result["error"] = "Details API unavailable — manual booking needed"
        notify_slot_found(
            monitor["restaurant"],
            slot["date"],
            slot["time"],
            slot["party_size"],
            "Resy",
        )
        conn = get_db()
        conn.execute(
            """INSERT INTO booking_attempts
               (monitor_id, restaurant_name, platform, slot_date, slot_time, party_size, status, notified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (monitor.get("id"), monitor["restaurant"], "Resy", slot["date"], slot["time"],
             slot["party_size"], "alert_only", True)
        )
        conn.commit()
        conn.close()
        return result

    # Log booking attempt
    conn = get_db()

    if details.get("requires_payment"):
        # CC required - notify but don't book
        result["status"] = "cc_required"
        notify_cc_required(
            monitor["restaurant"],
            slot["date"],
            slot["time"],
            slot["party_size"],
            monitor.get("url")
        )
        conn.execute(
            """INSERT INTO booking_attempts
               (monitor_id, restaurant_name, platform, slot_date, slot_time, party_size, status, requires_cc, notified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (monitor.get("id"), monitor["restaurant"], "Resy", slot["date"], slot["time"],
             slot["party_size"], "cc_required", True, True)
        )
        conn.commit()
        conn.close()
        return result

    # No CC required - proceed with booking
    book_token = details.get("book_token")
    if not book_token:
        result["status"] = "error"
        result["error"] = "No book_token in details"
        conn.execute(
            """INSERT INTO booking_attempts
               (monitor_id, restaurant_name, platform, slot_date, slot_time, party_size, status, requires_cc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (monitor.get("id"), monitor["restaurant"], "Resy", slot["date"], slot["time"],
             slot["party_size"], "failed", False)
        )
        conn.commit()
        conn.close()
        return result

    booking = book(book_token, token)
    if booking:
        result["status"] = "booked"
        result["booking"] = booking
        notify_booking_made(
            monitor["restaurant"],
            slot["date"],
            slot["time"],
            slot["party_size"],
            booking.get("confirmation")
        )
        conn.execute(
            """INSERT INTO booking_attempts
               (monitor_id, restaurant_name, platform, slot_date, slot_time, party_size, status, confirmation_code, requires_cc, notified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (monitor.get("id"), monitor["restaurant"], "Resy", slot["date"], slot["time"],
             slot["party_size"], "booked", booking.get("confirmation"), False, True)
        )
        conn.commit()
    else:
        result["status"] = "failed"
        result["error"] = "Booking request failed"
        conn.execute(
            """INSERT INTO booking_attempts
               (monitor_id, restaurant_name, platform, slot_date, slot_time, party_size, status, requires_cc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (monitor.get("id"), monitor["restaurant"], "Resy", slot["date"], slot["time"],
             slot["party_size"], "failed", False)
        )
        conn.commit()

    conn.close()
    return result
