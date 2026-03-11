"""Tock availability monitor using the Tock search API."""

import time
import sys
import os
from datetime import datetime

from typing import Optional

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db

TOCK_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://www.exploretock.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
}

# Tock uses Cloudflare — track if we've already been blocked to avoid spamming logs
_TOCK_CLOUDFLARE_BLOCKED = False


def _get(url: str, params: dict = None, retries: int = 2) -> Optional[httpx.Response]:
    global _TOCK_CLOUDFLARE_BLOCKED
    for attempt in range(retries + 1):
        try:
            resp = httpx.get(url, params=params, headers=TOCK_HEADERS, timeout=10, follow_redirects=True)
            if resp.status_code == 403 and "cloudflare" in resp.text.lower():
                if not _TOCK_CLOUDFLARE_BLOCKED:
                    print("[Tock] Cloudflare bot protection active — pure HTTP calls are blocked. "
                          "A session cookie (cf_clearance) is required to bypass this.")
                    _TOCK_CLOUDFLARE_BLOCKED = True
                return None
            if resp.status_code in (429, 403):
                print(f"[Tock] Blocked ({resp.status_code}) — skipping")
                return None
            _TOCK_CLOUDFLARE_BLOCKED = False  # reset if we got through
            return resp
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            if attempt < retries:
                time.sleep(2)
            else:
                print(f"[Tock] Timed out after {retries} retries on {url}")
        except Exception as e:
            if attempt < retries:
                time.sleep(2)
            else:
                print(f"[Tock] Request failed after {retries} retries: {e}")
    return None


def check_availability(slug: str, party_size: int, dates: list[str]) -> list[dict]:
    slots = []
    for date in dates:
        url = "https://www.exploretock.com/api/experiences/search/timeslot"
        params = {
            "city": "",
            "date": date,
            "size": party_size,
            "time": "19:00",
            "venueSlug": slug,
        }
        resp = _get(url, params=params)
        if resp is None:
            continue
        if resp.status_code != 200:
            print(f"[Tock] Unexpected status {resp.status_code} for {slug} on {date}")
            continue
        try:
            data = resp.json()
            # Tock returns list of experiences or timeslots
            items = data if isinstance(data, list) else data.get("results", []) or data.get("timeslots", []) or data.get("experiences", [])
            for item in items:
                if isinstance(item, dict):
                    slot_time = item.get("startTime") or item.get("time") or item.get("dateTime") or date
                    available = item.get("available", True)
                    if available:
                        slots.append({"date": date, "time": slot_time, "raw": item})
                else:
                    slots.append({"date": date, "time": str(item), "raw": item})
            if items:
                print(f"[Tock] {slug} on {date}: found {len(items)} slot(s)")
        except Exception as e:
            print(f"[Tock] Parse error for {slug} on {date}: {e} | body={resp.text[:200]}")
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
        print(f"[Tock] DB log error: {e}")


def _update_last_checked(monitor_id: int):
    try:
        conn = get_db()
        now = datetime.utcnow().isoformat()
        conn.execute("UPDATE monitors SET last_checked = ? WHERE id = ?", (now, monitor_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Tock] DB update error: {e}")


def run_tock_monitors(dates: list[str] = None):
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
            "SELECT * FROM monitors WHERE platform = 'Tock' AND status = 'watching'"
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"[Tock] DB read error: {e}")
        return

    slug_map = {
        "Benu": "benu",
        "Lazy Bear": "lazybear",
        "Saison": "saison",
        "Noodle in a Haystack": "noodleinahaystack",
        "Single Thread": "singlethreadfarms",
        "Californios": "californios",
    }

    for monitor in monitors:
        monitor = dict(monitor)
        name = monitor["restaurant"]
        monitor_id = monitor["id"]

        slug = monitor.get("venue_slug") or slug_map.get(name)
        if not slug:
            print(f"[Tock] No slug for {name}, skipping")
            _log_result(name, "skipped: no slug configured")
            continue

        party_size = 2
        try:
            criteria = monitor.get("criteria", "")
            for part in criteria.split("|"):
                part = part.strip()
                if part.startswith("Party:"):
                    party_size = int(part.split(":")[1].strip())
                    break
        except Exception:
            pass

        print(f"[Tock] Checking {name} (slug={slug}, party={party_size}) for {dates}")
        slots = check_availability(slug, party_size, dates)
        _update_last_checked(monitor_id)

        if slots:
            for slot in slots:
                msg = f"AVAILABLE: {slot['date']} {slot['time']}"
                # Tock restaurants are prepaid — always alert, never auto-book
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
            print(f"[Tock] No availability for {name}")
            _log_result(name, "no availability")

        time.sleep(1)


if __name__ == "__main__":
    from datetime import date, timedelta
    today = date.today()
    test_dates = [str(today + timedelta(days=i)) for i in range(1, 15)
                  if (today + timedelta(days=i)).weekday() in (4, 5, 6)][:4]
    print(f"Testing Tock monitors for dates: {test_dates}")
    run_tock_monitors(test_dates)
