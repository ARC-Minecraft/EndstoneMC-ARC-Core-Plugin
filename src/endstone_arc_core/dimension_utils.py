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

# 旧版 chunk_lands_* 表名；检测到后需重建索引
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


def normalize_dimension_id(dimension: Optional[str]) -> str:
    """将维度字符串升为官方规范 ID；自定义维度原样保留。"""
    if not dimension:
        return ""
    raw = str(dimension).strip()
    if not raw:
        return ""
    if raw in _VANILLA_CANONICAL:
        return _VANILLA_CANONICAL[raw]
    lower = raw.lower()
    if lower in _VANILLA_CANONICAL:
        return _VANILLA_CANONICAL[lower]
    compact = "".join(c for c in lower if c.isalnum() or c == ":")
    if compact in _VANILLA_CANONICAL:
        return _VANILLA_CANONICAL[compact]
    return raw


def get_dimension_id(dimension: Any) -> str:
    """从 Dimension 取出规范维度 ID（优先 .id，回退 .name，并规范化）。"""
    if dimension is None:
        return ""
    text = ""
    dim_id = getattr(dimension, "id", None)
    if dim_id is not None:
        text = str(dim_id).strip()
    if not text:
        name = getattr(dimension, "name", None)
        if name is not None:
            text = str(name).strip()
    if not text:
        text = str(dimension).strip()
    return normalize_dimension_id(text)


def format_dimension_for_command(dimension: Optional[str]) -> str:
    """execute in 直接使用已存储的规范维度 ID。"""
    return normalize_dimension_id(dimension) or "minecraft:overworld"


def chunk_table_suffix(dimension: Optional[str]) -> str:
    """chunk_lands_<suffix>：由规范维度 ID 直接生成（minecraft:overworld → minecraft_overworld）。"""
    raw = (normalize_dimension_id(dimension) or str(dimension or "")).strip().lower()
    return "".join(c if c.isalnum() else "_" for c in raw) or "unknown"


def translate_dimension_display(dimension: Optional[str], language_manager=None) -> str:
    """显示名：原版走语言文件；未知/自定义返回完整 ID（不写入语言文件）。"""
    if not dimension:
        return ""
    canonical = normalize_dimension_id(dimension)
    lang_key = _VANILLA_LANG_KEYS.get(canonical)
    if lang_key and language_manager is not None:
        try:
            lang_code = getattr(language_manager, "language_code", None)
            lang_dict = getattr(type(language_manager), "language_dict", None) or {}
            bucket = lang_dict.get(lang_code, {}) if lang_code else {}
            text = bucket.get(lang_key) if isinstance(bucket, dict) else None
            if text:
                return text
            translated = language_manager.GetText(lang_key)
            if translated:
                return translated
        except Exception:
            pass
    return str(dimension).strip()


def migrate_dimension_column(db, table: str, column: str = "dimension") -> int:
    """
    将表中非规范维度值一次性升为官方 ID。
    普通列：UPDATE SET column = new WHERE column = old
    返回更新行数（按行累计）。
    """
    if not db.table_exists(table):
        return 0
    try:
        rows = db.query_all(f"SELECT DISTINCT {column} AS dim FROM {table}")
    except Exception as e:
        print(f"[ARC Core]migrate_dimension_column read {table}.{column} error: {e}")
        return 0
    total = 0
    for row in rows:
        old = row.get("dim") if isinstance(row, dict) else None
        if old is None:
            continue
        old_s = str(old)
        new_s = normalize_dimension_id(old_s)
        if not new_s or new_s == old_s:
            continue
        try:
            n = db.execute_and_get_rowcount(
                f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                (new_s, old_s),
            )
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
    table = "spawn_locations"
    if not db.table_exists(table):
        return 0
    try:
        rows = db.query_all(f"SELECT * FROM {table}")
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
                f"SELECT dimension FROM {table} WHERE dimension = ?", (new_s,)
            )
            if existing:
                if db.delete(table, "dimension = ?", (old_s,)):
                    total += 1
                    print(
                        f"[ARC Core]Migrated spawn_locations: dropped duplicate "
                        f"{old_s!r} (kept {new_s!r})"
                    )
            else:
                ok = db.execute(
                    f"UPDATE {table} SET dimension = ? WHERE dimension = ?",
                    (new_s, old_s),
                )
                if ok:
                    total += 1
                    print(
                        f"[ARC Core]Migrated spawn_locations: {old_s!r} -> {new_s!r}"
                    )
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
    for row in rows:
        name = row.get("name") if isinstance(row, dict) else None
        if name in _LEGACY_CHUNK_LAND_TABLES:
            return True
    return False
