# -*- coding: utf-8 -*-
"""一次性：从旧共享库导回残余表，并用天眼/本地表重建 player_basic_info。"""
from __future__ import annotations

import json
import sqlite3
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

RECOVERED_UUID_PREFIX = "recovered-"
MARKER_NAME = ".legacy_import_done"
LEGACY_PATHS_SETTING = "LEGACY_IMPORT_DATABASE_PATHS"

IMPORT_TABLES = (
    "player_basic_info",
    "player_economy",
    "title_definitions",
    "player_title_unlock_time",
    "player_title_equipped",
    "guilds",
    "guild_members",
    "guild_invites",
)

XUID_SOURCES = (
    ("player_local_info", "xuid"),
    ("player_economy", "xuid"),
    ("player_title_unlock_time", "xuid"),
    ("player_title_equipped", "xuid"),
    ("lands", "owner_xuid"),
    ("sub_lands", "owner_xuid"),
    ("player_homes", "owner_xuid"),
    ("public_warps", "created_by"),
    ("guild_members", "xuid"),
    ("guilds", "owner_xuid"),
    ("player_activity_stats", "xuid"),
    ("guild_invites", "invitee_xuid"),
    ("guild_invites", "inviter_xuid"),
)

LogFn = Callable[[str, str], None]


def parse_legacy_paths(raw: Optional[str]) -> List[Path]:
    if not raw or not str(raw).strip():
        return []
    out: List[Path] = []
    seen: Set[str] = set()
    for part in str(raw).split(","):
        text = part.strip().strip('"').strip("'")
        if not text:
            continue
        path = Path(text)
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _alias_for_index(i: int) -> str:
    return f"legacy{i}"


def _table_exists_on(conn: sqlite3.Connection, table: str, schema: str = "main") -> bool:
    row = conn.execute(
        f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _columns_on(conn: sqlite3.Connection, table: str, schema: str = "main") -> List[str]:
    rows = conn.execute(f"PRAGMA {schema}.table_info({table})").fetchall()
    names: List[str] = []
    for row in rows:
        name = row[1] if row is not None else None
        if name:
            names.append(str(name))
    return names


def _import_table_from_attached(
    db,
    src_path: Path,
    table: str,
    alias: str,
) -> Tuple[int, str]:
    dest_path = Path(db.path_for_table(table))
    try:
        if dest_path.exists() and src_path.resolve() == dest_path.resolve():
            return 0, "skip-same-file"
    except Exception:
        pass
    if not db.table_exists(table):
        return 0, "dest-missing"
    conn = db.connection_for_table(table)
    src_sql = src_path.resolve().as_posix().replace("'", "''")
    try:
        conn.execute(f"ATTACH DATABASE '{src_sql}' AS {alias}")
        if not _table_exists_on(conn, table, alias):
            return 0, "src-missing"
        src_cols = set(_columns_on(conn, table, alias))
        dest_cols = _columns_on(conn, table, "main")
        common = [c for c in dest_cols if c in src_cols]
        if not common:
            return 0, "no-common-columns"
        col_sql = ", ".join(common)
        cur = conn.execute(
            f"INSERT OR IGNORE INTO {table} ({col_sql}) "
            f"SELECT {col_sql} FROM {alias}.{table}"
        )
        conn.commit()
        n = 0 if cur.rowcount is None else max(0, int(cur.rowcount))
        return n, "ok"
    except Exception as e:
        with suppress(sqlite3.Error):
            conn.rollback()
        return 0, f"error:{e}"
    finally:
        try:
            conn.execute(f"DETACH DATABASE {alias}")
        except Exception:
            pass


def import_legacy_tables(db, paths: Iterable[Path], log: LogFn) -> Dict[str, Any]:
    stats: Dict[str, Any] = {"files": [], "tables": {}}
    for i, path in enumerate(paths):
        if not path.exists() or not path.is_file():
            log("warning", f"[ARC Core]Legacy import skip missing file: {path}")
            stats["files"].append({"path": str(path), "ok": False, "reason": "missing"})
            continue
        file_stat = {"path": str(path), "ok": True, "imported": {}}
        for table in IMPORT_TABLES:
            n, reason = _import_table_from_attached(db, path, table, _alias_for_index(i))
            file_stat["imported"][table] = {"rows": n, "reason": reason}
            prev = stats["tables"].get(table, 0)
            stats["tables"][table] = prev + n
            if reason not in ("ok", "src-missing", "skip-same-file", "dest-missing"):
                log(
                    "warning",
                    f"[ARC Core]Legacy import {path.name}.{table}: {reason}",
                )
            elif n:
                log(
                    "info",
                    f"[ARC Core]Legacy import {path.name}.{table}: +{n} rows",
                )
        stats["files"].append(file_stat)
    return stats


def collect_xuids_from_core(db) -> Set[str]:
    xuids: Set[str] = set()
    for table, col in XUID_SOURCES:
        try:
            if not db.table_exists(table):
                continue
            cols = db.get_table_columns(table)
            if col not in cols:
                continue
            rows = db.query_all(f"SELECT DISTINCT {col} AS xuid FROM {table}") or []
            for row in rows:
                xuid = str((row or {}).get("xuid") or "").strip()
                if xuid:
                    xuids.add(xuid)
        except Exception:
            continue
    return xuids


def _sky_eye_connect(sky_eye_db: Path) -> Optional[sqlite3.Connection]:
    if not sky_eye_db.exists() or not sky_eye_db.is_file():
        return None
    conn = sqlite3.connect(str(sky_eye_db))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sky_eye_events'"
        ).fetchone()
        if row is None:
            conn.close()
            return None
    except Exception:
        conn.close()
        return None
    return conn


