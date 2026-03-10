# 🦞 Res Monitor

A private Bay Area restaurant reservation monitoring dashboard.

## Features
- Password-gated dashboard (`libbylobster`)
- Track confirmed reservations with confirmation numbers
- Monitor restaurants you're waiting on (Tock, Resy, OpenTable, Bento)
- Check log for monitoring activity history
- REST API for programmatic updates from scripts/bots

## Running locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://localhost:8000

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/reservations | List confirmed reservations |
| POST | /api/reservations | Add a confirmed reservation |
| GET | /api/monitors | List active monitors |
| POST | /api/monitors | Add a monitor |
| PATCH | /api/monitors/{id} | Update monitor status/last_checked |
| POST | /api/log | Add a log entry |
| GET | /api/log | Get recent log entries (last 20) |

## Deploy (Railway)

1. Push to GitHub
2. Connect repo in Railway
3. Railway auto-detects `Procfile` — it will run `uvicorn`

The SQLite database (`reservations.db`) is created automatically on first run and seeded with 8 Bay Area monitors.
