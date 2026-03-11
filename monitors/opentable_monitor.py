"""OpenTable availability monitor using the unofficial widget API."""

import time
import sys
import os
from datetime import datetime

from typing import Optional

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db

OT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://www.opentable.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Ordered list of availability endpoint templates to try (rid substituted in)
_ENDPOINT_TEMPLATES = [
    # OT internal availability API (JSON)
    ("GET", "https://www.opentable.com/widget/reservation/availability", "params"),
    # Booking flow slot API
    ("GET", "https://www.opentable.com/booking/booking-flow/time-slots", "params_alt"),
]


def _get(url: str, params: dict = None, retries: int = 2, timeout: int = 20) -> Optional[httpx.Response]:
    for attempt in range(retries + 1):
        try:
            resp = httpx.get(url, params=params, headers=OT_HEADERS, timeout=timeout, follow_redirects=True)
            if resp.status_code in (429, 403):
                print(f"[OpenTable] Blocked ({resp.status_code}) on {url} — skipping")
                return None
            return resp
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            if attempt < retries:
                print(f"[OpenTable] Timeout on attempt {attempt + 1}, retrying...")
                time.sleep(2)
            else:
                print(f"[OpenTable] Timed out after {retries} retries on {url}")
        except Exception as e:
            if attempt < retries:
                time.sleep(2)
            else:
                print(f"[OpenTable] Request failed after {retries} retries: {e}")
    return None


def check_availability(rid: int, party_size: int, dates: list[str], start_time: str = "17:00", end_time: str = "21:30") -> list[dict]:
    slots = []
    for date in dates:
        # Primary endpoint: OT widget availability
        params = {
            "rid": rid,
            "type": "standard",
            "startTime": start_time,
            "endTime": end_time,
            "covers": party_size,
            "date": date,
        }
        resp = _get("https://www.opentable.com/widget/reservation/availability", params=params, timeout=20)

        # Fallback: booking-flow slot API
        if resp is None or resp.status_code != 200:
            alt_params = {
                "restaurantId": rid,
                "dateTime": f"{date}T19:00",
                "partySize": party_size,
            }
            resp = _get("https://www.opentable.com/booking/booking-flow/time-slots", params=alt_params, timeout=20)

        if resp is None:
            print(f"[OpenTable] No response for rid={rid} on {date} — platform may be blocking requests")
            continue
        if resp.status_code != 200:
            print(f"[OpenTable] Unexpected status {resp.status_code} for rid={rid} on {date}")
            continue
        try:
            data = resp.json()
            times = []
            if isinstance(data, dict):
                for key in ("availability", "times", "slots", "timeslots", "timeSlots"):
                    val = data.get(key)
                    if isinstance(val, list) and val:
                        times = val
                        break
            elif isinstance(data, list):
                times = data
            for t in times:
                if isinstance(t, dict):
                    slot_time = t.get("dateTime") or t.get("time") or t.get("startTime") or str(t)
                else:
                    slot_time = str(t)
                slots.append({"date": date, "time": slot_time, "raw": t})
        except Exception as e:
            print(f"[OpenTable] Parse error for rid={rid} on {date}: {e} | body={resp.text[:200]}")
        time.sleep(1)
    return slots


def _log_result(restaurant: str, result: str):
    try:
        conn = get_db()
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO check_log (timestamp, restaurant, result) VALUES (?, ?, ?)",
            (now, restaurant, result),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[OpenTable] DB log error: {e}")


def _update_last_checked(monitor_id: int):
    try:
        conn = get_db()
        now = datetime.utcnow().isoformat()
        conn.execute("UPDATE monitors SET last_checked = ? WHERE id = ?", (now, monitor_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[OpenTable] DB update error: {e}")


def run_opentable_monitors(dates: list[str] = None):
    if dates is None:
        from datetime import date, timedelta
        today = date.today()
        days_ahead = []
        for i in range(14):
            d = today + timedelta(days=i + 1)
            if d.weekday() in (4, 5, 6):
                days_ahead.append(str(d))
        dates = days_ahead[:6]

    try:
        conn = get_db()
        monitors = conn.execute(
            "SELECT * FROM monitors WHERE platform = 'OpenTable' AND status = 'watching'"
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"[OpenTable] DB read error: {e}")
        return

    rid_map = {
        "House of Prime Rib": 1779,
        "Gary Danko": 3709,
        "State Bird Provisions": 220077,
        "Commis": 69604,
    }
    party_map = {
        "House of Prime Rib": 4,
        "Gary Danko": 2,
        "State Bird Provisions": 2,
        "Commis": 2,
    }

    for monitor in monitors:
        monitor = dict(monitor)
        name = monitor["restaurant"]
        monitor_id = monitor["id"]

        rid = monitor.get("venue_id")
        if rid:
            try:
                rid = int(rid)
            except Exception:
                rid = None

        if not rid:
            rid = rid_map.get(name)

        if not rid:
            print(f"[OpenTable] No rid for {name}, skipping")
            _log_result(name, "skipped: no rid configured")
            continue

        party_size = party_map.get(name, 2)
        try:
            criteria = monitor.get("criteria", "")
            for part in criteria.split("|"):
                part = part.strip()
                if part.startswith("Party:"):
                    party_size = int(part.split(":")[1].strip())
                    break
        except Exception:
            pass

        print(f"[OpenTable] Checking {name} (rid={rid}, party={party_size}) for {dates}")
        slots = check_availability(rid, party_size, dates)
        _update_last_checked(monitor_id)

        if slots:
            for slot in slots:
                msg = f"AVAILABLE: {slot['date']} {slot['time']}"
                if monitor.get("prepaid"):
                    print(f"ALERT: {name} available {slot['date']} {slot['time']} - PREPAID, needs manual approval")
                    _log_result(name, f"ALERT: {msg} (prepaid)")
                elif monitor.get("auto_book"):
                    print(f"BOOK: {name} {slot['date']} {slot['time']}")
                    _log_result(name, f"BOOK: {msg}")
                else:
                    print(f"ALERT: {name} {msg}")
                    _log_result(name, f"alert: {msg}")
        else:
            print(f"[OpenTable] No availability for {name}")
            _log_result(name, "no availability")

        time.sleep(1)


if __name__ == "__main__":
    from datetime import date, timedelta
    today = date.today()
    test_dates = [str(today + timedelta(days=i)) for i in range(1, 15)
                  if (today + timedelta(days=i)).weekday() in (4, 5, 6)][:4]
    print(f"Testing OpenTable monitors for dates: {test_dates}")
    run_opentable_monitors(test_dates)
