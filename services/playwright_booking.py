"""Playwright-based booking for OpenTable and Tock (Cloudflare bypass)."""

import time
from typing import Optional, Dict, List, Any

# Playwright is optional - gracefully handle if not installed
try:
    from playwright.sync_api import sync_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[Playwright] Not installed - browser-based booking disabled. Run: pip install playwright && playwright install chromium")


def _launch_browser():
    """Launch a headless browser with stealth settings."""
    if not PLAYWRIGHT_AVAILABLE:
        return None, None

    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ]
    )
    return pw, browser


def check_opentable(
    restaurant_url: str,
    dates: List[str],
    party_sizes: List[int] = [4, 2],
    time_start: str = "17:30",
    time_end: str = "21:00",
) -> List[Dict[str, Any]]:
    """
    Check OpenTable for availability using Playwright.

    Args:
        restaurant_url: Full OpenTable URL (e.g., https://www.opentable.com/house-of-prime-rib)
        dates: List of dates to check (YYYY-MM-DD)
        party_sizes: Party sizes to try in order
        time_start: Earliest acceptable time
        time_end: Latest acceptable time

    Returns:
        List of available slots with date, time, party_size, and cc_required
    """
    if not PLAYWRIGHT_AVAILABLE:
        print("[OpenTable] Playwright not available")
        return []

    slots = []
    pw = None
    browser = None

    try:
        pw, browser = _launch_browser()
        if not browser:
            return []

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()

        for party_size in party_sizes:
            for date in dates:
                try:
                    # Build URL with params
                    url = f"{restaurant_url}?date={date}&partySize={party_size}&time=19:00"
                    print(f"[OpenTable] Checking {url}")
                    page.goto(url, timeout=30000)
                    time.sleep(3)  # Wait for dynamic content

                    # Look for time slot buttons
                    # OpenTable uses various selectors depending on page version
                    slot_selectors = [
                        "[data-test='time-slot-button']",
                        ".timeslot-button",
                        "[class*='TimeSlot']",
                        "button[data-time]",
                    ]

                    for selector in slot_selectors:
                        try:
                            slot_elements = page.query_selector_all(selector)
                            if slot_elements:
                                for el in slot_elements:
                                    slot_time = el.get_attribute("data-time") or el.inner_text().strip()
                                    # Parse time and filter
                                    if slot_time and len(slot_time) >= 4:
                                        time_clean = slot_time[:5].replace(":", "").ljust(4, "0")
                                        try:
                                            time_formatted = f"{time_clean[:2]}:{time_clean[2:4]}"
                                            if time_start <= time_formatted <= time_end:
                                                slots.append({
                                                    "date": date,
                                                    "time": time_formatted,
                                                    "party_size": party_size,
                                                    "platform": "OpenTable",
                                                    "url": url,
                                                    "cc_required": None,  # Check during booking
                                                })
                                        except (ValueError, IndexError):
                                            pass
                                break
                        except Exception:
                            pass

                except Exception as e:
                    print(f"[OpenTable] Error checking {date}: {e}")

                time.sleep(2)  # Rate limiting

            if slots:
                break  # Found slots, don't try smaller party size

    except Exception as e:
        print(f"[OpenTable] Browser error: {e}")
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()

    return slots


