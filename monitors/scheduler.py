"""Scheduler: runs all platform monitors and consolidates results."""

import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitors.resy_monitor import run_resy_monitors
from monitors.opentable_monitor import run_opentable_monitors
from monitors.tock_monitor import run_tock_monitors


def _default_dates(days_out: int = 30, weekends_only: bool = False) -> list[str]:
    today = date.today()
    dates = []
    for i in range(1, days_out + 1):
        d = today + timedelta(days=i)
        if weekends_only and d.weekday() not in (4, 5, 6):
            continue
        dates.append(str(d))
    return dates


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
