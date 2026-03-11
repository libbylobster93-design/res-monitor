#!/usr/bin/env python3
"""Master runner — calls all monitors and sends Telegram alert if slots found."""
import subprocess, sys, os, json
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8536904842:AAGhsh3CJ7vHgG7nnABcQErbE6c7sDqgoX0"
TELEGRAM_CHAT_ID = "8773861980"

def send_telegram(message: str):
    import httpx
    try:
        httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram send failed: {e}")

def run():
    print(f"=== Res Monitor Run: {datetime.now().strftime('%Y-%m-%d %H:%M PT')} ===\n")
    alerts = []

    # Run Resy checks
    print("--- RESY ---")
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        import resy_check
        resy_found = resy_check.run()
        for r in resy_found:
            slot = r['slots'][0]
            alerts.append(f"🎉 *{r['restaurant']}* (Resy) — {slot['date']}")
    except Exception as e:
        print(f"Resy check error: {e}")

    print("\n--- OPENTABLE ---")
    try:
        import opentable_check
        ot_found = opentable_check.run()
        for r in ot_found:
            slot = r['slots'][0]
            alerts.append(f"🎉 *{r['restaurant']}* (OpenTable) — {slot['date']}")
    except Exception as e:
        print(f"OpenTable check error: {e}")

    print("\n=== SUMMARY ===")
    if alerts:
        msg = "🦞 *Res Monitor Alert*\n\nAvailability found:\n" + "\n".join(alerts)
        msg += "\n\nCheck dashboard: https://res-monitor-production.up.railway.app"
        send_telegram(msg)
        print(f"Sent Telegram alert: {len(alerts)} restaurants found")
    else:
        print("No availability found — no alert sent")
    
    print(f"\nRun complete: {datetime.now().strftime('%H:%M PT')}")

if __name__ == "__main__":
    run()
