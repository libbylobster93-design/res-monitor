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
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS check_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            restaurant TEXT NOT NULL,
            result TEXT NOT NULL
        );
    """)

    # Seed monitors if empty
    c.execute("SELECT COUNT(*) FROM monitors")
    count = c.fetchone()[0]
    if count == 0:
        now = datetime.utcnow().isoformat()
        seed_monitors = [
            (
                "House of Prime Rib",
                "Party: 4 | Sat/Sun only | 5:00pm–7:30pm | April 1+ 2026",
                "OpenTable",
                "https://www.opentable.com/house-of-prime-rib",
                "watching",
                now,
            ),
            (
                "Benu",
                "Party: 2 | Any day | Dinner",
                "Tock",
                "https://www.exploretock.com/benu",
                "watching",
                now,
            ),
            (
                "Atelier Crenn",
                "Party: 2 | Any day | Dinner",
                "Bento",
                "https://ateliercrenn.getbento.com/",
                "watching",
                now,
            ),
            (
                "Lazy Bear",
                "Party: 2 | Any day | Dinner | Releases 1st of month",
                "Tock",
                "https://www.exploretock.com/lazybear",
                "watching",
                now,
            ),
            (
                "Noodle in a Haystack",
                "Party: 2 | Any day | Dinner | Releases monthly",
                "Tock",
                "https://www.exploretock.com/noodleinahaystack",
                "watching",
                now,
            ),
            (
                "Saison",
                "Party: 2 | Tue–Sat | Dinner | Releases 1st of month",
                "Tock",
                "https://www.exploretock.com/saison",
                "watching",
                now,
            ),
            (
                "Single Thread",
                "Party: 2 | Any day | Dinner",
                "Tock",
                "https://www.exploretock.com/singlethreadfarms",
                "watching",
                now,
            ),
            (
                "Quince",
                "Party: 2 | Any day | Dinner",
                "Resy",
                "https://resy.com/cities/sf/quince",
                "watching",
                now,
            ),
        ]
        c.executemany(
            "INSERT INTO monitors (restaurant, criteria, platform, url, status, last_checked, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(r[0], r[1], r[2], r[3], r[4], r[5], now) for r in seed_monitors],
        )

    conn.commit()
    conn.close()
