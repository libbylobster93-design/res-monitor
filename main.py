from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os

from database import get_db, init_db

app = FastAPI(title="Res Monitor")

init_db()

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


# ── Models ──────────────────────────────────────────────────────────────────

class ReservationIn(BaseModel):
    restaurant: str
    date: str
    time: str
    party_size: int
    confirmation_number: Optional[str] = None
    booked_on: Optional[str] = None


class MonitorIn(BaseModel):
    restaurant: str
    criteria: str
    platform: str
    url: Optional[str] = None
    status: Optional[str] = "watching"
    prepaid: Optional[int] = 0
    auto_book: Optional[int] = 0
    cc_required: Optional[str] = None
    min_cost: Optional[str] = None
    booking_notes: Optional[str] = None


class MonitorPatch(BaseModel):
    status: Optional[str] = None
    last_checked: Optional[str] = None
    criteria: Optional[str] = None
    auto_book: Optional[int] = None
    cc_required: Optional[str] = None
    min_cost: Optional[str] = None
    booking_notes: Optional[str] = None


class LogEntryIn(BaseModel):
    restaurant: str
    result: str
    timestamp: Optional[str] = None


class CheckResultIn(BaseModel):
    restaurant: str
    status: str  # "available" | "unavailable" | "check_required" | "error"
    slots: Optional[list] = []
    checked_at: Optional[str] = None


class BookedIn(BaseModel):
    restaurant: str
    date: str
    time: str
    party_size: int
    confirmation_number: Optional[str] = None
    booked_on: Optional[str] = None


# ── Reservations ─────────────────────────────────────────────────────────────

@app.get("/api/reservations")
def list_reservations():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM reservations ORDER BY date ASC, time ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/reservations", status_code=201)
def add_reservation(body: ReservationIn):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO reservations (restaurant, date, time, party_size, confirmation_number, booked_on, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            body.restaurant,
            body.date,
            body.time,
            body.party_size,
            body.confirmation_number,
            body.booked_on or now[:10],
            now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM reservations WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


# ── Monitors ─────────────────────────────────────────────────────────────────

@app.get("/api/monitors")
def list_monitors():
    conn = get_db()
    rows = conn.execute("SELECT * FROM monitors ORDER BY restaurant ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/monitors", status_code=201)
def add_monitor(body: MonitorIn):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO monitors (restaurant, criteria, platform, url, status, prepaid, auto_book, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (body.restaurant, body.criteria, body.platform, body.url, body.status or "watching", body.prepaid or 0, body.auto_book or 0, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM monitors WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


@app.patch("/api/monitors/{monitor_id}/toggle-autobook")
def toggle_autobook(monitor_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Monitor not found")
    new_val = 0 if row["auto_book"] else 1
    conn.execute("UPDATE monitors SET auto_book = ? WHERE id = ?", (new_val, monitor_id))
    conn.commit()
    row = conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
    conn.close()
    return dict(row)


@app.patch("/api/monitors/{monitor_id}")
def update_monitor(monitor_id: int, body: MonitorPatch):
    conn = get_db()
    row = conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Monitor not found")

    updates = {}
    if body.status is not None:
        updates["status"] = body.status
    if body.last_checked is not None:
        updates["last_checked"] = body.last_checked
    if body.criteria is not None:
        updates["criteria"] = body.criteria
    if body.auto_book is not None:
        updates["auto_book"] = body.auto_book
    if body.cc_required is not None:
        updates["cc_required"] = body.cc_required
    if body.min_cost is not None:
        updates["min_cost"] = body.min_cost
    if body.booking_notes is not None:
        updates["booking_notes"] = body.booking_notes

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [monitor_id]
        conn.execute(f"UPDATE monitors SET {set_clause} WHERE id = ?", values)
        conn.commit()

    row = conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
    conn.close()
    return dict(row)


# ── Check Log ────────────────────────────────────────────────────────────────

@app.post("/api/log", status_code=201)
def add_log(body: LogEntryIn):
    ts = body.timestamp or datetime.utcnow().isoformat()
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO check_log (timestamp, restaurant, result) VALUES (?, ?, ?)",
        (ts, body.restaurant, body.result),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM check_log WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


@app.get("/api/log")
def get_log():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM check_log ORDER BY timestamp DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Monitor Runner ────────────────────────────────────────────────────────────

@app.post("/api/monitors/run-check")
def run_check(body: CheckResultIn):
    """Receives check results posted by external monitoring scripts."""
    now = datetime.utcnow().isoformat()
    checked_at = body.checked_at or now

    conn = get_db()
    # Update matching monitor's last_checked and status
    conn.execute(
        "UPDATE monitors SET last_checked = ?, status = ? WHERE restaurant = ?",
        (checked_at, body.status, body.restaurant),
    )
    # Log the result
    slot_summary = ", ".join(str(s) for s in body.slots[:5]) if body.slots else "none"
    log_result = f"status={body.status} slots=[{slot_summary}]"
    conn.execute(
        "INSERT INTO check_log (timestamp, restaurant, result) VALUES (?, ?, ?)",
        (checked_at, body.restaurant, log_result),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "restaurant": body.restaurant, "status": body.status}


@app.post("/api/reservations/booked", status_code=201)
def record_booked(body: BookedIn):
    """Records a completed booking with optional confirmation number."""
    now = datetime.utcnow().isoformat()
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO reservations (restaurant, date, time, party_size, confirmation_number, booked_on, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            body.restaurant,
            body.date,
            body.time,
            body.party_size,
            body.confirmation_number,
            body.booked_on or now[:10],
            now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM reservations WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)
