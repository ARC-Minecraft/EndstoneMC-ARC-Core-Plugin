# -*- coding: utf-8 -*-
"""本地 DB 变更 → 同步中心镜像（上行）辅助逻辑。"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 可同步表的主键（用于写后回读整行再 upsert）
SYNC_TABLE_PRIMARY_KEYS: Dict[str, Tuple[str, ...]] = {
    "player_basic_info": ("xuid",),
    "player_economy": ("xuid",),
    "player_title": ("xuid",),
    "title_definitions": ("title",),
    "player_title_unlock_time": ("xuid", "title"),
    "player_title_equipped": ("xuid",),
    "guilds": ("id",),
    "guild_members": ("guild_id", "xuid"),
    "guild_invites": ("id",),
}


def is_mutating_sql(sql: str) -> bool:
    s = (sql or "").lstrip().upper()
    return s.startswith("INSERT") or s.startswith("UPDATE") or s.startswith("DELETE")


def parse_delete_where(sql: str) -> Optional[str]:
    m = re.search(r"\bDELETE\s+FROM\s+[`\"\[]?\w+[\]\"`]?\s+WHERE\s+(.+)$", sql, re.I | re.S)
    return m.group(1).strip() if m else None


def split_update_where(sql: str) -> Tuple[Optional[str], int]:
    """返回 (WHERE 子句, SET 段中的 ? 数量)。"""
    m = re.search(
        r"\bUPDATE\s+[`\"\[]?\w+[\]\"`]?\s+SET\s+(.+?)\s+WHERE\s+(.+)$",
        sql,
        re.I | re.S,
    )
    if not m:
        return None, 0
    set_part, where_part = m.group(1), m.group(2)
    return where_part.strip(), set_part.count("?")


def parse_insert_columns_and_values(
    sql: str, params: Sequence[Any]
) -> Optional[Dict[str, Any]]:
    """从简单 INSERT INTO t (cols) VALUES (?,?,?) 还原行字典。"""
    m = re.search(
        r"\bINSERT\s+(?:OR\s+\w+\s+)?INTO\s+[`\"\[]?\w+[\]\"`]?\s*"
        r"\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
        sql,
        re.I | re.S,
    )
    if not m:
        return None
    cols = [c.strip().strip('`"[]') for c in m.group(1).split(",")]
    placeholders = m.group(2).count("?")
    if placeholders != len(cols) or placeholders != len(params):
        return None
    return {cols[i]: params[i] for i in range(len(cols))}


def resolve_rows_after_write(
    db,
    table: str,
    *,
    data: Optional[Dict[str, Any]] = None,
    where: Optional[str] = None,
    params: Optional[Sequence[Any]] = None,
    sql: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    在本地写成功后，尽量定位受影响行并 SELECT * 得到完整行，供中心 upsert。
    """
    table = table.lower()
    params = tuple(params or ())

    if sql:
        upper = sql.lstrip().upper()
        if upper.startswith("DELETE"):
            return []
        if upper.startswith("INSERT"):
            row = parse_insert_columns_and_values(sql, params)
            if row:
                return _refetch_by_pk_or_row(db, table, row)
            return []
        if upper.startswith("UPDATE"):
            where_clause, set_q = split_update_where(sql)
            if not where_clause:
                return []
            where_params = params[set_q:]
            return db.query_all(f"SELECT * FROM {table} WHERE {where_clause}", where_params) or []

    if where:
        return db.query_all(f"SELECT * FROM {table} WHERE {where}", params) or []

    if data:
        return _refetch_by_pk_or_row(db, table, data)

    return []


def _refetch_by_pk_or_row(db, table: str, row: Dict[str, Any]) -> List[Dict[str, Any]]:
    pks = SYNC_TABLE_PRIMARY_KEYS.get(table)
    if pks and all(k in row and row[k] is not None for k in pks):
        where = " AND ".join(f"{k} = ?" for k in pks)
        params = tuple(row[k] for k in pks)
        found = db.query_all(f"SELECT * FROM {table} WHERE {where}", params) or []
        if found:
            return found
    # 回退：用写入字典本身（INSERT OR REPLACE 时通常足够）
    return [dict(row)]
