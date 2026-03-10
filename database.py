import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "reservations.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            party_size INTEGER NOT NULL,
            confirmation_number TEXT,
            booked_on TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS monitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            restaurant TEXT NOT NULL,
            criteria TEXT NOT NULL,
            platform TEXT NOT NULL,
            url TEXT,
            status TEXT NOT NULL DEFAULT 'watching',
            last_checked TEXT,
            prepaid INTEGER NOT NULL DEFAULT 0,
            auto_book INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS check_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            restaurant TEXT NOT NULL,
            result TEXT NOT NULL
        );
    """)

    # Migration: add new columns to existing monitors table if missing
    for col, definition in [
        ("prepaid", "INTEGER NOT NULL DEFAULT 0"),
        ("auto_book", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        try:
            c.execute(f"ALTER TABLE monitors ADD COLUMN {col} {definition}")
            conn.commit()
        except Exception:
            pass

    # Seed monitors if empty
    c.execute("SELECT COUNT(*) FROM monitors")
    count = c.fetchone()[0]
    if count == 0:
        now = datetime.utcnow().isoformat()
        # Tuple: (restaurant, criteria, platform, url, status, last_checked, prepaid, auto_book)
        seed_monitors = [
            # ── Non-prepaid (credit card hold) — auto_book=1 ──────────────────
            (
                "House of Prime Rib",
                "Party: 4 | Sat/Sun only | 5:00pm–7:30pm | April 1+ 2026",
                "OpenTable",
                "https://www.opentable.com/house-of-prime-rib",
                "watching",
                now,
                0,
                1,
            ),
            (
                "Quince",
                "Party: 2 | Any day | Dinner",
                "Resy",
                "https://resy.com/cities/sf/quince",
                "watching",
                now,
                0,
                1,
            ),
            (
                "Gary Danko",
                "Party: 2 | Any night | Dinner",
                "OpenTable",
                "https://www.opentable.com/gary-danko",
                "watching",
                now,
                0,
                1,
            ),
            (
                "Birdsong",
                "Party: 2 | Any night | Dinner",
                "Resy",
                "https://resy.com/cities/sf/birdsong",
                "watching",
                now,
                0,
                1,
            ),
            (
                "State Bird Provisions",
                "Party: 2 | Any night | Dinner",
                "OpenTable",
                "https://www.opentable.com/state-bird-provisions",
                "watching",
                now,
                0,
                1,
            ),
            (
                "Rich Table",
                "Party: 2 | Any night | Dinner",
                "Resy",
                "https://resy.com/cities/sf/rich-table",
                "watching",
                now,
                0,
                1,
            ),
            (
                "Commis",
                "Party: 2 | Any night | Dinner | Oakland",
                "OpenTable",
                "https://www.opentable.com/commis",
                "watching",
                now,
                0,
                1,
            ),
            (
                "Chez Panisse",
                "Party: 2 | Any night | Dinner | Berkeley",
                "Other",
                "https://www.chezpanisse.com/reservations/",
                "watching",
                now,
                0,
                1,
            ),
            # ── Prepaid (charged at booking) — auto_book=0 ───────────────────
            (
                "Benu",
                "Party: 2 | Any day | Dinner",
                "Tock",
                "https://www.exploretock.com/benu",
                "watching",
                now,
                1,
                0,
            ),
            (
                "Atelier Crenn",
                "Party: 2 | Any day | Dinner",
                "Bento",
                "https://ateliercrenn.getbento.com/",
                "watching",
                now,
                1,
                0,
            ),
            (
                "Lazy Bear",
                "Party: 2 | Any day | Dinner | Releases 1st of month",
                "Tock",
                "https://www.exploretock.com/lazybear",
                "watching",
                now,
                1,
                0,
            ),
            (
                "Noodle in a Haystack",
                "Party: 2 | Any day | Dinner | Releases monthly",
                "Tock",
                "https://www.exploretock.com/noodleinahaystack",
                "watching",
                now,
                1,
                0,
            ),
            (
                "Saison",
                "Party: 2 | Tue–Sat | Dinner | Releases 1st of month",
                "Tock",
                "https://www.exploretock.com/saison",
                "watching",
                now,
                1,
                0,
            ),
            (
                "Single Thread",
                "Party: 2 | Any day | Dinner",
                "Tock",
                "https://www.exploretock.com/singlethreadfarms",
                "watching",
                now,
                1,
                0,
            ),
            (
                "Californios",
                "Party: 2 | Any day | Dinner",
                "Tock",
                "https://www.exploretock.com/californios",
                "watching",
                now,
                1,
                0,
            ),
        ]
        c.executemany(
            "INSERT INTO monitors (restaurant, criteria, platform, url, status, last_checked, prepaid, auto_book, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], now) for r in seed_monitors],
        )

    conn.commit()
    conn.close()
