#!/usr/bin/env python3
"""Resy availability checker — pure HTTP, no browser."""
import httpx, json, time, sys
from datetime import datetime, timedelta
from typing import Optional

RESY_API_KEY = "VbWk7s3L4KiK5fzlO7JD3Q5EYolJI7n5"
HEADERS = {
    "Authorization": f'ResyAPI api_key="{RESY_API_KEY}"',
    "Origin": "https://resy.com",
    "X-Origin": "https://resy.com",
    "Referer": "https://resy.com/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

DASHBOARD_URL = "https://res-monitor-production.up.railway.app"

# Restaurants with confirmed venue_ids don't need slug lookup
RESTAURANTS = [
    {"name": "Gary Danko",  "venue_id": 5891, "slug": None,                       "location": "sf", "party": 2},
    {"name": "Birdsong",    "venue_id": None,  "slug": "birdsong-san-francisco",   "location": "sf", "party": 2},
    {"name": "Quince",      "venue_id": None,  "slug": "quince-san-francisco",     "location": "sf", "party": 2},
    {"name": "Rich Table",  "venue_id": None,  "slug": "rich-table",               "location": "sf", "party": 2},
]


def get_venue_id(slug: str, location: str) -> Optional[int]:
    try:
        r = httpx.get(
            f"https://api.resy.com/3/venue?url_slug={slug}&location={location}",
            headers=HEADERS, timeout=10
        )
        data = r.json()
        return data.get("id", {}).get("resy") or data.get("venue", {}).get("id", {}).get("resy")
    except Exception as e:
        print(f"  venue lookup failed: {e}")
        return None


def check_availability(venue_id: int, party_size: int, dates: list) -> list:
    slots = []
    for day in dates:
        try:
            r = httpx.get(
                f"https://api.resy.com/4/find?lat=0&long=0&day={day}&party_size={party_size}&venue_id={venue_id}",
                headers=HEADERS, timeout=10
            )
            data = r.json()
            venues = data.get("results", {}).get("venues", [])
            for v in venues:
                for slot in v.get("slots", []):
                    slots.append({
                        "date": slot.get("date", {}).get("start", ""),
                        "type": slot.get("config", {}).get("type", ""),
                    })
            time.sleep(0.5)
        except Exception as e:
            print(f"  availability check failed for {day}: {e}")
    return slots


def post_result(restaurant: str, status: str, slots: list, checked_at: str):
    try:
        httpx.post(
            f"{DASHBOARD_URL}/api/monitors/run-check",
            json={
                "restaurant": restaurant,
                "status": status,
                "slots": [f"{s.get('date','')} {s.get('type','')}".strip() for s in slots[:5]],
                "checked_at": checked_at,
            },
            timeout=10
        )
    except Exception as e:
        print(f"  dashboard POST failed: {e}")


def run():
    # Check next 30 days, all days
    dates = []
    d = datetime.now()
    for i in range(1, 31):
        day = d + timedelta(days=i)
        dates.append(day.strftime("%Y-%m-%d"))

    print(f"Resy check — {datetime.now().strftime('%Y-%m-%d %H:%M PT')}")
    print(f"Checking next {len(dates)} days: {dates[0]} → {dates[-1]}\n")

    found = []
    for r in RESTAURANTS:
        print(f"🔍 {r['name']}...")
        checked_at = datetime.utcnow().isoformat()

        vid = r["venue_id"]
        if vid is None:
            vid = get_venue_id(r["slug"], r["location"])
        if not vid:
            print(f"  ⚠️  Could not find venue ID for {r['name']} — skipping\n")
            post_result(r["name"], "error", [], checked_at)
            continue
        print(f"  venue_id: {vid}")

        slots = check_availability(vid, r["party"], dates)
        if slots:
            print(f"  ✅ {len(slots)} slots available!")
            for s in slots[:3]:
                print(f"     → {s['date']} ({s['type']})")
            found.append({"restaurant": r["name"], "slots": slots})
            post_result(r["name"], "available", slots, checked_at)
        else:
            print(f"  ❌ No availability")
            post_result(r["name"], "unavailable", [], checked_at)
        print()
        time.sleep(1)

    return found


if __name__ == "__main__":
    results = run()
    if results:
        print(f"\n🎉 FOUND AVAILABILITY: {[r['restaurant'] for r in results]}")
    else:
        print("\nNo availability found today.")
