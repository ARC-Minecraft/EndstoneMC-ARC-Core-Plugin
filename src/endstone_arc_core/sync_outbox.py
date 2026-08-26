# -*- coding: utf-8 -*-
"""子服上行 outbox：断线期间本地变更落盘，重连后按序重放。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

OUTBOX_TABLE = "sync_outbox"
OUTBOX_MAX_ATTEMPTS = 50


def ensure_outbox_table(db) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS sync_outbox ("
        "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
        "table_name TEXT NOT NULL, "
        "op TEXT NOT NULL, "
        "payload_json TEXT NOT NULL, "
        "created_at TEXT NOT NULL, "
        "attempts INTEGER NOT NULL DEFAULT 0, "
        "last_error TEXT"
        ")"
    )


def enqueue(
    db,
    table: str,
    op: str,
    payload: Dict[str, Any],
) -> Optional[int]:
    """写入 outbox，返回 seq；失败返回 None。"""
    table_s = str(table or "").strip().lower()
    op_s = str(op or "").strip().lower()
    if not table_s or op_s not in ("insert", "delete"):
        return None
    ensure_outbox_table(db)
    created_at = datetime.now().isoformat(timespec="seconds")
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    ok = db.execute(
        "INSERT INTO sync_outbox (table_name, op, payload_json, created_at, attempts) "
        "VALUES (?, ?, ?, ?, 0)",
        (table_s, op_s, payload_json, created_at),
    )
    if not ok:
        return None
    row = db.query_one("SELECT last_insert_rowid() AS seq", ())
    if not row:
        return None
    try:
        return int(row.get("seq"))
    except (TypeError, ValueError):
        return None


def list_pending(db, limit: int = 200) -> List[Dict[str, Any]]:
    ensure_outbox_table(db)
    rows = db.query_all(
        "SELECT seq, table_name, op, payload_json, created_at, attempts, last_error "
        "FROM sync_outbox ORDER BY seq ASC LIMIT ?",
        (max(1, int(limit)),),
    ) or []
    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.get("payload_json") or "{}")
        except Exception:
            item["payload"] = {}
        out.append(item)
    return out


def count_pending(db) -> int:
    ensure_outbox_table(db)
    row = db.query_one("SELECT COUNT(*) AS c FROM sync_outbox", ())
    try:
        return int((row or {}).get("c") or 0)
    except (TypeError, ValueError):
        return 0


def delete_seq(db, seq: int) -> None:
    try:
        db.execute("DELETE FROM sync_outbox WHERE seq = ?", (int(seq),))
    except Exception:
        pass


def mark_attempt(db, seq: int, error: str = "") -> int:
    """attempts + 1，写入 last_error；返回新 attempts。"""
    try:
        row = db.query_one(
            "SELECT attempts FROM sync_outbox WHERE seq = ?", (int(seq),)
        )
        attempts = int((row or {}).get("attempts") or 0) + 1
        db.execute(
            "UPDATE sync_outbox SET attempts = ?, last_error = ? WHERE seq = ?",
            (attempts, str(error or "")[:500], int(seq)),
        )
        return attempts
    except Exception:
        return OUTBOX_MAX_ATTEMPTS


def latest_error(db) -> str:
    ensure_outbox_table(db)
    row = db.query_one(
        "SELECT last_error FROM sync_outbox "
        "WHERE last_error IS NOT NULL AND TRIM(last_error) != '' "
        "ORDER BY seq DESC LIMIT 1",
        (),
    )
    return str((row or {}).get("last_error") or "").strip()
