"""Smoke tests for DatabaseManager table routing (DDL / PRAGMA / DML)."""
from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DM_PATH = ROOT / "src" / "endstone_arc_core" / "DatabaseManager.py"

spec = importlib.util.spec_from_file_location("DatabaseManager", DM_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
DatabaseManager = mod.DatabaseManager


def test_extract_table_names() -> None:
    cases = [
        ("ALTER TABLE player_basic_info ADD COLUMN is_op INTEGER", "player_basic_info"),
        ("CREATE TABLE IF NOT EXISTS player_basic_info (xuid TEXT)", "player_basic_info"),
        ("DROP TABLE IF EXISTS player_basic_info", "player_basic_info"),
        ("PRAGMA table_info(player_basic_info)", "player_basic_info"),
        ("PRAGMA table_info(`player_basic_info`)", "player_basic_info"),
        (
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='title_definitions'",
            "title_definitions",
        ),
        ("UPDATE player_basic_info SET is_op=1 WHERE xuid=?", "player_basic_info"),
        ("INSERT OR REPLACE INTO player_title_equipped (xuid) VALUES (?)", "player_title_equipped"),
        ("SELECT * FROM player_economy", "player_economy"),
    ]
    for sql, expect in cases:
        got = DatabaseManager._extract_table_name(sql)
        assert got == expect, f"{sql!r} -> {got!r}, expect {expect!r}"


def test_ddl_routes_to_shared_db() -> None:
    with tempfile.TemporaryDirectory() as td:
        local = str(Path(td) / "local.db")
        shared = str(Path(td) / "shared.db")
        db = DatabaseManager(local)
        db.add_route("player_basic_info", shared)

        assert db.create_table(
            "player_basic_info",
            {"xuid": "TEXT PRIMARY KEY", "name": "TEXT"},
        )
        assert db.execute(
            "ALTER TABLE player_basic_info ADD COLUMN is_op INTEGER DEFAULT 0"
        )
        cols = db.get_table_columns("player_basic_info")
        assert "is_op" in cols
        assert "xuid" in cols

        conn = sqlite3.connect(local)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='player_basic_info'"
            ).fetchall()
        finally:
            conn.close()
        assert not rows, "orphan player_basic_info must not be created on local db"

        assert db.upsert(
            "player_basic_info",
            {"xuid": "1", "name": "Steve", "is_op": 1, "money": 999},
        )
        row = db.query_one(
            "SELECT xuid, name, is_op FROM player_basic_info WHERE xuid=?", ("1",)
        )
        assert row is not None
        assert int(row["is_op"]) == 1
        assert "money" not in row
        db.close()


def test_tables_in_sql() -> None:
    sql = (
        "INSERT INTO player_basic_info__sync_new (xuid) "
        "SELECT xuid FROM player_basic_info"
    )
    assert DatabaseManager.tables_in_sql(sql) == [
        "player_basic_info__sync_new",
        "player_basic_info",
    ]
    alter = "ALTER TABLE player_basic_info__sync_new RENAME TO player_basic_info"
    names = DatabaseManager.tables_in_sql(alter)
    assert "player_basic_info__sync_new" in names
    assert "player_basic_info" in names


def test_cross_db_insert_select_rejected() -> None:
    with tempfile.TemporaryDirectory() as td:
        local = str(Path(td) / "local.db")
        shared = str(Path(td) / "shared.db")
        db = DatabaseManager(local)
        db.add_route("player_basic_info", shared)
        assert db.create_table(
            "player_basic_info",
            {"uuid": "TEXT PRIMARY KEY", "xuid": "TEXT", "name": "TEXT"},
        )
        db.upsert(
            "player_basic_info",
            {"uuid": "u1", "xuid": "1", "name": "Steve"},
        )
        ok = db.execute(
            "CREATE TABLE player_basic_info__sync_new "
            "(uuid TEXT PRIMARY KEY, xuid TEXT, name TEXT)"
        )
        assert ok
        mixed = db.execute(
            "INSERT INTO player_basic_info__sync_new (uuid, xuid, name) "
            "SELECT uuid, xuid, name FROM player_basic_info"
        )
        assert mixed is False
        still = db.query_one(
            "SELECT xuid FROM player_basic_info WHERE xuid=?", ("1",)
        )
        assert still is not None
        db.close()


def test_rebuild_table_copy_stays_on_shared_db() -> None:
    with tempfile.TemporaryDirectory() as td:
        local = str(Path(td) / "local.db")
        shared = str(Path(td) / "shared.db")
        db = DatabaseManager(local)
        db.add_route("player_basic_info", shared)
        assert db.create_table(
            "player_basic_info",
            {
                "uuid": "TEXT PRIMARY KEY",
                "xuid": "TEXT NOT NULL",
                "name": "TEXT NOT NULL",
                "is_op": "INTEGER DEFAULT 0",
            },
        )
        db.upsert(
            "player_basic_info",
            {"uuid": "u1", "xuid": "1", "name": "Steve", "is_op": 1},
        )
        db.upsert(
            "player_basic_info",
            {"uuid": "u2", "xuid": "2", "name": "Alex", "is_op": 0},
        )
        ok = db.rebuild_table_copy(
            logical_table="player_basic_info",
            temp_table="player_basic_info__sync_new",
            create_sql=(
                "CREATE TABLE player_basic_info__sync_new ("
                "uuid TEXT PRIMARY KEY, "
                "xuid TEXT NOT NULL, "
                "name TEXT NOT NULL"
                ")"
            ),
            copy_columns=["uuid", "xuid", "name"],
        )
        assert ok
        cols = db.get_table_columns("player_basic_info")
        assert "uuid" in cols and "is_op" not in cols
        row = db.query_one(
            "SELECT name FROM player_basic_info WHERE xuid=?", ("1",)
        )
        assert row is not None and row["name"] == "Steve"
        conn = sqlite3.connect(local)
        try:
            names = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
        finally:
            conn.close()
        assert "player_basic_info" not in names
        shared_conn = sqlite3.connect(shared)
        try:
            n = shared_conn.execute(
                "SELECT COUNT(*) FROM player_basic_info"
            ).fetchone()[0]
        finally:
            shared_conn.close()
        assert n == 2
        db.close()


if __name__ == "__main__":
    test_extract_table_names()
    test_ddl_routes_to_shared_db()
    test_tables_in_sql()
    test_cross_db_insert_select_rejected()
    test_rebuild_table_copy_stays_on_shared_db()
    print("ok")
