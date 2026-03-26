"""Scheduler: runs all platform monitors and consolidates results."""

import sys
import os
from datetime import date, timedelta, datetime
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitors.resy_monitor import run_resy_monitors
from database import get_db


def _default_dates(days_out: int = 30, weekends_only: bool = False) -> List[str]:
    today = date.today()
    dates = []
    for i in range(1, days_out + 1):
        d = today + timedelta(days=i)
        if weekends_only and d.weekday() not in (4, 5, 6):
            continue
        dates.append(str(d))
    return dates


def _get_next_fri_sat(count: int = 4) -> List[str]:
    """Get the next N Fridays and Saturdays."""
    today = date.today()
    dates = []
    d = today + timedelta(days=1)
    while len(dates) < count:
        if d.weekday() in (4, 5):  # Friday=4, Saturday=5
            dates.append(str(d))
        d += timedelta(days=1)
    return dates


def run_daily_check() -> dict:
    """
    Daily availability check for all monitored restaurants.

    Strategy:
      - Resy: full API check, auto-book if no CC required
      - OpenTable/Tock: Cloudflare-blocked — send weekly batch Telegram with booking links
      - Other/Bento: skip

    Checks next 4 Fridays/Saturdays, 5:30pm–9:00pm PT, party of 4 → 2.
    """
    from services.notifications import send_telegram
    import os

    print(f"\n{'='*60}")
    print(f"[Daily Check] Starting at {datetime.now().isoformat()}")
    print(f"{'='*60}\n")

    dates = _get_next_fri_sat(4)
    print(f"[Daily Check] Checking dates: {dates}")

    time_start = "17:30"
    time_end = "21:00"
    party_sizes = [4, 2]

    restaurants_checked = 0
    slots_found = 0
    bookings_made = 0
    alerts_sent = 0
    errors = []

    # Collect manual-check restaurants (OpenTable/Tock)
    manual_opentable = []
    manual_tock = []

    conn = get_db()
    monitors = conn.execute(
        "SELECT * FROM monitors WHERE status = 'watching'"
    ).fetchall()
    conn.close()

    print(f"[Daily Check] Found {len(monitors)} active monitors\n")

    for monitor in monitors:
        monitor = dict(monitor)
        name = monitor["restaurant"]
        platform = monitor.get("platform", "").lower()
        url = monitor.get("url", "")

        print(f"[Daily Check] --- {name} ({platform}) ---")
        restaurants_checked += 1

        try:
            if platform == "resy":
                from services.resy_booking import check_and_book as resy_check_and_book
                result = resy_check_and_book(monitor, dates, party_sizes, time_start, time_end)

                if result.get("slots_found"):
                    slots_found += len(result["slots_found"])
                    alerts_sent += 1  # notify_slot_found always fires when slots exist
                if result.get("status") == "booked":
                    bookings_made += 1
                elif result.get("status") in ("cc_required",):
                    pass  # cc_required also calls notify_cc_required — counted above

            elif platform == "opentable":
                manual_opentable.append((name, url))

            elif platform == "tock":
                manual_tock.append((name, url))

            else:
                print(f"[Daily Check] Skipping unsupported platform: {platform}")

        except Exception as e:
            error_msg = f"{name}: {str(e)}"
            print(f"[Daily Check] Error: {error_msg}")
            errors.append(error_msg)

        # Update last_checked
        try:
            conn = get_db()
            now = datetime.utcnow().isoformat()
            conn.execute("UPDATE monitors SET last_checked = ? WHERE id = ?", (now, monitor["id"]))
            conn.commit()
            conn.close()
        except Exception:
            pass

    # Send weekly manual-check digest (OpenTable + Tock) — only on Fridays
    today_weekday = date.today().weekday()
    if today_weekday == 4 and (manual_opentable or manual_tock):  # Friday only
        lines = ["📋 *Weekly manual-check reminder* — these restaurants need human eyes:\n"]
        if manual_opentable:
            lines.append("*OpenTable* (Cloudflare-blocked):")
            for name, url in manual_opentable:
                lines.append(f"  • [{name}]({url})")
        if manual_tock:
            lines.append("\n*Tock* (prepaid — book manually):")
            for name, url in manual_tock:
                lines.append(f"  • [{name}]({url})")
        lines.append(f"\nChecking: {', '.join(dates)}")
        send_telegram("\n".join(lines))
        alerts_sent += 1
        print(f"[Daily Check] Sent weekly manual-check digest ({len(manual_opentable)} OT, {len(manual_tock)} Tock)")

    # Log the check run
    try:
        conn = get_db()
        conn.execute(
            """INSERT INTO check_logs (restaurants_checked, slots_found, bookings_made, alerts_sent, errors)
               VALUES (?, ?, ?, ?, ?)""",
            (restaurants_checked, slots_found, bookings_made, alerts_sent, "; ".join(errors) if errors else None)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Daily Check] Failed to log check run: {e}")

    summary = {
        "restaurants_checked": restaurants_checked,
        "slots_found": slots_found,
        "bookings_made": bookings_made,
        "alerts_sent": alerts_sent,
        "errors": errors,
    }

    print(f"\n{'='*60}")
    print(f"[Daily Check] Complete!")
    print(f"[Daily Check] Checked: {restaurants_checked}, Found: {slots_found}, Booked: {bookings_made}, Alerts: {alerts_sent}")
    if errors:
        print(f"[Daily Check] Errors: {len(errors)}")
    print(f"{'='*60}\n")

    return summary
