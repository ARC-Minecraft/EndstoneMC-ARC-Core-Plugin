# -*- coding: utf-8 -*-
"""维度标识：统一为官方 namespaced ID（如 minecraft:overworld），支持自定义维度。"""
from __future__ import annotations

from typing import Any, Optional

# 历史写法 → 官方规范 ID（仅用于写入时规范化与一次性库迁移）
_VANILLA_CANONICAL = {
    "overworld": "minecraft:overworld",
    "minecraft:overworld": "minecraft:overworld",
    "Overworld": "minecraft:overworld",
    "nether": "minecraft:nether",
    "the_nether": "minecraft:nether",
    "thenether": "minecraft:nether",
    "minecraft:nether": "minecraft:nether",
    "minecraft:the_nether": "minecraft:nether",
    "TheNether": "minecraft:nether",
    "theend": "minecraft:the_end",
    "the_end": "minecraft:the_end",
    "end": "minecraft:the_end",
    "minecraft:the_end": "minecraft:the_end",
    "TheEnd": "minecraft:the_end",
}

_VANILLA_LANG_KEYS = {
    "minecraft:overworld": "DIMENSION_OVERWORLD",
    "minecraft:nether": "DIMENSION_NETHER",
    "minecraft:the_end": "DIMENSION_THEEND",
}

_LEGACY_CHUNK_LAND_TABLES = frozenset(
    {
        "chunk_lands_overworld",
        "chunk_lands_thenether",
        "chunk_lands_theend",
        "chunk_lands_nether",
        "chunk_lands_the_nether",
        "chunk_lands_the_end",
        "chunk_lands_end",
    }
)

_DIMENSION_COLUMN_MIGRATE_SQL = {
    "lands": (
        "SELECT DISTINCT dimension AS dim FROM lands",
        "UPDATE lands SET dimension = ? WHERE dimension = ?",
    ),
    "public_warps": (
        "SELECT DISTINCT dimension AS dim FROM public_warps",
        "UPDATE public_warps SET dimension = ? WHERE dimension = ?",
    ),
    "player_homes": (
        "SELECT DISTINCT dimension AS dim FROM player_homes",
        "UPDATE player_homes SET dimension = ? WHERE dimension = ?",
    ),
}


def normalize_dimension_id(dimension: Optional[str]) -> str:
    """将维度字符串升为官方规范 ID；自定义维度原样保留。"""
    raw = str(dimension or "").strip()
    if not raw:
        return ""
    for key in (
        raw,
        raw.lower(),
        "".join(c for c in raw.lower() if c.isalnum() or c == ":"),
    ):
        hit = _VANILLA_CANONICAL.get(key)
        if hit:
            return hit
    return raw


def get_dimension_id(dimension: Any) -> str:
    """从 Dimension 取出规范维度 ID（优先 .id，回退 .name，并规范化）。"""
    if dimension is None:
        return ""
    for attr in ("id", "name"):
        val = getattr(dimension, attr, None)
        if val is not None:
            text = str(val).strip()
            if text:
                return normalize_dimension_id(text)
    return normalize_dimension_id(str(dimension).strip())


def format_dimension_for_command(dimension: Optional[str]) -> str:
    """execute in 直接使用已存储的规范维度 ID。"""
    return normalize_dimension_id(dimension) or "minecraft:overworld"


def chunk_table_suffix(dimension: Optional[str]) -> str:
    """chunk_lands_<suffix>：由规范维度 ID 直接生成（minecraft:overworld → minecraft_overworld）。"""
    raw = (normalize_dimension_id(dimension) or str(dimension or "")).strip().lower()
    return "".join(c if c.isalnum() else "_" for c in raw) or "unknown"


def translate_dimension_display(dimension: Optional[str], language_manager=None) -> str:
    """显示名：原版走语言文件；未知/自定义返回完整 ID（不写入语言文件）。"""
    fallback = str(dimension or "").strip()
    if not fallback:
        return ""
    lang_key = _VANILLA_LANG_KEYS.get(normalize_dimension_id(dimension))
    if not lang_key or language_manager is None:
        return fallback
    try:
        lang_code = getattr(language_manager, "language_code", None)
        lang_dict = getattr(type(language_manager), "language_dict", None) or {}
        bucket = lang_dict.get(lang_code) if lang_code else None
        text = bucket.get(lang_key) if isinstance(bucket, dict) else None
        return text or language_manager.GetText(lang_key) or fallback
    except (AttributeError, KeyError, TypeError):
        return fallback


def migrate_dimension_column(db, table: str, column: str = "dimension") -> int:
    """将表中非规范维度值一次性升为官方 ID。返回更新行数。"""
    sql_pair = _DIMENSION_COLUMN_MIGRATE_SQL.get(table) if column == "dimension" else None
    if not sql_pair or not db.table_exists(table):
        return 0
    select_sql, update_sql = sql_pair
    try:
        rows = db.query_all(select_sql)
    except Exception as e:
        print(f"[ARC Core]migrate_dimension_column read {table}.{column} error: {e}")
        return 0
    total = 0
    for row in rows:
        old_s = str((row.get("dim") if isinstance(row, dict) else None) or "")
        new_s = normalize_dimension_id(old_s)
        if not old_s or not new_s or new_s == old_s:
            continue
        try:
            n = db.execute_and_get_rowcount(update_sql, (new_s, old_s))
            if n > 0:
                total += n
                print(
                    f"[ARC Core]Migrated {table}.{column}: {old_s!r} -> {new_s!r} ({n} row(s))"
                )
        except Exception as e:
            print(
                f"[ARC Core]migrate_dimension_column update {table} "
                f"{old_s!r}->{new_s!r} error: {e}"
            )
    return total


def migrate_spawn_locations_dimensions(db) -> int:
    """spawn_locations 以 dimension 为主键，需单独迁移（避免主键冲突）。"""
    if not db.table_exists("spawn_locations"):
        return 0
    try:
        rows = db.query_all("SELECT * FROM spawn_locations")
    except Exception as e:
        print(f"[ARC Core]migrate_spawn_locations read error: {e}")
        return 0
    total = 0
    for row in rows:
        old_s = str(row.get("dimension") or "")
        new_s = normalize_dimension_id(old_s)
        if not old_s or not new_s or new_s == old_s:
            continue
        try:
            existing = db.query_one(
                "SELECT dimension FROM spawn_locations WHERE dimension = ?",
                (new_s,),
            )
            ok = (
                db.delete("spawn_locations", "dimension = ?", (old_s,))
                if existing
                else db.execute(
                    "UPDATE spawn_locations SET dimension = ? WHERE dimension = ?",
                    (new_s, old_s),
                )
            )
            if ok:
                total += 1
                print(f"[ARC Core]Migrated spawn_locations: {old_s!r} -> {new_s!r}")
        except Exception as e:
            print(
                f"[ARC Core]migrate_spawn_locations {old_s!r}->{new_s!r} error: {e}"
            )
    return total


def has_legacy_chunk_land_tables(db) -> bool:
    """是否仍存在旧版 chunk_lands_* 表名（需重建索引）。"""
    try:
        rows = db.query_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'chunk_lands_%'"
        )
    except Exception:
        return False
    return any(
        isinstance(row, dict) and row.get("name") in _LEGACY_CHUNK_LAND_TABLES
        for row in rows
    )