def collect_xuids_from_sky_eye(sky_eye_db: Path) -> Set[str]:
    conn = _sky_eye_connect(sky_eye_db)
    if conn is None:
        return set()
    try:
        rows = conn.execute(
            "SELECT DISTINCT player_xuid AS xuid FROM sky_eye_events "
            "WHERE player_xuid IS NOT NULL AND TRIM(player_xuid) != ''"
        ).fetchall()
        return {str(r["xuid"]).strip() for r in rows if r and r["xuid"]}
    except Exception:
        return set()
    finally:
        conn.close()


def latest_names_from_sky_eye(sky_eye_db: Path) -> Dict[str, str]:
    conn = _sky_eye_connect(sky_eye_db)
    if conn is None:
        return {}
    out: Dict[str, str] = {}
    try:
        rows = conn.execute(
            "SELECT player_xuid, player_name FROM sky_eye_events "
            "WHERE player_xuid IS NOT NULL AND TRIM(player_xuid) != '' "
            "ORDER BY ts_unix DESC, id DESC"
        ).fetchall()
        for row in rows:
            xuid = str(row["player_xuid"] or "").strip()
            name = str(row["player_name"] or "").strip()
            if xuid and name and xuid not in out:
                out[xuid] = name
        return out
    except Exception:
        return {}
    finally:
        conn.close()


def playtime_from_sky_eye(sky_eye_db: Path) -> Dict[str, Dict[str, Any]]:
    """按 PlayerJoin/PlayerQuit 配对推算时长与进出记录。"""
    conn = _sky_eye_connect(sky_eye_db)
    if conn is None:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    try:
        rows = conn.execute(
            "SELECT player_xuid, action, ts, ts_unix FROM sky_eye_events "
            "WHERE action IN ('PlayerJoin', 'PlayerQuit') "
            "AND player_xuid IS NOT NULL AND TRIM(player_xuid) != '' "
            "ORDER BY player_xuid, ts_unix ASC, id ASC"
        ).fetchall()
    except Exception:
        conn.close()
        return {}
    conn.close()

    pending_join: Dict[str, Tuple[str, int]] = {}
    for row in rows:
        xuid = str(row["player_xuid"] or "").strip()
        if not xuid:
            continue
        rec = out.setdefault(
            xuid,
            {
                "total_playtime": 0,
                "session_count": 0,
                "last_join_time": None,
                "last_quit_time": None,
            },
        )
        action = str(row["action"] or "")
        ts = row["ts"]
        try:
            ts_unix = int(row["ts_unix"] or 0)
        except (TypeError, ValueError):
            ts_unix = 0
        if action == "PlayerJoin":
            rec["session_count"] = int(rec["session_count"] or 0) + 1
            rec["last_join_time"] = ts
            pending_join[xuid] = (str(ts) if ts is not None else "", ts_unix)
        elif action == "PlayerQuit":
            rec["last_quit_time"] = ts
            pending = pending_join.pop(xuid, None)
            if pending is not None:
                _join_ts, join_unix = pending
                if ts_unix > join_unix > 0:
                    rec["total_playtime"] = int(rec["total_playtime"] or 0) + (
                        ts_unix - join_unix
                    )
    return out


def placeholder_name(xuid: str) -> str:
    tail = xuid[-6:] if len(xuid) >= 6 else xuid
    return f"xuid:{tail}"


def recovered_uuid(xuid: str) -> str:
    return f"{RECOVERED_UUID_PREFIX}{xuid}"


