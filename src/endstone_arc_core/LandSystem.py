# -*- coding: utf-8 -*-
"""领地系统：建表、区块索引、CRUD、子领地、权限设置的全部数据/逻辑层"""
import json
from typing import Any, Callable, Dict, Optional, Set


class LandSystem:
    """领地系统：负责 lands / sub_lands / chunk_lands_* 表的所有数据操作，不包含 UI 逻辑。"""

    # 领地主人存于 lands.owner_xuid / sub_lands.owner_xuid（列名未改，值为下列格式）：
    # - 玩家：Player_<xuid>
    # - 公会：GUILD_<guild_id>
    # - 公共：PUBLIC（旧版曾用 "0"，启动时自动升级）
    LAND_OWNER_PUBLIC = "PUBLIC"
    LAND_OWNER_PLAYER_PREFIX = "Player_"
    LAND_OWNER_GUILD_PREFIX = "GUILD_"
    # 兼容旧插件里对「公共领地主键」的引用（新值为 PUBLIC，不再使用 "0"）
    PUBLIC_LAND_OWNER_XUID = LAND_OWNER_PUBLIC

    # 未开放展示框（allow_frame）时禁止交互/破坏的方块；配置项留空则使用此集合
    _DEFAULT_PUBLIC_LAND_INTERACT_BLOCK_BLACKLIST = frozenset({
        "minecraft:frame",
        "minecraft:glow_frame",
        "minecraft:oak_shelf",
        "minecraft:spruce_shelf",
        "minecraft:birch_shelf",
        "minecraft:jungle_shelf",
        "minecraft:acacia_shelf",
        "minecraft:dark_oak_shelf",
        "minecraft:mangrove_shelf",
        "minecraft:cherry_shelf",
        "minecraft:pale_oak_shelf",
        "minecraft:bamboo_shelf",
        "minecraft:crimson_shelf",
        "minecraft:warped_shelf",
    })

    @staticmethod
    def is_public_land_owner(value: Any) -> bool:
        s = str(value or "").strip()
        if s == LandSystem.LAND_OWNER_PUBLIC:
            return True
        return s == "0"

    @staticmethod
    def land_owner_key_player(xuid: Any) -> str:
        return f"{LandSystem.LAND_OWNER_PLAYER_PREFIX}{str(xuid).strip()}"

    @staticmethod
    def land_owner_key_guild(guild_id: Any) -> str:
        return f"{LandSystem.LAND_OWNER_GUILD_PREFIX}{int(guild_id)}"

    @staticmethod
    def parse_land_owner_player_xuid(owner_key: Any) -> Optional[str]:
        s = str(owner_key or "").strip()
        p = LandSystem.LAND_OWNER_PLAYER_PREFIX
        if not s.startswith(p):
            return None
        rest = s[len(p) :].strip()
        return rest if rest else None

    @staticmethod
    def parse_land_owner_guild_id(owner_key: Any) -> Optional[int]:
        s = str(owner_key or "").strip()
        p = LandSystem.LAND_OWNER_GUILD_PREFIX
        if not s.startswith(p):
            return None
        rest = s[len(p) :].strip()
        if not rest:
            return None
        try:
            return int(rest)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def normalize_owner_key_for_write(raw: Any) -> str:
        """写入库前规范化主人键；裸字符串视为玩家 XUID；GUILD_/Player_ 保持前缀。"""
        s = str(raw or "").strip()
        if not s:
            return ""
        if s == "0" or s.upper() == "PUBLIC":
            return LandSystem.LAND_OWNER_PUBLIC
        if s.startswith(LandSystem.LAND_OWNER_GUILD_PREFIX):
            return s
        if s.startswith(LandSystem.LAND_OWNER_PLAYER_PREFIX):
            rest = s[len(LandSystem.LAND_OWNER_PLAYER_PREFIX) :].strip()
            return (
                f"{LandSystem.LAND_OWNER_PLAYER_PREFIX}{rest}" if rest else ""
            )
        return LandSystem.land_owner_key_player(s)

    def __init__(self, database_manager, setting_manager, logger=None):
        self.db = database_manager
        self.setting_manager = setting_manager
        self.logger = logger
        self._persistent_error_cb: Optional[
            Callable[[str, str, Optional[BaseException]], None]
        ] = None
        self._load_config()

    def set_persistent_error_callback(
        self, callback: Optional[Callable[[str, str, Optional[BaseException]], None]]
    ) -> None:
        self._persistent_error_cb = callback

    def _emit_persistent_error(
        self, error_code: str, detail: str, exc: Optional[BaseException] = None
    ) -> None:
        if self._persistent_error_cb:
            try:
                self._persistent_error_cb(error_code, detail, exc)
            except Exception as cb_err:
                self._log("warning", f"persistent error callback failed: {cb_err}")

    def _load_config(self):
        self.land_min_distance = self._parse_int("MIN_LAND_DISTANCE", 0)
        self.land_price = self._parse_int("LAND_PRICE", 100)
        self.land_sell_refund_coefficient = self._parse_float("LAND_SELL_REFUND_COEFFICIENT", 0.9)
        self.land_min_size = self._parse_int("LAND_MIN_SIZE", 5)

    def reload_config(self):
        self._load_config()

    def set_logger(self, logger):
        self.logger = logger

    def _parse_int(self, key: str, default: int) -> int:
        try:
            return int(self.setting_manager.GetSetting(key))
        except (ValueError, TypeError):
            return default

    def _parse_float(self, key: str, default: float) -> float:
        try:
            return float(self.setting_manager.GetSetting(key))
        except (ValueError, TypeError):
            return default

    def _log(self, level: str, message: str):
        if self.logger:
            if level == "error":
                self.logger.error(message)
            elif level == "warning":
                self.logger.warning(message)
            else:
                self.logger.info(message)
        else:
            print(f"[{level.upper()}] {message}")

    # ─── 工具 ─────────────────────────────────────────────────────────────────

    def _column_exists(self, table: str, column: str) -> bool:
        """检查表中是否存在指定列"""
        if table not in ("lands", "sub_lands"):
            return False
        try:
            columns_info = self.db.query_all("PRAGMA table_info(" + table + ")")  # nosec B608
            return any(col["name"] == column for col in columns_info)
        except Exception:
            return False

    def _migrate_land_owner_keys_in_table(self, table: str) -> None:
        """旧库：公共领地 owner_xuid 由 0 升为 PUBLIC；玩家由裸 XUID 升为 Player_<xuid>；已有 GUILD_ 不动。"""
        if table not in ("lands", "sub_lands"):
            return
        try:
            if not self.db.table_exists(table) or not self._column_exists(
                table, "owner_xuid"
            ):
                return
            if table == "lands":
                n0 = self.db.execute_and_get_rowcount(
                    "UPDATE lands SET owner_xuid = ? WHERE owner_xuid = ?",
                    (self.LAND_OWNER_PUBLIC, "0"),
                )
                n1 = self.db.execute_and_get_rowcount(
                    "UPDATE lands SET owner_xuid = ? || owner_xuid "
                    "WHERE owner_xuid != ? AND owner_xuid NOT LIKE ? AND owner_xuid NOT LIKE ?",
                    (
                        self.LAND_OWNER_PLAYER_PREFIX,
                        self.LAND_OWNER_PUBLIC,
                        f"{self.LAND_OWNER_PLAYER_PREFIX}%",
                        f"{self.LAND_OWNER_GUILD_PREFIX}%",
                    ),
                )
            else:
                n0 = self.db.execute_and_get_rowcount(
                    "UPDATE sub_lands SET owner_xuid = ? WHERE owner_xuid = ?",
                    (self.LAND_OWNER_PUBLIC, "0"),
                )
                n1 = self.db.execute_and_get_rowcount(
                    "UPDATE sub_lands SET owner_xuid = ? || owner_xuid "
                    "WHERE owner_xuid != ? AND owner_xuid NOT LIKE ? AND owner_xuid NOT LIKE ?",
                    (
                        self.LAND_OWNER_PLAYER_PREFIX,
                        self.LAND_OWNER_PUBLIC,
                        f"{self.LAND_OWNER_PLAYER_PREFIX}%",
                        f"{self.LAND_OWNER_GUILD_PREFIX}%",
                    ),
                )
            touched = 0
            for n in (n0, n1):
                if isinstance(n, int) and n > 0:
                    touched += n
            if touched:
                print(
                    f"[ARC Core]Migrated owner_xuid in {table} ({touched} row(s) updated)"
                )
        except Exception as e:
            print(f"[ARC Core]Migrate owner_xuid in {table} error: {str(e)}")

    def _get_dimension_table(self, dimension: str) -> str:
        from endstone_arc_core.dimension_utils import chunk_table_suffix

        return f"chunk_lands_{chunk_table_suffix(dimension)}"

    def _get_chunk_key(self, x: int, z: int) -> str:
        return f"{x >> 4}_{z >> 4}"

    def _get_affected_chunks(
        self, min_x: int, max_x: int, min_z: int, max_z: int
    ) -> Set[str]:
        keys: Set[str] = set()
        for cx in range(min_x >> 4, (max_x >> 4) + 1):
            for cz in range(min_z >> 4, (max_z >> 4) + 1):
                keys.add(f"{cx}_{cz}")
        return keys

    def _ensure_dimension_table(self, dimension: str) -> bool:
        table = self._get_dimension_table(dimension)
        if self.db.table_exists(table):
            return True
        return self.db.create_table(
            table,
            {
                "chunk_key": "TEXT PRIMARY KEY",
                "land_ids": "TEXT NOT NULL",
            },
        )

    def _register_land_to_chunk_mapping(
        self,
        land_id: int,
        dimension: str,
        min_x: int,
        max_x: int,
        min_z: int,
        max_z: int,
    ) -> bool:
        try:
            table = self._get_dimension_table(dimension)
            for chunk_key in self._get_affected_chunks(min_x, max_x, min_z, max_z):
                existing = self.db.query_one(
                    f"SELECT land_ids FROM {table} WHERE chunk_key = ?", (chunk_key,)
                )
                if existing:
                    ids = json.loads(existing["land_ids"])
                    ids.append(land_id)
                    self.db.update(
                        table, {"land_ids": json.dumps(ids)}, "chunk_key = ?", (chunk_key,)
                    )
                else:
                    self.db.insert(
                        table,
                        {"chunk_key": chunk_key, "land_ids": json.dumps([land_id])},
                    )
            return True
        except Exception as e:
            self._log("error", f"Register land to chunk mapping error: {str(e)}")
            return False

    # ─── 建表与升级 ──────────────────────────────────────────────────────────

    def init_land_tables(self) -> bool:
        try:
            land_fields = {
                "land_id": "INTEGER PRIMARY KEY AUTOINCREMENT",
                "owner_xuid": "TEXT NOT NULL",
                "land_name": "TEXT NOT NULL",
                "dimension": "TEXT NOT NULL",
                "min_x": "INTEGER NOT NULL",
                "max_x": "INTEGER NOT NULL",
                "min_y": "INTEGER NOT NULL DEFAULT 0",
                "max_y": "INTEGER NOT NULL DEFAULT 255",
                "min_z": "INTEGER NOT NULL",
                "max_z": "INTEGER NOT NULL",
                "tp_x": "REAL NOT NULL",
                "tp_y": "REAL NOT NULL",
                "tp_z": "REAL NOT NULL",
                "shared_users": "TEXT",
                "allow_explosion": "INTEGER DEFAULT 0",
                "allow_public_interact": "INTEGER DEFAULT 0",
                "allow_actor_interaction": "INTEGER DEFAULT 0",
                "allow_actor_damage": "INTEGER DEFAULT 0",
                "allow_frame": "INTEGER DEFAULT 0",
                "owner_paid_money": "REAL DEFAULT 0",
                "allow_non_public_land": "INTEGER DEFAULT 0",
                "allow_guild_member_interact": "INTEGER DEFAULT 0",
                "for_sale": "INTEGER DEFAULT 0",
                "sale_price": "REAL DEFAULT 0",
            }
            if self.db.table_exists("lands"):
                self._upgrade_land_table()
            else:
                success = self.db.create_table("lands", land_fields)
                if not success:
                    return False
                print("[ARC Core]Created new land table with all fields")
            self._migrate_land_owner_keys_in_table("lands")
            from endstone_arc_core.dimension_utils import (
                migrate_dimension_column,
                has_legacy_chunk_land_tables,
            )

            migrated = migrate_dimension_column(self.db, "lands", "dimension")
            if migrated > 0 or has_legacy_chunk_land_tables(self.db):
                ok, n_dims, n_lands, err = self.rebuild_chunk_land_mapping()
                if ok:
                    print(
                        f"[ARC Core]Rebuilt chunk_lands after dimension migrate "
                        f"(dims={n_dims}, lands={n_lands})"
                    )
                else:
                    print(f"[ARC Core]Rebuild chunk_lands failed: {err}")
            return True
        except Exception as e:
            print(f"[ARC Core]Init land tables error: {str(e)}")
            return False

    def _upgrade_land_table(self) -> bool:
        try:
            upgrades = (
                ("allow_explosion", "ALTER TABLE lands ADD COLUMN allow_explosion INTEGER DEFAULT 0"),
                ("allow_public_interact", "ALTER TABLE lands ADD COLUMN allow_public_interact INTEGER DEFAULT 0"),
                ("allow_actor_interaction", "ALTER TABLE lands ADD COLUMN allow_actor_interaction INTEGER DEFAULT 0"),
                ("allow_actor_damage", "ALTER TABLE lands ADD COLUMN allow_actor_damage INTEGER DEFAULT 0"),
                ("allow_frame", "ALTER TABLE lands ADD COLUMN allow_frame INTEGER DEFAULT 0"),
            )
            for col, sql in upgrades:
                if not self._column_exists("lands", col):
                    ok = self.db.execute(sql)
                    msg = f"added {col}" if ok else f"failed to add {col}"
                    print(f"[ARC Core]Upgraded land table: {msg}")

            if not self._column_exists("lands", "owner_paid_money"):
                ok = self.db.execute(
                    "ALTER TABLE lands ADD COLUMN owner_paid_money REAL DEFAULT 0"
                )
                if ok:
                    upgrade_price = self._parse_float("LAND_PRICE", 100.0)
                    self.db.execute(
                        "UPDATE lands SET owner_paid_money = (max_x - min_x + 1) * (max_z - min_z + 1) * ?",
                        (upgrade_price,),
                    )
                    print(
                        f"[ARC Core]owner_paid_money initialized (land_price={upgrade_price}, one-time migration only)"
                    )
                else:
                    print("[ARC Core]Failed to add owner_paid_money column")

            _add_col("allow_non_public_land", "INTEGER DEFAULT 0")
            _add_col("allow_guild_member_interact", "INTEGER DEFAULT 0")
            _add_col("for_sale", "INTEGER DEFAULT 0")
            _add_col("sale_price", "REAL DEFAULT 0")
            _add_col("min_y", "INTEGER NOT NULL DEFAULT 0")
            _add_col("max_y", "INTEGER NOT NULL DEFAULT 255")
            return True
        except Exception as e:
            print(f"[ARC Core]Upgrade land table error: {str(e)}")
            return True  # 不影响启动

    def init_sub_land_table(self) -> bool:
        try:
            fields = {
                "sub_land_id": "INTEGER PRIMARY KEY AUTOINCREMENT",
                "parent_land_id": "INTEGER NOT NULL",
                "owner_xuid": "TEXT NOT NULL",
                "sub_land_name": "TEXT NOT NULL",
                "min_x": "INTEGER NOT NULL",
                "max_x": "INTEGER NOT NULL",
                "min_y": "INTEGER NOT NULL DEFAULT 0",
                "max_y": "INTEGER NOT NULL DEFAULT 255",
                "min_z": "INTEGER NOT NULL",
                "max_z": "INTEGER NOT NULL",
                "shared_users": 'TEXT DEFAULT "[]"',
            }
            ok = self.db.create_table("sub_lands", fields)
            self._migrate_land_owner_keys_in_table("sub_lands")
            return ok
        except Exception as e:
            print(f"[ARC Core]Init sub_land table error: {str(e)}")
            return False

    def rebuild_chunk_land_mapping(self) -> tuple:
        """重建所有区块-领地映射表。返回 (success, num_dims, num_lands, error_str)"""
        try:
            tables = self.db.query_all(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'chunk_lands_%'"
            )
            for row in tables:
                name = row.get("name") if isinstance(row, dict) else None
                if (
                    not isinstance(name, str)
                    or not name.startswith("chunk_lands_")
                    or not all(c.isalnum() or c == "_" for c in name)
                ):
                    continue
                self.db.execute("DROP TABLE IF EXISTS " + name)  # nosec B608

            lands = self.db.query_all(
                "SELECT land_id, dimension, min_x, max_x, min_z, max_z FROM lands"
            )
            if not lands:
                return True, 0, 0, None

            dimensions_done: Set[str] = set()
            for land in lands:
                dim = land["dimension"]
                if dim not in dimensions_done:
                    self._ensure_dimension_table(dim)
                    dimensions_done.add(dim)
                self._register_land_to_chunk_mapping(
                    land["land_id"], dim,
                    land["min_x"], land["max_x"],
                    land["min_z"], land["max_z"],
                )
            return True, len(dimensions_done), len(lands), None
        except Exception as e:
            return False, 0, 0, str(e)

    # ─── 主领地 CRUD ─────────────────────────────────────────────────────────

    def create_land(
        self,
        owner_xuid: str,
        land_name: str,
        dimension: str,
        min_x: int,
        max_x: int,
        min_y: int,
        max_y: int,
        min_z: int,
        max_z: int,
        tp_x: float,
        tp_y: float,
        tp_z: float,
        owner_paid_money: float = 0.0,
    ) -> Optional[int]:
        try:
            from endstone_arc_core.dimension_utils import normalize_dimension_id

            owner_xuid = self.normalize_owner_key_for_write(owner_xuid)
            if not owner_xuid:
                return None
            dimension = normalize_dimension_id(dimension)
            if not self._ensure_dimension_table(dimension):
                return None
            self.db.execute(
                "INSERT INTO lands "
                "(owner_xuid, land_name, dimension, min_x, max_x, min_y, max_y, min_z, max_z, "
                "tp_x, tp_y, tp_z, shared_users, allow_explosion, allow_public_interact, "
                "allow_guild_member_interact, owner_paid_money, for_sale, sale_price) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    owner_xuid, land_name, dimension,
                    min_x, max_x, min_y, max_y, min_z, max_z,
                    tp_x, tp_y, tp_z,
                    "[]", 0, 0, 0, float(owner_paid_money),
                    0, 0.0,
                ),
            )
            result = self.db.query_one("SELECT last_insert_rowid() as land_id")
            land_id = result["land_id"]
            if not self._register_land_to_chunk_mapping(land_id, dimension, min_x, max_x, min_z, max_z):
                self._log("error", f"Create land: chunk mapping failed, land_id={land_id}")
            return land_id
        except Exception as e:
            self._log("error", f"Create land error: {str(e)}")
            return None

    def get_land_at_pos(
        self, dimension: str, x: int, z: int, y: int = None
    ) -> Optional[int]:
        try:
            x, z = int(x), int(z)
            if not self._ensure_dimension_table(dimension):
                return None
            table = self._get_dimension_table(dimension)
            chunk_key = self._get_chunk_key(x, z)
            chunk_data = self.db.query_one(
                f"SELECT land_ids FROM {table} WHERE chunk_key = ?", (chunk_key,)
            )
            if not chunk_data:
                return None
            land_ids = json.loads(chunk_data["land_ids"])
            public_land_id = None
            for land_id in land_ids:
                land = self.db.query_one(
                    "SELECT * FROM lands WHERE land_id = ?", (land_id,)
                )
                if not land:
                    continue
                if not (land["min_x"] <= x <= land["max_x"] and land["min_z"] <= z <= land["max_z"]):
                    continue
                if y is not None:
                    if not (land.get("min_y", 0) <= int(y) <= land.get("max_y", 255)):
                        continue
                if not self.is_public_land_owner(land["owner_xuid"]):
                    return land_id
                public_land_id = land_id
            return public_land_id
        except Exception as e:
            self._log("error", f"Get land at pos error: {str(e)}")
            return None

    def _unregister_land_from_chunk_mapping(
        self,
        land_id: int,
        dimension: str,
        min_x: int,
        max_x: int,
        min_z: int,
        max_z: int,
    ) -> None:
        """从 chunk_lands_* 索引中移除该领地 ID（不删除 lands 表行）。"""
        try:
            table = self._get_dimension_table(dimension)
            for chunk_key in self._get_affected_chunks(min_x, max_x, min_z, max_z):
                row = self.db.query_one(
                    f"SELECT land_ids FROM {table} WHERE chunk_key = ?", (chunk_key,)
                )
                if row:
                    ids = json.loads(row["land_ids"])
                    if land_id in ids:
                        ids.remove(land_id)
                        if ids:
                            self.db.update(
                                table,
                                {"land_ids": json.dumps(ids)},
                                "chunk_key = ?",
                                (chunk_key,),
                            )
                        else:
                            self.db.delete(table, "chunk_key = ?", (chunk_key,))
        except Exception as e:
            self._log("error", f"Unregister land from chunk mapping error: {str(e)}")

    def delete_land(self, land_id: int) -> bool:
        try:
            land = self.db.query_one("SELECT * FROM lands WHERE land_id = ?", (land_id,))
            if not land:
                return False
            self._unregister_land_from_chunk_mapping(
                land_id,
                land["dimension"],
                land["min_x"],
                land["max_x"],
                land["min_z"],
                land["max_z"],
            )
            return self.db.delete("lands", "land_id = ?", (land_id,))
        except Exception as e:
            self._log("error", f"Delete land error: {str(e)}")
            return False

    def update_land_bounds(
        self,
        land_id: int,
        min_x: int,
        max_x: int,
        min_y: int,
        max_y: int,
        min_z: int,
        max_z: int,
        owner_paid_money: Optional[float] = None,
    ) -> bool:
        """更新领地范围并重建 chunk 索引；land_id 不变。owner_paid_money 为 None 时不改该列。"""
        try:
            min_x, max_x = min(min_x, max_x), max(min_x, max_x)
            min_y, max_y = min(min_y, max_y), max(min_y, max_y)
            min_z, max_z = min(min_z, max_z), max(min_z, max_z)
            land = self.db.query_one("SELECT * FROM lands WHERE land_id = ?", (land_id,))
            if not land:
                return False
            dim = land["dimension"]
            self._unregister_land_from_chunk_mapping(
                land_id,
                dim,
                land["min_x"],
                land["max_x"],
                land["min_z"],
                land["max_z"],
            )
            if owner_paid_money is not None:
                self.db.execute(
                    "UPDATE lands SET min_x = ?, max_x = ?, min_y = ?, max_y = ?, min_z = ?, max_z = ?, "
                    "owner_paid_money = ? WHERE land_id = ?",
                    (
                        min_x,
                        max_x,
                        min_y,
                        max_y,
                        min_z,
                        max_z,
                        float(owner_paid_money),
                        land_id,
                    ),
                )
            else:
                self.db.execute(
                    "UPDATE lands SET min_x = ?, max_x = ?, min_y = ?, max_y = ?, min_z = ?, max_z = ? "
                    "WHERE land_id = ?",
                    (min_x, max_x, min_y, max_y, min_z, max_z, land_id),
                )
            if not self._register_land_to_chunk_mapping(
                land_id, dim, min_x, max_x, min_z, max_z
            ):
                self._log(
                    "error",
                    f"update_land_bounds: chunk mapping failed land_id={land_id}",
                )
                return False
            return True
        except Exception as e:
            self._log("error", f"update_land_bounds error: {str(e)}")
            return False

    def check_land_availability(
        self,
        dimension: str,
        min_x: int,
        max_x: int,
        min_y: int,
        max_y: int,
        min_z: int,
        max_z: int,
        exclude_land_ids: Optional[Set[int]] = None,
    ) -> tuple:
        """检查领地范围是否可用。返回 (available, reason_key_or_None, overlapping_ids_or_None)

        exclude_land_ids：重设范围时排除当前领地自身与其它已排除 ID，避免与自身旧范围判重叠。
        """
        try:
            min_x, max_x = min(min_x, max_x), max(min_x, max_x)
            min_y, max_y = min(min_y, max_y), max(min_y, max_y)
            min_z, max_z = min(min_z, max_z), max(min_z, max_z)
            d = self.land_min_distance
            check_min_x, check_max_x = min_x - d, max_x + d
            check_min_z, check_max_z = min_z - d, max_z + d
            affected = self._get_affected_chunks(check_min_x, check_max_x, check_min_z, check_max_z)
            if not self._ensure_dimension_table(dimension):
                self._emit_persistent_error(
                    "LAND_SYS1",
                    f"check_land_availability _ensure_dimension_table failed dimension={dimension!r}",
                    None,
                )
                return False, "SYSTEM_ERROR", None
            table = self._get_dimension_table(dimension)
            nearby_ids: Set[int] = set()
            for chunk_key in affected:
                row = self.db.query_one(
                    f"SELECT land_ids FROM {table} WHERE chunk_key = ?", (chunk_key,)
                )
                if row:
                    nearby_ids.update(json.loads(row["land_ids"]))
            overlapping = []
            for land_id in nearby_ids:
                if exclude_land_ids and land_id in exclude_land_ids:
                    continue
                land = self.db.query_one(
                    "SELECT * FROM lands WHERE land_id = ? AND dimension = ?",
                    (land_id, dimension),
                )
                if not land:
                    continue
                if (
                    self.is_public_land_owner(land.get("owner_xuid"))
                    and land.get("allow_non_public_land", 0)
                ):
                    continue
                exist_min_y = land.get("min_y", 0)
                exist_max_y = land.get("max_y", 255)
                y_overlap = min_y <= exist_max_y and max_y >= exist_min_y
                xz_overlap = (
                    check_min_x <= land["max_x"]
                    and check_max_x >= land["min_x"]
                    and check_min_z <= land["max_z"]
                    and check_max_z >= land["min_z"]
                )
                if y_overlap and xz_overlap:
                    overlapping.append(land_id)
            if overlapping:
                return False, "LAND_MIN_DISTANCE_NOT_SATISFIED", overlapping
            return True, None, None
        except Exception as e:
            self._log("error", f"Check land availability error: {str(e)}")
            self._emit_persistent_error("LAND_SYS2", f"check_land_availability: {e}", e)
            return False, "SYSTEM_ERROR", None

    # ─── 领地属性读写 ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_land_row(row) -> dict:
        if not row:
            return {}
        return {
            "land_name": row["land_name"],
            "dimension": row["dimension"],
            "min_x": row["min_x"],
            "max_x": row["max_x"],
            "min_y": row.get("min_y", 0),
            "max_y": row.get("max_y", 255),
            "min_z": row["min_z"],
            "max_z": row["max_z"],
            "tp_x": row["tp_x"],
            "tp_y": row["tp_y"],
            "tp_z": row["tp_z"],
            "shared_users": json.loads(row["shared_users"]),
            "owner_xuid": row["owner_xuid"],
            "allow_explosion": bool(row.get("allow_explosion", 0)),
            "allow_public_interact": bool(row.get("allow_public_interact", 0)),
            "allow_actor_interaction": bool(row.get("allow_actor_interaction", 0)),
            "allow_actor_damage": bool(row.get("allow_actor_damage", 0)),
            "allow_frame": bool(row.get("allow_frame", 0)),
            "allow_non_public_land": bool(row.get("allow_non_public_land", 0)),
            "allow_guild_member_interact": bool(
                row.get("allow_guild_member_interact", 0)
            ),
            "for_sale": bool(row.get("for_sale", 0)),
            "sale_price": float(row.get("sale_price") or 0),
            "owner_paid_money": row.get("owner_paid_money", 0),
        }

    def get_land_info(self, land_id: int) -> dict:
        try:
            row = self.db.query_one("SELECT * FROM lands WHERE land_id = ?", (land_id,))
            return self._parse_land_row(row)
        except Exception as e:
            self._log("error", f"Get land info error: {str(e)}")
            return {}

    def get_land_owner(self, land_id: int) -> str:
        try:
            row = self.db.query_one("SELECT owner_xuid FROM lands WHERE land_id = ?", (land_id,))
            return row["owner_xuid"] if row else ""
        except Exception as e:
            self._log("error", f"Get land owner error: {str(e)}")
            return ""

    def get_land_name(self, land_id: int) -> str:
        try:
            row = self.db.query_one("SELECT land_name FROM lands WHERE land_id = ?", (land_id,))
            return row["land_name"] if row else ""
        except Exception as e:
            self._log("error", f"Get land name error: {str(e)}")
            return ""

    def get_land_dimension(self, land_id: int) -> str:
        try:
            row = self.db.query_one("SELECT dimension FROM lands WHERE land_id = ?", (land_id,))
            return row["dimension"] if row else ""
        except Exception as e:
            self._log("error", f"Get land dimension error: {str(e)}")
            return ""

    def get_land_teleport_point(self, land_id: int) -> Optional[tuple]:
        try:
            row = self.db.query_one(
                "SELECT tp_x, tp_y, tp_z FROM lands WHERE land_id = ?", (land_id,)
            )
            return (row["tp_x"], row["tp_y"], row["tp_z"]) if row else None
        except Exception as e:
            self._log("error", f"Get land teleport point error: {str(e)}")
            return None

    def set_land_teleport_point(self, land_id: int, x: int, y: int, z: int) -> tuple:
        """返回 (success, error_reason_key_or_None)"""
        try:
            info = self.get_land_info(land_id)
            if not info:
                return False, "LAND_NOT_FOUND"
            if not (info["min_x"] <= x <= info["max_x"] and info["min_z"] <= z <= info["max_z"]):
                return False, "TP_POINT_OUT_OF_LAND"
            self.db.execute(
                "UPDATE lands SET tp_x = ?, tp_y = ?, tp_z = ? WHERE land_id = ?",
                (x, y, z, land_id),
            )
            return True, None
        except Exception as e:
            self._log("error", f"Set land teleport point error: {str(e)}")
            return False, str(e)

    def rename_land(self, land_id: int, new_name: str) -> tuple:
        """返回 (success, error_reason_key_or_None)"""
        try:
            if not self.get_land_info(land_id):
                return False, "LAND_NOT_FOUND"
            self.db.execute(
                "UPDATE lands SET land_name = ? WHERE land_id = ?", (new_name, land_id)
            )
            return True, None
        except Exception as e:
            self._log("error", f"Rename land error: {str(e)}")
            return False, str(e)

    def is_public_land(self, land_id: int) -> bool:
        return self.is_public_land_owner(self.get_land_owner(land_id))

    def set_land_as_public(self, land_id: int) -> bool:
        try:
            if not self.get_land_info(land_id):
                return False
            return self.db.execute(
                "UPDATE lands SET owner_xuid = ?, owner_paid_money = 0, "
                "for_sale = 0, sale_price = 0, "
                "allow_public_interact = 1, allow_actor_interaction = 1, allow_actor_damage = 1 "
                "WHERE land_id = ?",
                (self.LAND_OWNER_PUBLIC, land_id),
            )
        except Exception as e:
            self._log("error", f"Set land as public error: {str(e)}")
            return False

    def transfer_land(self, land_id: int, new_owner_xuid: str) -> bool:
        try:
            if not self.get_land_info(land_id):
                return False
            new_key = self.normalize_owner_key_for_write(new_owner_xuid)
            if not new_key:
                return False
            self.db.execute(
                "UPDATE lands SET owner_xuid = ?, for_sale = 0, sale_price = 0 WHERE land_id = ?",
                (new_key, land_id),
            )
            return True
        except Exception as e:
            self._log("error", f"Transfer land error: {str(e)}")
            return False

    def set_land_sale_listing(
        self, land_id: int, for_sale: bool, sale_price: float = 0.0
    ) -> bool:
        """私人领地上架/下架：上架时售价须 > 0。"""
        try:
            if not self.get_land_info(land_id):
                return False
            sp = float(sale_price)
            if for_sale:
                if sp <= 0:
                    return False
            else:
                sp = 0.0
            return bool(
                self.db.execute(
                    "UPDATE lands SET for_sale = ?, sale_price = ? WHERE land_id = ?",
                    (1 if for_sale else 0, sp, land_id),
                )
            )
        except Exception as e:
            self._log("error", f"Set land sale listing error: {str(e)}")
            return False

    def transfer_land_purchase(
        self,
        land_id: int,
        buyer_owner_key: str,
        seller_owner_key: str,
        price: float,
    ) -> bool:
        """
        买家购买上架领地：须仍为 seller 且 for_sale=1 且 sale_price 与 price 一致。
        转让后清空出售状态、授权列表，owner_paid_money 记为成交价。
        """
        try:
            new_key = self.normalize_owner_key_for_write(buyer_owner_key)
            if not new_key:
                return False
            fp = float(price)
            if fp <= 0:
                return False
            row = self.db.query_one(
                "SELECT owner_xuid, for_sale, sale_price FROM lands WHERE land_id = ?",
                (land_id,),
            )
            if not row:
                return False
            if str(row["owner_xuid"]) != str(seller_owner_key):
                return False
            if not int(row.get("for_sale") or 0):
                return False
            listed = float(row.get("sale_price") or 0)
            if abs(listed - fp) > 1e-6:
                return False
            return bool(
                self.db.execute(
                    "UPDATE lands SET owner_xuid = ?, for_sale = 0, sale_price = 0, "
                    "shared_users = '[]', owner_paid_money = ? "
                    "WHERE land_id = ? AND owner_xuid = ? AND for_sale = 1 "
                    "AND ABS(sale_price - ?) < 1e-6",
                    (new_key, fp, land_id, seller_owner_key, fp),
                )
            )
        except Exception as e:
            self._log("error", f"Transfer land purchase error: {str(e)}")
            return False

    def get_player_land_count(self, xuid: str) -> int:
        try:
            key = self.land_owner_key_player(xuid)
            row = self.db.query_one(
                "SELECT COUNT(*) as count FROM lands WHERE owner_xuid = ?", (key,)
            )
            return row["count"] if row else 0
        except Exception as e:
            self._log("error", f"Get player land count error: {str(e)}")
            return 0

    def get_player_lands(self, xuid: str) -> Dict[int, dict]:
        try:
            key = self.land_owner_key_player(xuid)
            rows = self.db.query_all(
                "SELECT * FROM lands WHERE owner_xuid = ?", (key,)
            )
            return {r["land_id"]: self._parse_land_row(r) for r in rows}
        except Exception as e:
            self._log("error", f"Get player lands error: {str(e)}")
            return {}

    def get_guild_land_count(self, guild_id: int) -> int:
        try:
            key = self.land_owner_key_guild(guild_id)
            row = self.db.query_one(
                "SELECT COUNT(*) as count FROM lands WHERE owner_xuid = ?", (key,)
            )
            return int(row["count"]) if row else 0
        except Exception as e:
            self._log("error", f"Get guild land count error: {str(e)}")
            return 0

    def get_guild_lands(self, guild_id: int) -> Dict[int, dict]:
        """返回指定公会名下所有主领地 land_id -> 解析后的领地信息。"""
        try:
            key = self.land_owner_key_guild(int(guild_id))
            rows = self.db.query_all(
                "SELECT * FROM lands WHERE owner_xuid = ? ORDER BY land_id",
                (key,),
            )
            return {int(r["land_id"]): self._parse_land_row(r) for r in rows}
        except Exception as e:
            self._log("error", f"Get guild lands error: {str(e)}")
            return {}

    def get_all_lands(self) -> Dict[int, dict]:
        try:
            rows = self.db.query_all("SELECT * FROM lands ORDER BY land_id")
            return {r["land_id"]: self._parse_land_row(r) for r in rows}
        except Exception as e:
            self._log("error", f"Get all lands error: {str(e)}")
            return {}

    # ─── 领地设置 toggle ─────────────────────────────────────────────────────

    _LAND_FLAG_COLUMNS = frozenset(
        {
            "allow_explosion",
            "allow_public_interact",
            "allow_actor_interaction",
            "allow_actor_damage",
            "allow_frame",
        }
    )

    def _set_land_flag(self, land_id: int, col: str, value: bool) -> bool:
        if col not in self._LAND_FLAG_COLUMNS:
            return False
        sql = {
            "allow_explosion": "UPDATE lands SET allow_explosion = ? WHERE land_id = ?",
            "allow_public_interact": "UPDATE lands SET allow_public_interact = ? WHERE land_id = ?",
            "allow_actor_interaction": "UPDATE lands SET allow_actor_interaction = ? WHERE land_id = ?",
            "allow_actor_damage": "UPDATE lands SET allow_actor_damage = ? WHERE land_id = ?",
            "allow_frame": "UPDATE lands SET allow_frame = ? WHERE land_id = ?",
        }[col]
        try:
            return bool(self.db.execute(sql, (1 if value else 0, land_id)))
        except Exception as e:
            self._log("error", f"Set land flag {col} error: {str(e)}")
            return False

    def set_land_allow_explosion(self, land_id: int, allow: bool) -> bool:
        return self._set_land_flag(land_id, "allow_explosion", allow)

    def set_land_allow_public_interact(self, land_id: int, allow: bool) -> bool:
        return self._set_land_flag(land_id, "allow_public_interact", allow)

    def set_land_allow_guild_member_interact(self, land_id: int, allow: bool) -> bool:
        """开启后，与领地主人（Player_ 主人）同一公会的成员可进行方块交互（不含建造/破坏）。"""
        return self._set_land_flag(land_id, "allow_guild_member_interact", allow)

    def set_land_allow_actor_interaction(self, land_id: int, allow: bool) -> bool:
        return self._set_land_flag(land_id, "allow_actor_interaction", allow)

    def set_land_allow_actor_damage(self, land_id: int, allow: bool) -> bool:
        return self._set_land_flag(land_id, "allow_actor_damage", allow)

    def set_land_allow_frame(self, land_id: int, allow: bool) -> bool:
        return self._set_land_flag(land_id, "allow_frame", allow)

    def set_land_allow_non_public_land(self, land_id: int, allow: bool) -> bool:
        return self._set_land_flag(land_id, "allow_non_public_land", allow)

    # ─── 领地授权 ─────────────────────────────────────────────────────────────

    def add_land_shared_user(self, land_id: int, xuid: str) -> bool:
        """将 xuid 加入领地共享列表，已存在返回 False"""
        try:
            info = self.get_land_info(land_id)
            if not info:
                return False
            shared = info["shared_users"]
            if xuid in shared:
                return False
            shared.append(xuid)
            return bool(self.db.execute(
                "UPDATE lands SET shared_users = ? WHERE land_id = ?",
                (json.dumps(shared), land_id),
            ))
        except Exception as e:
            self._log("error", f"Add land shared user error: {str(e)}")
            return False

    def remove_land_shared_user(self, land_id: int, xuid: str) -> bool:
        """从领地共享列表移除 xuid，不存在返回 False"""
        try:
            info = self.get_land_info(land_id)
            if not info:
                return False
            shared = info["shared_users"]
            if xuid not in shared:
                return False
            shared.remove(xuid)
            return bool(self.db.execute(
                "UPDATE lands SET shared_users = ? WHERE land_id = ?",
                (json.dumps(shared), land_id),
            ))
        except Exception as e:
            self._log("error", f"Remove land shared user error: {str(e)}")
            return False

    # ─── 公共领地 ─────────────────────────────────────────────────────────────

    def get_public_land_protected_entities(self) -> Set[str]:
        raw = self.setting_manager.GetSetting("PUBLIC_LAND_PROTECTED_ENTITIES")
        if not raw or not str(raw).strip():
            return set()
        return {s.strip() for s in str(raw).split(",") if s.strip()}

    def get_public_land_interact_block_blacklist(self) -> Set[str]:
        """与展示框权限（allow_frame）联动的方块黑名单；配置为逗号分隔方块 ID，留空则使用内置默认。"""
        raw = self.setting_manager.GetSetting("PUBLIC_LAND_INTERACT_BLOCK_BLACKLIST")
        if raw is None or not str(raw).strip():
            return set(self._DEFAULT_PUBLIC_LAND_INTERACT_BLOCK_BLACKLIST)
        result: Set[str] = set()
        for part in str(raw).split(","):
            part = part.strip()
            if not part:
                continue
            normalized = part.lower()
            if ":" not in normalized:
                normalized = "minecraft:" + normalized
            result.add(normalized)
        return result if result else set(self._DEFAULT_PUBLIC_LAND_INTERACT_BLOCK_BLACKLIST)

    # ─── 子领地 ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_sub_land_row(r) -> dict:
        return {
            "sub_land_id": r["sub_land_id"],
            "parent_land_id": r["parent_land_id"],
            "owner_xuid": r["owner_xuid"],
            "sub_land_name": r["sub_land_name"],
            "min_x": r["min_x"], "max_x": r["max_x"],
            "min_y": r.get("min_y", 0), "max_y": r.get("max_y", 255),
            "min_z": r["min_z"], "max_z": r["max_z"],
            "shared_users": json.loads(r.get("shared_users") or "[]"),
        }

    def create_sub_land(
        self,
        parent_land_id: int,
        owner_xuid: str,
        sub_land_name: str,
        min_x: int, max_x: int,
        min_y: int, max_y: int,
        min_z: int,         max_z: int,
    ) -> Optional[int]:
        try:
            owner_xuid = self.normalize_owner_key_for_write(owner_xuid)
            if not owner_xuid:
                return None
            self.db.execute(
                "INSERT INTO sub_lands "
                "(parent_land_id, owner_xuid, sub_land_name, min_x, max_x, min_y, max_y, min_z, max_z, shared_users) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (parent_land_id, owner_xuid, sub_land_name, min_x, max_x, min_y, max_y, min_z, max_z, "[]"),
            )
            row = self.db.query_one("SELECT last_insert_rowid() as sub_land_id")
            return row["sub_land_id"] if row else None
        except Exception as e:
            self._log("error", f"Create sub land error: {str(e)}")
            return None

    def delete_sub_land(self, sub_land_id: int) -> bool:
        try:
            return self.db.delete("sub_lands", "sub_land_id = ?", (sub_land_id,))
        except Exception as e:
            self._log("error", f"Delete sub land error: {str(e)}")
            return False

    def get_sub_land_info(self, sub_land_id: int) -> dict:
        try:
            row = self.db.query_one(
                "SELECT * FROM sub_lands WHERE sub_land_id = ?", (sub_land_id,)
            )
            return self._parse_sub_land_row(row) if row else {}
        except Exception as e:
            self._log("error", f"Get sub land info error: {str(e)}")
            return {}

    def get_sub_lands_by_parent(self, parent_land_id: int) -> Dict[int, dict]:
        try:
            rows = self.db.query_all(
                "SELECT * FROM sub_lands WHERE parent_land_id = ?", (parent_land_id,)
            )
            return {r["sub_land_id"]: self._parse_sub_land_row(r) for r in rows}
        except Exception as e:
            self._log("error", f"Get sub lands by parent error: {str(e)}")
            return {}

    def get_sub_lands_by_owner_in_parent(
        self, parent_land_id: int, owner_xuid: str
    ) -> Dict[int, dict]:
        try:
            key = self.normalize_owner_key_for_write(owner_xuid)
            rows = self.db.query_all(
                "SELECT * FROM sub_lands WHERE parent_land_id = ? AND owner_xuid = ?",
                (parent_land_id, key),
            )
            return {r["sub_land_id"]: self._parse_sub_land_row(r) for r in rows}
        except Exception as e:
            self._log("error", f"Get sub lands by owner error: {str(e)}")
            return {}

    def get_sub_land_at_pos(
        self, parent_land_id: int, x: int, y: int, z: int
    ) -> Optional[int]:
        try:
            rows = self.db.query_all(
                "SELECT sub_land_id, min_x, max_x, min_y, max_y, min_z, max_z "
                "FROM sub_lands WHERE parent_land_id = ?",
                (parent_land_id,),
            )
            for r in rows:
                if (
                    r["min_x"] <= x <= r["max_x"]
                    and r.get("min_y", 0) <= y <= r.get("max_y", 255)
                    and r["min_z"] <= z <= r["max_z"]
                ):
                    return r["sub_land_id"]
            return None
        except Exception as e:
            self._log("error", f"Get sub land at pos error: {str(e)}")
            return None

    def check_sub_land_availability(
        self,
        parent_land_id: int,
        min_x: int, max_x: int,
        min_y: int, max_y: int,
        min_z: int, max_z: int,
        exclude_sub_land_id: int = None,
    ) -> tuple:
        """返回 (True, None) 或 (False, reason_key)"""
        try:
            parent = self.get_land_info(parent_land_id)
            if not parent:
                self._emit_persistent_error(
                    "LAND_SYS3",
                    f"check_sub_land_availability parent_land_id={parent_land_id} not found",
                    None,
                )
                return False, "SYSTEM_ERROR"
            if (
                min_x < parent["min_x"] or max_x > parent["max_x"]
                or min_y < parent.get("min_y", 0) or max_y > parent.get("max_y", 255)
                or min_z < parent["min_z"] or max_z > parent["max_z"]
            ):
                return False, "SUB_LAND_OUT_OF_PARENT"
            siblings = self.db.query_all(
                "SELECT sub_land_id, min_x, max_x, min_y, max_y, min_z, max_z "
                "FROM sub_lands WHERE parent_land_id = ?",
                (parent_land_id,),
            )
            for r in siblings:
                if exclude_sub_land_id is not None and r["sub_land_id"] == exclude_sub_land_id:
                    continue
                if (
                    min_x <= r["max_x"] and max_x >= r["min_x"]
                    and min_y <= r.get("max_y", 255) and max_y >= r.get("min_y", 0)
                    and min_z <= r["max_z"] and max_z >= r["min_z"]
                ):
                    return False, "SUB_LAND_OVERLAP"
            return True, None
        except Exception as e:
            self._log("error", f"Check sub land availability error: {str(e)}")
            self._emit_persistent_error(
                "LAND_SYS4",
                f"check_sub_land_availability parent_land_id={parent_land_id}: {e}",
                e,
            )
            return False, "SYSTEM_ERROR"

    def add_sub_land_shared_user(self, sub_land_id: int, xuid: str) -> bool:
        try:
            info = self.get_sub_land_info(sub_land_id)
            if not info or xuid in info["shared_users"]:
                return False
            info["shared_users"].append(xuid)
            return bool(self.db.execute(
                "UPDATE sub_lands SET shared_users = ? WHERE sub_land_id = ?",
                (json.dumps(info["shared_users"]), sub_land_id),
            ))
        except Exception as e:
            self._log("error", f"Add sub land shared user error: {str(e)}")
            return False

    def remove_sub_land_shared_user(self, sub_land_id: int, xuid: str) -> bool:
        try:
            info = self.get_sub_land_info(sub_land_id)
            if not info or xuid not in info["shared_users"]:
                return False
            info["shared_users"].remove(xuid)
            return bool(self.db.execute(
                "UPDATE sub_lands SET shared_users = ? WHERE sub_land_id = ?",
                (json.dumps(info["shared_users"]), sub_land_id),
            ))
        except Exception as e:
            self._log("error", f"Remove sub land shared user error: {str(e)}")
            return False

    def rename_sub_land(self, sub_land_id: int, new_name: str) -> bool:
        try:
            return bool(self.db.execute(
                "UPDATE sub_lands SET sub_land_name = ? WHERE sub_land_id = ?",
                (new_name, sub_land_id),
            ))
        except Exception as e:
            self._log("error", f"Rename sub land error: {str(e)}")
            return False
