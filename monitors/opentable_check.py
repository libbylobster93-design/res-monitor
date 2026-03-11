#!/usr/bin/env python3
"""OpenTable availability checker — pure HTTP."""
import httpx, json, time
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.opentable.com/",
    "Accept": "application/json, text/plain, */*",
}

DASHBOARD_URL = "https://res-monitor-production.up.railway.app"

RESTAURANTS = [
    {"name": "House of Prime Rib",   "rid": 1779,   "party": 4, "days": ["saturday", "sunday"], "start": "17:00", "end": "19:30", "min_date": "2026-04-01"},
    {"name": "Gary Danko",           "rid": 3709,   "party": 2, "days": ["any"],                "start": "17:00", "end": "21:00", "min_date": None},
    {"name": "State Bird Provisions","rid": 220077, "party": 2, "days": ["any"],                "start": "17:00", "end": "21:00", "min_date": None},
    {"name": "Commis",               "rid": 69604,  "party": 2, "days": ["any"],                "start": "17:00", "end": "21:00", "min_date": None},
]


def check_availability(rid: int, party_size: int, date: str, start_time: str, end_time: str) -> list:
    try:
        r = httpx.get(
            "https://www.opentable.com/widget/reservation/availability",
            params={
                "rid": rid,
                "type": "standard",
                "startTime": start_time,
                "endTime": end_time,
                "covers": party_size,
                "date": date,
            },
            headers=HEADERS,
            timeout=20
        )
        if r.status_code == 200:
            try:
                data = r.json()
                times = data.get("availability", data.get("times", data.get("availableTimes", [])))
                return times if isinstance(times, list) else []
            except Exception:
                return ["available"] if "available" in r.text.lower() and r.text.strip() else []
        return []
    except Exception as e:
        print(f"  error: {e}")
        return []


def post_result(restaurant: str, status: str, slots: list, checked_at: str):
    try:
        httpx.post(
            f"{DASHBOARD_URL}/api/monitors/run-check",
            json={
                "restaurant": restaurant,
                "status": status,
                "slots": [s.get("date", str(s)) if isinstance(s, dict) else str(s) for s in slots[:5]],
                "checked_at": checked_at,
            },
            timeout=10
        )
    except Exception as e:
        print(f"  dashboard POST failed: {e}")


def run():
    d = datetime.now()
    dates = []
    for i in range(1, 35):
        day = d + timedelta(days=i)
        dates.append((day.strftime("%Y-%m-%d"), day.strftime("%A").lower()))

    print(f"OpenTable check — {datetime.now().strftime('%Y-%m-%d %H:%M PT')}")
    print(f"Checking up to {len(dates)} dates\n")

    found = []
    for r in RESTAURANTS:
        print(f"🔍 {r['name']} (rid={r['rid']})...")
        checked_at = datetime.utcnow().isoformat()
        slots = []

        check_dates = [
            (date, weekday) for date, weekday in dates
            if (r["days"] == ["any"] or any(w in weekday for w in r["days"]))
            and (r["min_date"] is None or date >= r["min_date"])
        ][:10]  # cap at 10 dates per restaurant

        for date, weekday in check_dates:
            result = check_availability(r["rid"], r["party"], date, r["start"], r["end"])
            if result:
                slots.extend([{"date": date, "info": str(t)} for t in result[:3]])
            time.sleep(0.3)

        if slots:
            print(f"  ✅ {len(slots)} slots found!")
            for s in slots[:3]:
                print(f"     → {s['date']} {s.get('info','')[:50]}")
            found.append({"restaurant": r["name"], "slots": slots})
            post_result(r["name"], "available", slots, checked_at)
        elif not check_dates:
            print(f"  ⏭  No qualifying dates in window")
            post_result(r["name"], "check_required", [], checked_at)
        else:
            print(f"  ❌ No availability (OT widget may require browser session)")
            post_result(r["name"], "check_required", [], checked_at)
        print()
        time.sleep(1)

    return found


if __name__ == "__main__":
    results = run()
    if results:
        print(f"\n🎉 FOUND: {[r['restaurant'] for r in results]}")
    else:
        print("\nNo availability found.")