def _is_empty_text(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def rebuild_player_basic_info(
    db,
    sky_eye_db: Path,
    log: LogFn,
) -> Dict[str, Any]:
    if not db.table_exists("player_basic_info"):
        log("error", "[ARC Core]Legacy rebuild skipped: player_basic_info missing")
        return {"inserted": 0, "updated": 0, "players": 0}

    xuids = collect_xuids_from_core(db) | collect_xuids_from_sky_eye(sky_eye_db)
    names = latest_names_from_sky_eye(sky_eye_db)
    play = playtime_from_sky_eye(sky_eye_db)
    once_op_xuids: Set[str] = set()
    if db.table_exists("player_local_info") and "is_op" in db.get_table_columns(
        "player_local_info"
    ):
        for row in db.query_all(
            "SELECT xuid FROM player_local_info WHERE COALESCE(is_op, 0) = 1"
        ) or []:
            xuid = str((row or {}).get("xuid") or "").strip()
            if xuid:
                once_op_xuids.add(xuid)

    inserted = 0
    updated = 0
    for xuid in sorted(xuids):
        name = names.get(xuid) or placeholder_name(xuid)
        pt = play.get(xuid) or {}
        row_data = {
            "uuid": recovered_uuid(xuid),
            "xuid": xuid,
            "name": name,
            "password": None,
            "inviter_xuid": None,
            "pending_invite_reward_times": 0,
            "default_title_auto_equipped": 0,
            "total_playtime": _as_int(pt.get("total_playtime")),
            "session_count": _as_int(pt.get("session_count")),
            "last_join_time": pt.get("last_join_time"),
            "last_quit_time": pt.get("last_quit_time"),
            "once_op": 1 if xuid in once_op_xuids else 0,
        }
        existing = db.query_one(
            "SELECT * FROM player_basic_info WHERE xuid = ?", (xuid,)
        )
        if existing is None:
            if db.insert("player_basic_info", row_data):
                inserted += 1
            continue
        patch: Dict[str, Any] = {}
        uuid_s = str(existing.get("uuid") or "")
        if _is_empty_text(uuid_s):
            patch["uuid"] = recovered_uuid(xuid)
        exist_name = str(existing.get("name") or "")
        if _is_empty_text(exist_name) or exist_name.startswith("xuid:"):
            if names.get(xuid):
                patch["name"] = names[xuid]
        if _as_int(existing.get("total_playtime")) == 0 and _as_int(
            pt.get("total_playtime")
        ):
            patch["total_playtime"] = _as_int(pt.get("total_playtime"))
        if _as_int(existing.get("session_count")) == 0 and _as_int(
            pt.get("session_count")
        ):
            patch["session_count"] = _as_int(pt.get("session_count"))
        if _is_empty_text(existing.get("last_join_time")) and pt.get("last_join_time"):
            patch["last_join_time"] = pt.get("last_join_time")
        if _is_empty_text(existing.get("last_quit_time")) and pt.get("last_quit_time"):
            patch["last_quit_time"] = pt.get("last_quit_time")
        if xuid in once_op_xuids and _as_int(existing.get("once_op")) == 0:
            patch["once_op"] = 1
        if patch:
            if db.update(
                table="player_basic_info",
                data=patch,
                where="xuid = ?",
                params=(xuid,),
            ):
                updated += 1
    log(
        "info",
        f"[ARC Core]Rebuilt player_basic_info from remnants: "
        f"players={len(xuids)} inserted={inserted} updated={updated}",
    )
    return {
        "players": len(xuids),
        "inserted": inserted,
        "updated": updated,
    }


def maybe_run_legacy_recovery(
    *,
    database_manager,
    setting_manager,
    data_dir: Path,
    sky_eye_db: Path,
    log: LogFn,
    is_sync_client: bool,
) -> Optional[Dict[str, Any]]:
    """配置了旧库路径且未见完成标记时执行一次。从服（远程客户端）跳过。"""
    raw = None
    getter = getattr(setting_manager, "get_existing", None)
    if getter is not None:
        raw = getter(LEGACY_PATHS_SETTING)
    else:
        raw = setting_manager.GetSetting(LEGACY_PATHS_SETTING)
    paths = parse_legacy_paths(raw)
    marker = Path(data_dir) / MARKER_NAME
    if marker.exists():
        return None
    if not paths:
        return None
    if is_sync_client:
        log(
            "warning",
            "[ARC Core] LEGACY_IMPORT_DATABASE_PATHS 已配置，但从服远程客户端模式跳过恢复；"
            "请只在主服（同步中心）执行",
        )
        return None

    log("info", f"[ARC Core]Legacy recovery start, files={len(paths)}")
    import_stats = import_legacy_tables(database_manager, paths, log)
    rebuild_stats = rebuild_player_basic_info(database_manager, sky_eye_db, log)
    result = {
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "files": [str(p) for p in paths],
        "import": import_stats,
        "rebuild": rebuild_stats,
    }
    try:
        marker.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        log("warning", f"[ARC Core]Failed to write {MARKER_NAME}: {e}")
    log(
        "info",
        "[ARC Core]Legacy recovery done: "
        f"inserted={rebuild_stats.get('inserted')} "
        f"updated={rebuild_stats.get('updated')} "
        f"players={rebuild_stats.get('players')}",
    )
    return result
