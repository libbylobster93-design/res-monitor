import os
import sqlite3
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_PATH = os.environ.get("DB_PATH", "reservations.db")

_use_postgres = DATABASE_URL is not None


class _CursorResult:
    """Wraps a cursor to provide lastrowid and fetch methods consistently."""
    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class DbConnection:
    """Thin wrapper providing a consistent interface for SQLite and PostgreSQL."""

    def __init__(self):
        if _use_postgres:
            import psycopg2
            import psycopg2.extras
            self._conn = psycopg2.connect(DATABASE_URL)
            self._is_pg = True
        else:
            self._conn = sqlite3.connect(DB_PATH)
            self._conn.row_factory = sqlite3.Row
            self._is_pg = False

    def execute(self, sql, params=None):
        if self._is_pg:
            import psycopg2.extras
            sql = sql.replace("?", "%s")
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, params or ())
            # Attempt to get lastrowid for INSERTs
            lastrowid = None
            if cur.description is None and sql.strip().upper().startswith("INSERT"):
                # Re-run to get the id — but we handle this via _execute_insert
                pass
            return _CursorResult(cur, lastrowid)
        else:
            cur = self._conn.execute(sql, params or ())
            return _CursorResult(cur, cur.lastrowid)

    def execute_insert(self, sql, params=None):
        """Execute an INSERT and return the new row's id."""
        if self._is_pg:
            import psycopg2.extras
            sql = sql.replace("?", "%s")
            # Append RETURNING id if not already present
            if "RETURNING" not in sql.upper():
                sql = sql.rstrip().rstrip(";") + " RETURNING id"
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, params or ())
            row = cur.fetchone()
            return row["id"] if row else None
        else:
            cur = self._conn.execute(sql, params or ())
            return cur.lastrowid

    def executemany(self, sql, params_list):
        if self._is_pg:
            sql = sql.replace("?", "%s")
            cur = self._conn.cursor()
            cur.executemany(sql, params_list)
        else:
            self._conn.executemany(sql, params_list)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_db():
    return DbConnection()


