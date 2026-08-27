# -*- coding: utf-8 -*-
"""玩家活动统计：击杀 / 破坏 / 放置累计（本服 SQLite，仅核心写入）。"""
from __future__ import annotations

import threading
from typing import Dict, Optional

from endstone_arc_core.KillRewardConfig import normalize_entity_type_id


class PlayerActivityStats:
    """
    表 player_activity_stats(xuid, stat_key, count)。

    stat_key:
      - kill_total / kill:{entity_id}（含 minecraft:player）
      - break_total / break:{block_id}
      - place_total / place:{block_id}
    """

    TABLE = "player_activity_stats"
    LEGACY_TABLE = "player_achievement_stats"

    def __init__(self, database_manager, logger=None):
        self.database_manager = database_manager
        self.logger = logger
        self._lock = threading.Lock()

    def ensure_tables(self) -> bool:
        try:
            ok = self.database_manager.execute(
                f"CREATE TABLE IF NOT EXISTS {self.TABLE} ("
                "xuid TEXT NOT NULL, "
                "stat_key TEXT NOT NULL, "
                "count INTEGER NOT NULL DEFAULT 0, "
                "PRIMARY KEY (xuid, stat_key)"
                ")"
            )
            if ok is False:
                return False
            if self._migrate_legacy_activity_stats():
                self._drop_legacy_achievement_stats_table()
            return True
        except Exception as e:
            self._log("error", f"[ARC Core]PlayerActivityStats ensure_tables error: {e}")
            return False

    def _log(self, level: str, msg: str) -> None:
        try:
            if self.logger is None:
                return
            fn = getattr(self.logger, level, None)
            if callable(fn):
                fn(msg)
        except Exception:
            pass

    @staticmethod
    def normalize_block_id(block_id: str) -> str:
        s = str(block_id or "").strip()
        if not s:
            return ""
        if ":" in s:
            ns, name = s.split(":", 1)
            return f"{ns.lower()}:{name.lower()}"
        return s.lower()

    @staticmethod
    def _is_air_block(block_id: str) -> bool:
        bid = PlayerActivityStats.normalize_block_id(block_id)
        return (not bid) or bid in ("air", "minecraft:air")

    @staticmethod
    def _map_legacy_stat_key(stat_key: str) -> Optional[str]:
        """旧 player_achievement_stats 键 → 本表键；ach_unlock 等返回 None（由成就插件接管）。"""
        key = str(stat_key or "").strip()
        if not key:
            return None
        if key == "kill_total" or key.startswith("kill:"):
            return key
        if key == "block_break_total":
            return "break_total"
        if key.startswith("block_break:"):
            bid = PlayerActivityStats.normalize_block_id(key.split(":", 1)[1])
            return f"break:{bid}" if bid and not PlayerActivityStats._is_air_block(bid) else None
        if key == "break_total" or key.startswith("break:"):
            return key
        if key == "block_place_total":
            return "place_total"
        if key.startswith("block_place:"):
            bid = PlayerActivityStats.normalize_block_id(key.split(":", 1)[1])
            return f"place:{bid}" if bid and not PlayerActivityStats._is_air_block(bid) else None
        if key == "place_total" or key.startswith("place:"):
            return key
        return None

    def _migrate_legacy_activity_stats(self) -> bool:
        """将旧成就表中的 kill / break / place 键拷贝到本表。成功（含无旧表）返回 True。"""
        try:
            legacy = self.database_manager.query_all(
                f"SELECT xuid, stat_key, count FROM {self.LEGACY_TABLE}"
            )
        except Exception:
            # 旧表不存在或不可读：视为无需再迁，允许 DROP IF EXISTS
            return True
        if not legacy:
            return True
        try:
            migrated = 0
            for row in legacy:
                if isinstance(row, dict):
                    xuid = str(row.get("xuid") or "").strip()
                    key = str(row.get("stat_key") or "").strip()
                    count = int(row.get("count") or 0)
                else:
                    xuid = str(row[0] or "").strip()
                    key = str(row[1] or "").strip()
                    count = int(row[2] or 0)
                mapped = self._map_legacy_stat_key(key)
                if not xuid or not mapped or count <= 0:
                    continue
                existing = self.get_stat(xuid, mapped)
                if existing >= count:
                    continue
                self._set_stat(xuid, mapped, count)
                migrated += 1
            if migrated:
                self._log(
                    "info",
                    f"[ARC Core]Migrated {migrated} activity stat rows from {self.LEGACY_TABLE}",
                )
            return True
        except Exception as e:
            self._log("warning", f"[ARC Core]Legacy activity stat migrate skipped: {e}")
            return False

    def _drop_legacy_achievement_stats_table(self) -> None:
        """活动键已迁入本表、成就解锁已由成就插件接管后，删除旧表。"""
        try:
            self.database_manager.execute(f"DROP TABLE IF EXISTS {self.LEGACY_TABLE}")
            self._log("info", f"[ARC Core]Dropped obsolete table {self.LEGACY_TABLE}")
        except Exception as e:
            self._log("warning", f"[ARC Core]Drop {self.LEGACY_TABLE} skipped: {e}")

    def get_stat(self, xuid: str, stat_key: str) -> int:
        xuid = str(xuid or "").strip()
        stat_key = str(stat_key or "").strip()
        if not xuid or not stat_key:
            return 0
        try:
            row = self.database_manager.query_one(
                f"SELECT count FROM {self.TABLE} WHERE xuid = ? AND stat_key = ?",
                (xuid, stat_key),
            )
            if not row:
                return 0
            if isinstance(row, dict):
                return int(row.get("count") or 0)
            return int(row[0] or 0)
        except Exception:
            return 0

    def get_stats(self, xuid: str, prefix: str = "") -> Dict[str, int]:
        xuid = str(xuid or "").strip()
        if not xuid:
            return {}
        prefix = str(prefix or "")
        try:
            if prefix:
                rows = self.database_manager.query_all(
                    f"SELECT stat_key, count FROM {self.TABLE} WHERE xuid = ? AND stat_key LIKE ?",
                    (xuid, prefix + "%"),
                )
            else:
                rows = self.database_manager.query_all(
                    f"SELECT stat_key, count FROM {self.TABLE} WHERE xuid = ?",
                    (xuid,),
                )
            out: Dict[str, int] = {}
            for row in rows or []:
                if isinstance(row, dict):
                    key = str(row.get("stat_key") or "")
                    count = int(row.get("count") or 0)
                else:
                    key = str(row[0] or "")
                    count = int(row[1] or 0)
                if key:
                    out[key] = count
            return out
        except Exception:
            return {}

    def _set_stat(self, xuid: str, stat_key: str, count: int) -> None:
        self.database_manager.execute(
            f"INSERT OR IGNORE INTO {self.TABLE} (xuid, stat_key, count) VALUES (?, ?, 0)",
            (xuid, stat_key),
        )
        self.database_manager.execute(
            f"UPDATE {self.TABLE} SET count = ? WHERE xuid = ? AND stat_key = ?",
            (int(count), xuid, stat_key),
        )

    def inc_stat(
        self, xuid: str, stat_key: str, delta: int = 1, *, return_count: bool = True
    ) -> int:
        xuid = str(xuid or "").strip()
        stat_key = str(stat_key or "").strip()
        delta = int(delta or 0)
        if not xuid or not stat_key or delta == 0:
            return self.get_stat(xuid, stat_key) if (return_count and xuid and stat_key) else 0
        with self._lock:
            self.database_manager.execute(
                f"INSERT OR IGNORE INTO {self.TABLE} (xuid, stat_key, count) VALUES (?, ?, 0)",
                (xuid, stat_key),
            )
            self.database_manager.execute(
                f"UPDATE {self.TABLE} SET count = count + ? WHERE xuid = ? AND stat_key = ?",
                (delta, xuid, stat_key),
            )
            if return_count:
                return self.get_stat(xuid, stat_key)
            return 0

    def record_kill(self, xuid: str, entity_type: str) -> None:
        xuid = str(xuid or "").strip()
        entity_type = normalize_entity_type_id(entity_type)
        if not xuid or not entity_type:
            return
        self.inc_stat(xuid, "kill_total", 1, return_count=False)
        self.inc_stat(xuid, f"kill:{entity_type}", 1, return_count=False)

    def record_block_break(self, xuid: str, block_id: str) -> None:
        xuid = str(xuid or "").strip()
        block_id = self.normalize_block_id(block_id)
        if not xuid or self._is_air_block(block_id):
            return
        self.inc_stat(xuid, "break_total", 1, return_count=False)
        self.inc_stat(xuid, f"break:{block_id}", 1, return_count=False)

    def record_block_place(self, xuid: str, block_id: str) -> None:
        xuid = str(xuid or "").strip()
        block_id = self.normalize_block_id(block_id)
        if not xuid or self._is_air_block(block_id):
            return
        self.inc_stat(xuid, "place_total", 1, return_count=False)
        self.inc_stat(xuid, f"place:{block_id}", 1, return_count=False)

    def get_kill_count(self, xuid: str, entity_id: str = "*") -> int:
        entity_id = str(entity_id or "*").strip()
        if entity_id == "*":
            return self.get_stat(xuid, "kill_total")
        return self.get_stat(xuid, f"kill:{normalize_entity_type_id(entity_id)}")

    def get_block_break_count(self, xuid: str, block_id: str = "*") -> int:
        block_id = str(block_id or "*").strip()
        if block_id == "*":
            return self.get_stat(xuid, "break_total")
        return self.get_stat(xuid, f"break:{self.normalize_block_id(block_id)}")

    def get_block_place_count(self, xuid: str, block_id: str = "*") -> int:
        block_id = str(block_id or "*").strip()
        if block_id == "*":
            return self.get_stat(xuid, "place_total")
        return self.get_stat(xuid, f"place:{self.normalize_block_id(block_id)}")