def check_tock(
    restaurant_url: str,
    dates: List[str],
    party_sizes: List[int] = [4, 2],
    time_start: str = "17:30",
    time_end: str = "21:00",
) -> List[Dict[str, Any]]:
    """
    Check Tock for availability using Playwright.

    Args:
        restaurant_url: Full Tock URL (e.g., https://www.exploretock.com/benu)
        dates: List of dates to check (YYYY-MM-DD)
        party_sizes: Party sizes to try in order
        time_start: Earliest acceptable time
        time_end: Latest acceptable time

    Returns:
        List of available slots
    """
    if not PLAYWRIGHT_AVAILABLE:
        print("[Tock] Playwright not available")
        return []

    slots = []
    pw = None
    browser = None

    try:
        pw, browser = _launch_browser()
        if not browser:
            return []

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()

        for party_size in party_sizes:
            for date in dates:
                try:
                    # Tock URL format
                    url = f"{restaurant_url}?date={date}&size={party_size}&time=19:00"
                    print(f"[Tock] Checking {url}")
                    page.goto(url, timeout=30000)
                    time.sleep(3)

                    # Look for Cloudflare challenge
                    if "challenge" in page.content().lower() or "cf-" in page.content():
                        print("[Tock] Cloudflare challenge detected - manual session required")
                        continue

                    # Tock slot selectors
                    slot_selectors = [
                        "[data-testid='timeslot']",
                        ".timeslot",
                        "[class*='Timeslot']",
                        "button[data-time]",
                    ]

                    for selector in slot_selectors:
                        try:
                            slot_elements = page.query_selector_all(selector)
                            if slot_elements:
                                for el in slot_elements:
                                    slot_time = el.get_attribute("data-time") or el.inner_text().strip()
                                    if slot_time and len(slot_time) >= 4:
                                        time_clean = slot_time[:5].replace(":", "").ljust(4, "0")
                                        try:
                                            time_formatted = f"{time_clean[:2]}:{time_clean[2:4]}"
                                            if time_start <= time_formatted <= time_end:
                                                slots.append({
                                                    "date": date,
                                                    "time": time_formatted,
                                                    "party_size": party_size,
                                                    "platform": "Tock",
                                                    "url": url,
                                                    "cc_required": True,  # Tock is always prepaid
                                                })
                                        except (ValueError, IndexError):
                                            pass
                                break
                        except Exception:
                            pass

                except Exception as e:
                    print(f"[Tock] Error checking {date}: {e}")

                time.sleep(2)

            if slots:
                break

    except Exception as e:
        print(f"[Tock] Browser error: {e}")
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()

    return slots


def book_opentable(
    slot_info: Dict[str, Any],
    name: str = "Andrew Ren",
    email: str = "andrewren3@gmail.com",
    phone: str = "",
) -> Dict[str, Any]:
    """
    Attempt to book an OpenTable slot.

    Returns:
        Dict with status (booked|cc_required|failed), confirmation, etc.
    """
    if not PLAYWRIGHT_AVAILABLE:
        return {"status": "failed", "error": "Playwright not available"}

    result = {
        "status": "failed",
        "confirmation": None,
        "cc_required": False,
        "error": None,
    }

    pw = None
    browser = None

    try:
        pw, browser = _launch_browser()
        if not browser:
            result["error"] = "Failed to launch browser"
            return result

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()

        url = slot_info.get("url")
        if not url:
            result["error"] = "No URL in slot info"
            return result

        page.goto(url, timeout=30000)
        time.sleep(3)

        # Find and click the time slot
        slot_time = slot_info.get("time", "")
        clicked = False

        for selector in ["[data-test='time-slot-button']", ".timeslot-button", "button[data-time]"]:
            try:
                buttons = page.query_selector_all(selector)
                for btn in buttons:
                    btn_time = btn.get_attribute("data-time") or btn.inner_text()
                    if slot_time in btn_time:
                        btn.click()
                        clicked = True
                        break
                if clicked:
                    break
            except Exception:
                pass

        if not clicked:
            result["error"] = "Could not find/click time slot"
            return result

        time.sleep(2)

        # Check for CC requirement on booking page
        page_content = page.content().lower()
        if "credit card" in page_content or "card number" in page_content or "payment" in page_content:
            result["status"] = "cc_required"
            result["cc_required"] = True
            return result

        # Fill booking form (if no CC required)
        try:
            # Name field
            name_input = page.query_selector("input[name*='name'], input[placeholder*='name']")
            if name_input:
                name_input.fill(name)

            # Email field
            email_input = page.query_selector("input[name*='email'], input[type='email']")
            if email_input:
                email_input.fill(email)

            # Phone field
            if phone:
                phone_input = page.query_selector("input[name*='phone'], input[type='tel']")
                if phone_input:
                    phone_input.fill(phone)

            # Submit
            submit_btn = page.query_selector("button[type='submit'], [data-test='complete-reservation']")
            if submit_btn:
                submit_btn.click()
                time.sleep(5)

                # Check for confirmation
                if "confirmed" in page.content().lower() or "confirmation" in page.content().lower():
                    result["status"] = "booked"
                    # Try to extract confirmation number
                    conf_match = page.query_selector("[data-test='confirmation-number'], .confirmation-number")
                    if conf_match:
                        result["confirmation"] = conf_match.inner_text()
                else:
                    result["error"] = "Booking submission unclear"
            else:
                result["error"] = "Could not find submit button"

        except Exception as e:
            result["error"] = f"Form fill error: {e}"

    except Exception as e:
        result["error"] = f"Browser error: {e}"
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()

    return result


