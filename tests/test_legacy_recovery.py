"""Smoke tests for legacy remnant import + player_basic_info rebuild."""
from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "endstone_arc_core"

def _load(name: str):
    path = SRC / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


dm = _load("DatabaseManager")
rec = _load("legacy_recovery")
DatabaseManager = dm.DatabaseManager


def _log(_level: str, _msg: str) -> None:
    return


def test_import_and_rebuild_from_remnants() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        main_db = str(base / "ARCCore.db")
        old_economy = base / "old_economy.db"
        sky = base / "skyeye.db"

        db = DatabaseManager(main_db)
        db.create_table(
            "player_basic_info",
            {
                "uuid": "TEXT PRIMARY KEY",
                "xuid": "TEXT NOT NULL",
                "name": "TEXT NOT NULL",
                "password": "TEXT",
                "inviter_xuid": "TEXT",
                "pending_invite_reward_times": "INTEGER DEFAULT 0",
                "default_title_auto_equipped": "INTEGER DEFAULT 0",
                "total_playtime": "INTEGER DEFAULT 0",
                "session_count": "INTEGER DEFAULT 0",
                "last_join_time": "TEXT",
                "last_quit_time": "TEXT",
                "once_op": "INTEGER DEFAULT 0",
            },
        )
        db.create_table(
            "player_economy",
            {"xuid": "TEXT PRIMARY KEY", "money": "REAL NOT NULL DEFAULT 0"},
        )
        db.create_table(
            "player_local_info",
            {
                "xuid": "TEXT PRIMARY KEY",
                "is_op": "INTEGER DEFAULT 0",
                "remaining_free_land_blocks": "INTEGER DEFAULT 100",
            },
        )
        db.insert("player_local_info", {"xuid": "1001", "is_op": 1})
        db.insert("player_local_info", {"xuid": "1002", "is_op": 0})

        econ = sqlite3.connect(str(old_economy))
        econ.execute(
            "CREATE TABLE player_economy (xuid TEXT PRIMARY KEY, money REAL NOT NULL DEFAULT 0)"
        )
        econ.execute("INSERT INTO player_economy (xuid, money) VALUES ('1001', 50.5)")
        econ.execute("INSERT INTO player_economy (xuid, money) VALUES ('1003', 9)")
        econ.commit()
        econ.close()

        sky_conn = sqlite3.connect(str(sky))
        sky_conn.execute(
            """
            CREATE TABLE sky_eye_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                ts_unix INTEGER NOT NULL,
                action TEXT NOT NULL,
                player_name TEXT NOT NULL,
                player_xuid TEXT NOT NULL
            )
            """
        )
        sky_conn.executemany(
            "INSERT INTO sky_eye_events (ts, ts_unix, action, player_name, player_xuid) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                ("2026-01-01 10:00:00", 1000, "PlayerJoin", "Steve", "1001"),
                ("2026-01-01 10:10:00", 1600, "PlayerQuit", "Steve", "1001"),
                ("2026-01-01 12:00:00", 2000, "PlayerJoin", "Alex", "1002"),
            ],
        )
        sky_conn.commit()
        sky_conn.close()

        imported = rec.import_legacy_tables(db, [old_economy], _log)
        assert imported["tables"].get("player_economy", 0) >= 2
        money = db.query_one("SELECT money FROM player_economy WHERE xuid=?", ("1001",))
        assert money is not None
        assert float(money["money"]) == 50.5

        stats = rec.rebuild_player_basic_info(db, sky, _log)
        assert stats["inserted"] >= 3
        steve = db.query_one(
            "SELECT * FROM player_basic_info WHERE xuid=?", ("1001",)
        )
        assert steve is not None
        assert steve["name"] == "Steve"
        assert str(steve["uuid"]).startswith("recovered-")
        assert int(steve["session_count"]) == 1
        assert int(steve["total_playtime"]) == 600
        assert int(steve["once_op"]) == 1
        alex = db.query_one(
            "SELECT name, session_count FROM player_basic_info WHERE xuid=?",
            ("1002",),
        )
        assert alex is not None
        assert alex["name"] == "Alex"
        assert int(alex["session_count"]) == 1
        extra = db.query_one(
            "SELECT name FROM player_basic_info WHERE xuid=?", ("1003",)
        )
        assert extra is not None
        assert str(extra["name"]).startswith("xuid:")

        stats2 = rec.rebuild_player_basic_info(db, sky, _log)
        assert stats2["inserted"] == 0
        db.close()


if __name__ == "__main__":
    test_import_and_rebuild_from_remnants()
    print("ok")
