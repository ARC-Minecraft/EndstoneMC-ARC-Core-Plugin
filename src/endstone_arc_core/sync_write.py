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

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
    return m.group(2).strip(), m.group(1).count("?")


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
    if m.group(2).count("?") != len(cols) or len(cols) != len(params):
        return None
    return dict(zip(cols, params))


def _select_rows(db, table: str, where: str, params: Sequence[Any]) -> List[Dict[str, Any]]:
    """仅允许同步表白名单内的表名；值一律参数化。"""
    if (
        table not in SYNC_TABLE_PRIMARY_KEYS
        or not _IDENT_RE.fullmatch(table)
        or not where
        or ";" in where
    ):
        return []
    query = "SELECT * FROM " + table + " WHERE " + where  # nosec B608
    return db.query_all(query, tuple(params)) or []


def resolve_rows_after_write(
    db,
    table: str,
    *,
    data: Optional[Dict[str, Any]] = None,
    where: Optional[str] = None,
    params: Optional[Sequence[Any]] = None,
    sql: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """本地写成功后定位受影响行并 SELECT *，供中心 upsert。"""
    table = table.lower()
    params_t = tuple(params or ())
    if table not in SYNC_TABLE_PRIMARY_KEYS:
        return []

    if sql:
        upper = sql.lstrip().upper()
        if upper.startswith("DELETE"):
            return []
        if upper.startswith("INSERT"):
            row = parse_insert_columns_and_values(sql, params_t)
            return _refetch_by_pk_or_row(db, table, row) if row else []
        if upper.startswith("UPDATE"):
            where_clause, set_q = split_update_where(sql)
            return (
                _select_rows(db, table, where_clause, params_t[set_q:])
                if where_clause
                else []
            )

    if where:
        return _select_rows(db, table, where, params_t)
    return _refetch_by_pk_or_row(db, table, data) if data else []


def _refetch_by_pk_or_row(db, table: str, row: Dict[str, Any]) -> List[Dict[str, Any]]:
    pks = SYNC_TABLE_PRIMARY_KEYS.get(table)
    if pks and all(row.get(k) is not None for k in pks):
        found = _select_rows(
            db,
            table,
            " AND ".join(k + " = ?" for k in pks),
            tuple(row[k] for k in pks),
        )
        if found:
            return found
    return [dict(row)]


def iter_mirror_write_actions(db, kind: str, table: str, **kwargs):
    """产出镜像动作：("delete", where, params) 或 ("insert", row)。"""
    sql = str(kwargs.get("sql") or "")
    if kind == "delete" or sql.lstrip().upper().startswith("DELETE"):
        where = kwargs.get("where") or parse_delete_where(sql)
        if where:
            yield ("delete", where, list(kwargs.get("params") or ()))
        return
    yield from (
        ("insert", row)
        for row in resolve_rows_after_write(db, table, **kwargs)
        if row
    )