def check_and_book_opentable(
    monitor: Dict[str, Any],
    dates: List[str],
    party_sizes: List[int] = [4, 2],
    time_start: str = "17:30",
    time_end: str = "21:00",
) -> Dict[str, Any]:
    """
    Full OpenTable flow: check availability and book if no CC required.
    """
    from services.notifications import notify_booking_made, notify_cc_required
    from database import get_db

    result = {
        "status": "no_slots",
        "restaurant": monitor.get("restaurant"),
        "slots_found": [],
        "booking": None,
        "error": None,
    }

    url = monitor.get("url")
    if not url:
        result["status"] = "error"
        result["error"] = "No URL configured"
        return result

    # Check availability
    slots = check_opentable(url, dates, party_sizes, time_start, time_end)
    result["slots_found"] = slots

    if not slots:
        return result

    # Try to book first slot
    slot = slots[0]
    conn = get_db()

    booking_result = book_opentable(slot)

    if booking_result["status"] == "booked":
        result["status"] = "booked"
        result["booking"] = booking_result
        notify_booking_made(
            monitor["restaurant"],
            slot["date"],
            slot["time"],
            slot["party_size"],
            booking_result.get("confirmation")
        )
        conn.execute(
            """INSERT INTO booking_attempts
               (monitor_id, restaurant_name, platform, slot_date, slot_time, party_size, status, confirmation_code, requires_cc, notified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (monitor.get("id"), monitor["restaurant"], "OpenTable", slot["date"], slot["time"],
             slot["party_size"], "booked", booking_result.get("confirmation"), False, True)
        )
    elif booking_result["status"] == "cc_required":
        result["status"] = "cc_required"
        notify_cc_required(
            monitor["restaurant"],
            slot["date"],
            slot["time"],
            slot["party_size"],
            url
        )
        conn.execute(
            """INSERT INTO booking_attempts
               (monitor_id, restaurant_name, platform, slot_date, slot_time, party_size, status, requires_cc, notified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (monitor.get("id"), monitor["restaurant"], "OpenTable", slot["date"], slot["time"],
             slot["party_size"], "cc_required", True, True)
        )
    else:
        result["status"] = "failed"
        result["error"] = booking_result.get("error")
        conn.execute(
            """INSERT INTO booking_attempts
               (monitor_id, restaurant_name, platform, slot_date, slot_time, party_size, status, requires_cc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (monitor.get("id"), monitor["restaurant"], "OpenTable", slot["date"], slot["time"],
             slot["party_size"], "failed", False)
        )

    conn.commit()
    conn.close()
    return result


def check_and_notify_tock(
    monitor: Dict[str, Any],
    dates: List[str],
    party_sizes: List[int] = [4, 2],
    time_start: str = "17:30",
    time_end: str = "21:00",
) -> Dict[str, Any]:
    """
    Check Tock availability and notify (Tock is always prepaid, no auto-book).
    """
    from services.notifications import notify_cc_required
    from database import get_db

    result = {
        "status": "no_slots",
        "restaurant": monitor.get("restaurant"),
        "slots_found": [],
        "error": None,
    }

    url = monitor.get("url")
    if not url:
        result["status"] = "error"
        result["error"] = "No URL configured"
        return result

    slots = check_tock(url, dates, party_sizes, time_start, time_end)
    result["slots_found"] = slots

    if not slots:
        return result

    # Tock is always prepaid - just notify
    slot = slots[0]
    result["status"] = "cc_required"
    notify_cc_required(
        monitor["restaurant"],
        slot["date"],
        slot["time"],
        slot["party_size"],
        url
    )

    conn = get_db()
    conn.execute(
        """INSERT INTO booking_attempts
           (monitor_id, restaurant_name, platform, slot_date, slot_time, party_size, status, requires_cc, notified)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (monitor.get("id"), monitor["restaurant"], "Tock", slot["date"], slot["time"],
         slot["party_size"], "cc_required", True, True)
    )
    conn.commit()
    conn.close()

    return result
