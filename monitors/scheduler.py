"""Scheduler: runs all platform monitors and consolidates results."""

import sys
import os
from datetime import date, timedelta, datetime
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitors.resy_monitor import run_resy_monitors
from monitors.opentable_monitor import run_opentable_monitors
from monitors.tock_monitor import run_tock_monitors
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

    - Checks next 4 Fridays/Saturdays
    - Time window: 5:30pm-9:00pm Pacific
    - Party size: try 4 first, fallback to 2
    - Auto-book if no CC required, otherwise Telegram alert

    Returns:
        Dict with check results summary
    """
    from services.resy_booking import check_and_book as resy_check_and_book
    from services.playwright_booking import check_and_book_opentable, check_and_notify_tock
    from services.notifications import send_telegram

    print(f"\n{'='*60}")
    print(f"[Daily Check] Starting at {datetime.now().isoformat()}")
    print(f"{'='*60}\n")

    # Get next 4 Fri/Sat dates
    dates = _get_next_fri_sat(4)
    print(f"[Daily Check] Checking dates: {dates}")

    # Time window
    time_start = "17:30"
    time_end = "21:00"
    party_sizes = [4, 2]

    # Stats
    restaurants_checked = 0
    slots_found = 0
    bookings_made = 0
    alerts_sent = 0
    errors = []

    # Get all active monitors
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
        auto_book = monitor.get("auto_book", 0)
        prepaid = monitor.get("prepaid", 0)

        print(f"[Daily Check] --- {name} ({platform}) ---")
        restaurants_checked += 1

        try:
            if platform == "resy":
                if auto_book and not prepaid:
                    result = resy_check_and_book(monitor, dates, party_sizes, time_start, time_end)
                else:
                    # Just check, don't book (prepaid or auto_book disabled)
                    from monitors.resy_monitor import check_availability, get_venue_id
                    venue_id = monitor.get("venue_id")
                    if venue_id:
                        try:
                            venue_id = int(venue_id)
                        except ValueError:
                            venue_id = None
                    if venue_id:
                        slots = check_availability(venue_id, party_sizes[0], dates)
                        if slots:
                            slots_found += len(slots)
                            slot = slots[0]
                            send_telegram(f"🍽️ {name} available: {slot['date']} {slot['time']}")
                            alerts_sent += 1
                    result = {"status": "checked", "slots_found": slots if venue_id else []}

                if result.get("slots_found"):
                    slots_found += len(result["slots_found"])
                if result.get("status") == "booked":
                    bookings_made += 1
                    alerts_sent += 1
                elif result.get("status") == "cc_required":
                    alerts_sent += 1

            elif platform == "opentable":
                if auto_book and not prepaid:
                    result = check_and_book_opentable(monitor, dates, party_sizes, time_start, time_end)
                else:
                    from services.playwright_booking import check_opentable
                    url = monitor.get("url")
                    if url:
                        slots = check_opentable(url, dates, party_sizes, time_start, time_end)
                        if slots:
                            slots_found += len(slots)
                            slot = slots[0]
                            send_telegram(f"🍽️ {name} available: {slot['date']} {slot['time']}")
                            alerts_sent += 1
                    result = {"status": "checked", "slots_found": slots if url else []}

                if result.get("slots_found"):
                    slots_found += len(result["slots_found"])
                if result.get("status") == "booked":
                    bookings_made += 1
                    alerts_sent += 1
                elif result.get("status") == "cc_required":
                    alerts_sent += 1

            elif platform == "tock":
                # Tock is always prepaid - just check and notify
                result = check_and_notify_tock(monitor, dates, party_sizes, time_start, time_end)
                if result.get("slots_found"):
                    slots_found += len(result["slots_found"])
                if result.get("status") == "cc_required":
                    alerts_sent += 1

            else:
                print(f"[Daily Check] Unknown platform: {platform}")

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


def run_all_monitors(dates: list[str] = None):
    if dates is None:
        dates = _default_dates(days_out=30, weekends_only=False)

    print(f"\n{'='*60}")
    print(f"[Scheduler] Starting all monitors for {len(dates)} dates")
    print(f"[Scheduler] Date range: {dates[0]} → {dates[-1]}")
    print(f"{'='*60}\n")

    try:
        print("[Scheduler] --- Resy ---")
        run_resy_monitors(dates)
    except Exception as e:
        print(f"[Scheduler] Resy monitor crashed: {e}")

    try:
        print("\n[Scheduler] --- OpenTable ---")
        run_opentable_monitors(dates)
    except Exception as e:
        print(f"[Scheduler] OpenTable monitor crashed: {e}")

    try:
        print("\n[Scheduler] --- Tock ---")
        run_tock_monitors(dates)
    except Exception as e:
        print(f"[Scheduler] Tock monitor crashed: {e}")

    print(f"\n{'='*60}")
    print("[Scheduler] All monitors complete.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run restaurant availability monitors")
    parser.add_argument("--dates", nargs="*", help="Specific dates (YYYY-MM-DD)")
    parser.add_argument("--days-out", type=int, default=30, help="How many days ahead to check")
    parser.add_argument("--weekends-only", action="store_true", help="Check Fri/Sat/Sun only")
    args = parser.parse_args()

    if args.dates:
        dates = args.dates
    else:
        dates = _default_dates(days_out=args.days_out, weekends_only=args.weekends_only)

    run_all_monitors(dates)