def init_db():
    conn_raw = None
    if _use_postgres:
        import psycopg2
        conn_raw = psycopg2.connect(DATABASE_URL)
        cur = conn_raw.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id SERIAL PRIMARY KEY,
                restaurant TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                party_size INTEGER NOT NULL,
                confirmation_number TEXT,
                booked_on TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS monitors (
                id SERIAL PRIMARY KEY,
                restaurant TEXT NOT NULL,
                criteria TEXT NOT NULL,
                platform TEXT NOT NULL,
                url TEXT,
                status TEXT NOT NULL DEFAULT 'watching',
                last_checked TEXT,
                prepaid INTEGER NOT NULL DEFAULT 0,
                auto_book INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS check_log (
                id SERIAL PRIMARY KEY,
                timestamp TEXT NOT NULL,
                restaurant TEXT NOT NULL,
                result TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS booking_attempts (
                id SERIAL PRIMARY KEY,
                monitor_id INTEGER,
                restaurant_name TEXT,
                platform TEXT,
                slot_date TEXT,
                slot_time TEXT,
                party_size INTEGER,
                status TEXT,
                confirmation_code TEXT,
                requires_cc BOOLEAN,
                notified BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS check_logs (
                id SERIAL PRIMARY KEY,
                run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                restaurants_checked INTEGER,
                slots_found INTEGER,
                bookings_made INTEGER,
                alerts_sent INTEGER,
                errors TEXT
            )
        """)
        conn_raw.commit()

        # Migration: add new columns to existing monitors table if missing
        for col, definition in [
            ("prepaid", "INTEGER NOT NULL DEFAULT 0"),
            ("auto_book", "INTEGER NOT NULL DEFAULT 0"),
            ("venue_id", "TEXT"),
            ("venue_slug", "TEXT"),
            ("cc_required", "TEXT"),
            ("min_cost", "TEXT"),
            ("booking_notes", "TEXT"),
        ]:
            try:
                cur.execute(f"ALTER TABLE monitors ADD COLUMN {col} {definition}")
                conn_raw.commit()
            except Exception:
                conn_raw.rollback()

        # Update criteria for all monitors
        cur.execute(
            "UPDATE monitors SET criteria = %s WHERE restaurant != %s",
            ("Party: 4 | Sat/Sun 5:00pm–7:30pm", "House of Prime Rib"),
        )
        cur.execute(
            "UPDATE monitors SET criteria = %s WHERE restaurant = %s",
            ("Party: 4 | Sat/Sun 5:00pm–7:30pm | April 1+ only", "House of Prime Rib"),
        )

        # Seed booking_notes
        booking_notes_seed = _get_booking_notes_seed()
        for restaurant, notes in booking_notes_seed:
            cur.execute(
                "UPDATE monitors SET booking_notes = %s WHERE restaurant = %s AND (booking_notes IS NULL OR booking_notes = '')",
                (notes, restaurant),
            )

        conn_raw.commit()

        # Seed monitors if empty
        cur.execute("SELECT COUNT(*) FROM monitors")
        count = cur.fetchone()[0]
        if count == 0:
            now = datetime.utcnow().isoformat()
            seed_monitors = _get_seed_monitors()
            for r in seed_monitors:
                cur.execute(
                    "INSERT INTO monitors (restaurant, criteria, platform, url, venue_id, prepaid, auto_book, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (r[0], r[1], r[2], r[3], r[4], r[5], r[6], now),
                )

        conn_raw.commit()
        cur.close()
        conn_raw.close()
    else:
        conn_raw = sqlite3.connect(DB_PATH)
        conn_raw.row_factory = sqlite3.Row
        c = conn_raw.cursor()

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

            CREATE TABLE IF NOT EXISTS booking_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monitor_id INTEGER,
                restaurant_name TEXT,
                platform TEXT,
                slot_date TEXT,
                slot_time TEXT,
                party_size INTEGER,
                status TEXT,
                confirmation_code TEXT,
                requires_cc BOOLEAN,
                notified BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS check_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                restaurants_checked INTEGER,
                slots_found INTEGER,
                bookings_made INTEGER,
                alerts_sent INTEGER,
                errors TEXT
            );
        """)

        # Migration: add new columns to existing monitors table if missing
        for col, definition in [
            ("prepaid", "INTEGER NOT NULL DEFAULT 0"),
            ("auto_book", "INTEGER NOT NULL DEFAULT 0"),
            ("venue_id", "TEXT"),
            ("venue_slug", "TEXT"),
            ("cc_required", "TEXT"),
            ("min_cost", "TEXT"),
            ("booking_notes", "TEXT"),
        ]:
            try:
                c.execute(f"ALTER TABLE monitors ADD COLUMN {col} {definition}")
                conn_raw.commit()
            except Exception:
                pass

        # Update criteria for all monitors
        c.execute(
            "UPDATE monitors SET criteria = ? WHERE restaurant != ?",
            ("Party: 4 | Sat/Sun 5:00pm–7:30pm", "House of Prime Rib"),
        )
        c.execute(
            "UPDATE monitors SET criteria = ? WHERE restaurant = ?",
            ("Party: 4 | Sat/Sun 5:00pm–7:30pm | April 1+ only", "House of Prime Rib"),
        )

        # Seed booking_notes
        booking_notes_seed = _get_booking_notes_seed()
        for restaurant, notes in booking_notes_seed:
            c.execute(
                "UPDATE monitors SET booking_notes = ? WHERE restaurant = ? AND (booking_notes IS NULL OR booking_notes = '')",
                (notes, restaurant),
            )

        conn_raw.commit()

        # Seed monitors if empty
        c.execute("SELECT COUNT(*) FROM monitors")
        count = c.fetchone()[0]
        if count == 0:
            now = datetime.utcnow().isoformat()
            seed_monitors = _get_seed_monitors()
            c.executemany(
                "INSERT INTO monitors (restaurant, criteria, platform, url, venue_id, prepaid, auto_book, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], now) for r in seed_monitors],
            )

        conn_raw.commit()
        conn_raw.close()


def _get_booking_notes_seed():
    return [
        ("House of Prime Rib", "Releases ~1yr out; midnight PT daily"),
        ("Benu", "Releases 10am daily, 30 days out"),
        ("Atelier Crenn", "Releases monthly"),
        ("Lazy Bear", "Releases 1st of month, 2 months out"),
        ("Noodle in a Haystack", "Releases monthly via Tock"),
        ("Saison", "Releases monthly"),
        ("Single Thread", "Releases monthly"),
        ("Californios", "Releases monthly via Tock"),
        ("Quince", "Releases monthly"),
        ("Gary Danko", "Releases daily, 1 month out"),
        ("Birdsong", "Releases via Tock"),
        ("State Bird Provisions", "Releases daily via Resy"),
        ("Rich Table", "Releases daily via Resy"),
        ("Commis", "Releases daily via OpenTable"),
        ("Chez Panisse", "Phone only: (510) 548-5525"),
        ("Acquerello", "Releases daily via OpenTable"),
        ("Nopa", "Releases daily via OpenTable"),
        ("Zuni Café", "Releases daily via OpenTable"),
        ("Sun Moon Studio", "Releases via Tock; 4 tables only"),
        ("Kokkari Estiatorio", "Releases daily via OpenTable"),
        ("Al's Place", "Releases daily via Resy"),
        ("Mister Jiu's", "Releases daily via Resy"),
        ("Nightbird", "Releases daily via Resy"),
        ("Sorrel", "Releases daily via Resy"),
    ]


def _get_seed_monitors():
    return [
        ("Mister Jiu's",     "Party: 4 | Fri/Sat | Dinner", "Resy",      "https://resy.com/cities/sf/venues/mister-jius",  "93096", 0, 1),
        ("Gary Danko",       "Party: 4 | Fri/Sat | Dinner", "OpenTable", "https://www.opentable.com/gary-danko",           None,    0, 0),
        ("House of Prime Rib","Party: 4 | Fri/Sat | Dinner","OpenTable", "https://www.opentable.com/house-of-prime-rib",   None,    0, 0),
        ("State Bird Provisions","Party: 4 | Fri/Sat | Dinner","OpenTable","https://www.opentable.com/state-bird-provisions",None,  0, 0),
        ("Rich Table",       "Party: 4 | Fri/Sat | Dinner", "OpenTable", "https://www.opentable.com/rich-table",           None,    0, 0),
        ("Commis",           "Party: 4 | Fri/Sat | Dinner", "OpenTable", "https://www.opentable.com/commis",               None,    0, 0),
        ("Sorrel",           "Party: 4 | Fri/Sat | Dinner", "Tock",      "https://www.exploretock.com/sorrel-san-francisco",None,    1, 0),
        ("Benu",             "Party: 4 | Fri/Sat | Dinner", "Tock",      "https://www.exploretock.com/benu",               None,    1, 0),
        ("Lazy Bear",        "Party: 4 | Fri/Sat | Dinner", "Tock",      "https://www.exploretock.com/lazybear",           None,    1, 0),
        ("Noodle in a Haystack","Party: 4 | Fri/Sat | Dinner","Tock",    "https://www.exploretock.com/noodleinahaystack",  None,    1, 0),
        ("Saison",           "Party: 4 | Fri/Sat | Dinner", "Tock",      "https://www.exploretock.com/saison",             None,    1, 0),
        ("Single Thread",    "Party: 4 | Fri/Sat | Dinner", "Tock",      "https://www.exploretock.com/singlethreadfarms",  None,    1, 0),
        ("Californios",      "Party: 4 | Fri/Sat | Dinner", "Tock",      "https://www.exploretock.com/californios",        None,    1, 0),
    ]
