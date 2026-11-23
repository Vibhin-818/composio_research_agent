import json
import sqlite3
from typing import Any, Optional

from config import CACHE_DB


def _connect() -> sqlite3.Connection:
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(CACHE_DB)


def init() -> None:
    con = _connect()
    con.execute(
        "CREATE TABLE IF NOT EXISTS docs (app_id INTEGER PRIMARY KEY, payload TEXT)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS app_results ("
        "app_id INTEGER PRIMARY KEY, payload TEXT NOT NULL, "
        "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS manual_review ("
        "app_id INTEGER PRIMARY KEY, reason TEXT NOT NULL, "
        "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    con.commit()
    con.close()


def get(app_id: int) -> Optional[dict[str, Any]]:
    con = _connect()
    row = con.execute("SELECT payload FROM docs WHERE app_id = ?", (app_id,)).fetchone()
    con.close()
    if not row:
        return None
    return json.loads(row[0])


def put(app_id: int, payload: dict[str, Any]) -> None:
    con = _connect()
    con.execute(
        "INSERT OR REPLACE INTO docs (app_id, payload) VALUES (?, ?)",
        (app_id, json.dumps(payload, ensure_ascii=False)),
    )
    con.commit()
    con.close()


def load_results() -> dict[int, dict[str, Any]]:
    con = _connect()
    try:
        rows = con.execute("SELECT app_id, payload FROM app_results").fetchall()
        return {int(app_id): json.loads(payload) for app_id, payload in rows}
    finally:
        con.close()


def save_result(record: dict[str, Any]) -> None:
    app_id = int(record["id"])
    con = _connect()
    try:
        con.execute(
            "INSERT INTO app_results (app_id, payload, updated_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(app_id) DO UPDATE SET "
            "payload = excluded.payload, updated_at = CURRENT_TIMESTAMP",
            (app_id, json.dumps(record, ensure_ascii=False)),
        )

        if record.get("status") in ("needs-human", "error"):
            verification = record.get("verification") or {}
            issues = verification.get("issues") or []
            reason = record.get("error") or "; ".join(map(str, issues))
            reason = reason or "Verifier flagged this app for manual review."
            con.execute(
                "INSERT INTO manual_review (app_id, reason, updated_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(app_id) DO UPDATE SET "
                "reason = excluded.reason, updated_at = CURRENT_TIMESTAMP",
                (app_id, reason),
            )
        else:
            con.execute("DELETE FROM manual_review WHERE app_id = ?", (app_id,))

        con.commit()
    finally:
        con.close()
