"""Resy availability monitor using the unofficial Resy API."""

import time
import sys
import os
from datetime import datetime

from typing import Optional

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db

RESY_API_KEY = "VbWk7s3L4KiK5fzlO7JD3Q5EYolJI7n5"
BASE_HEADERS = {
    "Authorization": f'ResyAPI api_key="{RESY_API_KEY}"',
    "Origin": "https://resy.com",
    "X-Origin": "https://resy.com",
    "User-Agent": "Mozilla/5.0 (compatible)",
}


def _get(url: str, params: dict = None, retries: int = 2) -> Optional[httpx.Response]:
    for attempt in range(retries + 1):
        try:
            resp = httpx.get(url, params=params, headers=BASE_HEADERS, timeout=10)
            if resp.status_code in (429, 403):
                print(f"[Resy] Rate limited ({resp.status_code}) on {url} — skipping")
                return None
            return resp
        except Exception as e:
            if attempt < retries:
                time.sleep(2)
            else:
                print(f"[Resy] Request failed after {retries} retries: {e}")
    return None


def get_venue_id(slug: str) -> Optional[int]:
    # Try known location strings
    for loc in ("sf", "san-francisco-ca", "new-york-ny", "ny"):
        resp = _get("https://api.resy.com/3/venue", params={"url_slug": slug, "location": loc})
        if resp is not None and resp.status_code == 200:
            try:
                data = resp.json()
                return data["id"]["resy"]
            except Exception as e:
                print(f"[Resy] Failed to parse venue ID for {slug}: {e}")
                return None
    # Fallback: search the SF lat/long find results by slug
    resp = _get(
        "https://api.resy.com/4/find",
        params={"lat": 37.7749, "long": -122.4194, "day": "2026-01-01", "party_size": 2},
    )
    if resp is not None and resp.status_code == 200:
        try:
            venues = resp.json().get("results", {}).get("venues", [])
            for v in venues:
                if v.get("venue", {}).get("url_slug") == slug:
                    return v["venue"]["id"]["resy"]
        except Exception:
            pass
    print(f"[Resy] Could not find venue ID for slug={slug!r} — venue may be inactive on Resy")
    return None


def check_availability(venue_id: int, party_size: int, dates: list[str]) -> list[dict]:
    slots = []
    for date in dates:
        resp = _get(
            "https://api.resy.com/4/find",
            params={"lat": 0, "long": 0, "day": date, "party_size": party_size, "venue_id": venue_id},
        )
        if resp is None:
            continue
        if resp.status_code != 200:
            print(f"[Resy] Unexpected status {resp.status_code} for venue {venue_id} on {date}")
            continue
        try:
            data = resp.json()
            results = data.get("results", {})
            venues = results.get("venues", [])
            for venue in venues:
                for slot in venue.get("slots", []):
                    date_start = slot.get("date", {}).get("start", "")
                    slots.append({"date": date, "time": date_start, "raw": slot})
        except Exception as e:
            print(f"[Resy] Parse error for venue {venue_id} on {date}: {e}")
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
        print(f"[Resy] DB log error: {e}")


def _update_last_checked(monitor_id: int):
    try:
        conn = get_db()
        now = datetime.utcnow().isoformat()
        conn.execute("UPDATE monitors SET last_checked = ? WHERE id = ?", (now, monitor_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Resy] DB update error: {e}")


def run_resy_monitors(dates: list[str] = None):
    if dates is None:
        # Default: next two weekends
        from datetime import date, timedelta
        today = date.today()
        days_ahead = []
        for i in range(14):
            d = today + timedelta(days=i + 1)
            if d.weekday() in (4, 5, 6):  # Fri/Sat/Sun
                days_ahead.append(str(d))
        dates = days_ahead[:6]

    try:
        conn = get_db()
        monitors = conn.execute(
            "SELECT * FROM monitors WHERE platform = 'Resy' AND status = 'watching'"
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"[Resy] DB read error: {e}")
        return

    # Slug mapping by restaurant name
    slug_map = {
        "Birdsong": "birdsong-san-francisco",
        "Quince": "quince-san-francisco",
        "Rich Table": "rich-table",
    }
    party_map = {
        "Birdsong": 2,
        "Quince": 2,
        "Rich Table": 2,
    }

    for monitor in monitors:
        monitor = dict(monitor)
        name = monitor["restaurant"]
        monitor_id = monitor["id"]

        slug = monitor.get("venue_slug") or slug_map.get(name)
        if not slug:
            print(f"[Resy] No slug for {name}, skipping")
            _log_result(name, "skipped: no slug configured")
            continue

        venue_id = monitor.get("venue_id")
        if venue_id:
            try:
                venue_id = int(venue_id)
            except Exception:
                venue_id = None

        if not venue_id:
            print(f"[Resy] Fetching venue ID for {name} ({slug})...")
            venue_id = get_venue_id(slug)
            if venue_id:
                try:
                    conn = get_db()
                    conn.execute("UPDATE monitors SET venue_id = ? WHERE id = ?", (str(venue_id), monitor_id))
                    conn.commit()
                    conn.close()
                except Exception:
                    pass

        if not venue_id:
            print(f"[Resy] Could not resolve venue ID for {name}, skipping")
            _log_result(name, "error: could not resolve venue ID")
            _update_last_checked(monitor_id)
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

        print(f"[Resy] Checking {name} (venue_id={venue_id}, party={party_size}) for {dates}")
        slots = check_availability(venue_id, party_size, dates)
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
            print(f"[Resy] No availability for {name}")
            _log_result(name, "no availability")

        time.sleep(1)


if __name__ == "__main__":
    from datetime import date, timedelta
    today = date.today()
    test_dates = [str(today + timedelta(days=i)) for i in range(1, 15)
                  if (today + timedelta(days=i)).weekday() in (4, 5, 6)][:4]
    print(f"Testing Resy monitors for dates: {test_dates}")
    run_resy_monitors(test_dates)
