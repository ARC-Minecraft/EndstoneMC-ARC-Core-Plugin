# -*- coding: utf-8 -*-
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from endstone import Player

from endstone_arc_core.achievement_conditions import (
    AchievementCheckContext,
    AchievementConditionBase,
    build_achievement_condition_from_dict,
)

# 与 默认成就.md 一致：一键生成 OP 面板「默认击杀成就」用
_DEFAULT_KILL_ACHIEVEMENT_BUNDLE: List[Dict[str, Any]] = [
    {"unlock_title": "屠夫", "name": "屠夫", "rarity": "普通", "reward_money": 1000.0, "reward_items": [{"item_name": "pb_gat:trinket_hunger", "count": 1}], "entity_ids": ["minecraft:cow", "minecraft:sheep", "minecraft:pig", "minecraft:chicken"], "required_count": 100},
    {"unlock_title": "恐怖分子", "name": "恐怖分子", "rarity": "普通", "reward_money": 1000.0, "reward_items": [{"item_name": "pb_gat:trinket_root", "count": 1}], "entity_ids": ["minecraft:villager_v2"], "required_count": 100},
    {"unlock_title": "赶尸人", "name": "赶尸人", "rarity": "普通", "reward_money": 2000.0, "reward_items": [], "entity_ids": ["minecraft:zombie"], "required_count": 100},
    {"unlock_title": "骸骨克星", "name": "骸骨克星", "rarity": "普通", "reward_money": 2500.0, "reward_items": [], "entity_ids": ["minecraft:skeleton"], "required_count": 100},
    {"unlock_title": "猪灵猎手", "name": "猪灵猎手", "rarity": "普通", "reward_money": 4500.0, "reward_items": [], "entity_ids": ["minecraft:piglin", "minecraft:piglin_brute", "minecraft:zombified_piglin"], "required_count": 100},
    {"unlock_title": "养蜂人", "name": "养蜂人", "rarity": "普通", "reward_money": 3000.0, "reward_items": [], "entity_ids": ["minecraft:bee"], "required_count": 100},
    {"unlock_title": "白眼狼", "name": "白眼狼", "rarity": "普通", "reward_money": 3000.0, "reward_items": [], "entity_ids": ["minecraft:wolf"], "required_count": 100},
    {"unlock_title": "犹鱼元首", "name": "犹鱼元首", "rarity": "普通", "reward_money": 3500.0, "reward_items": [], "entity_ids": ["minecraft:squid", "minecraft:glow_squid"], "required_count": 100},
    {"unlock_title": "捕鱼达人", "name": "捕鱼达人", "rarity": "普通", "reward_money": 2000.0, "reward_items": [], "entity_ids": ["minecraft:cod", "minecraft:salmon", "minecraft:tropicalfish", "minecraft:pufferfish"], "required_count": 200},
    {"unlock_title": "拆弹专家", "name": "拆弹专家", "rarity": "普通", "reward_money": 3500.0, "reward_items": [{"item_name": "minecraft:tnt", "count": 16}], "entity_ids": ["minecraft:creeper"], "required_count": 100},
    {"unlock_title": "杀虫剂", "name": "杀虫剂", "rarity": "普通", "reward_money": 6000.0, "reward_items": [], "entity_ids": ["minecraft:endermite"], "required_count": 100},
    {"unlock_title": "啄木鸟", "name": "啄木鸟", "rarity": "普通", "reward_money": 4000.0, "reward_items": [], "entity_ids": ["minecraft:silverfish"], "required_count": 100},
    {"unlock_title": "天空恶魔", "name": "天空恶魔", "rarity": "普通", "reward_money": 9000.0, "reward_items": [{"item_name": "pb_gat:trinket_loot", "count": 1}], "entity_ids": ["minecraft:phantom"], "required_count": 100},
    {"unlock_title": "水鬼克星", "name": "水鬼克星", "rarity": "普通", "reward_money": 3500.0, "reward_items": [], "entity_ids": ["minecraft:drowned"], "required_count": 100},
    {"unlock_title": "烈焰猎人", "name": "烈焰猎人", "rarity": "普通", "reward_money": 10000.0, "reward_items": [], "entity_ids": ["minecraft:blaze"], "required_count": 80},
    {"unlock_title": "逐寇者", "name": "逐寇者", "rarity": "普通", "reward_money": 5000.0, "reward_items": [], "entity_ids": ["minecraft:pillager"], "required_count": 100},
    {"unlock_title": "破阵者", "name": "破阵者", "rarity": "普通", "reward_money": 8000.0, "reward_items": [], "entity_ids": ["minecraft:vindicator"], "required_count": 100},
    {"unlock_title": "极地猛士", "name": "极地猛士", "rarity": "普通", "reward_money": 6000.0, "reward_items": [], "entity_ids": ["minecraft:polar_bear"], "required_count": 50},
    {"unlock_title": "节肢杀手", "name": "节肢杀手", "rarity": "稀有", "reward_money": 2000.0, "reward_items": [{"item_name": "pb_gat:trinket_weaving", "count": 1}], "entity_ids": ["minecraft:spider", "minecraft:cave_spider"], "required_count": 100},
    {"unlock_title": "末影猎手", "name": "末影猎手", "rarity": "稀有", "reward_money": 5000.0, "reward_items": [{"item_name": "pb_gat:trinket_boss_dragon", "count": 1}], "entity_ids": ["minecraft:enderman"], "required_count": 100},
    {"unlock_title": "粘液忍者", "name": "粘液忍者", "rarity": "稀有", "reward_money": 8000.0, "reward_items": [{"item_name": "pb_gat:trinket_food", "count": 1}], "entity_ids": ["minecraft:slime"], "required_count": 100},
    {"unlock_title": "熔火核心", "name": "熔火核心", "rarity": "稀有", "reward_money": 9000.0, "reward_items": [{"item_name": "pb_gat:trinket_fire", "count": 1}], "entity_ids": ["minecraft:magma_cube"], "required_count": 100},
    {"unlock_title": "女巫猎人", "name": "女巫猎人", "rarity": "稀有", "reward_money": 12000.0, "reward_items": [{"item_name": "pb_gat:trinket_remedy_vial", "count": 1}], "entity_ids": ["minecraft:witch"], "required_count": 100},
    {"unlock_title": "破法者", "name": "破法者", "rarity": "稀有", "reward_money": 15000.0, "reward_items": [{"item_name": "pb_gat:trinket_prophecy_scope", "count": 1}], "entity_ids": ["minecraft:evocation_illager"], "required_count": 30},
    {"unlock_title": "魂修", "name": "魂修", "rarity": "稀有", "reward_money": 15000.0, "reward_items": [{"item_name": "pb_gat:trinket_spectral_shard", "count": 1}], "entity_ids": ["minecraft:ghast"], "required_count": 50},
    {"unlock_title": "枯萎穿心攻击", "name": "枯萎穿心攻击", "rarity": "稀有", "reward_money": 18000.0, "reward_items": [{"item_name": "pb_gat:trinket_wither", "count": 1}], "entity_ids": ["minecraft:wither_skeleton"], "required_count": 120},
    {"unlock_title": "野猪骑士", "name": "野猪骑士", "rarity": "稀有", "reward_money": 7000.0, "reward_items": [{"item_name": "pb_gat:trinket_speed", "count": 1}], "entity_ids": ["minecraft:hoglin", "minecraft:zoglin", "minecraft:strider"], "required_count": 100},
    {"unlock_title": "土匪", "name": "土匪", "rarity": "稀有", "reward_money": 3500.0, "reward_items": [{"item_name": "pb_gat:trinket_coin_amulet", "count": 1}], "entity_ids": ["minecraft:wandering_trader"], "required_count": 100},
    {"unlock_title": "巨兽克星", "name": "巨兽克星", "rarity": "稀有", "reward_money": 10000.0, "reward_items": [{"item_name": "pb_gat:trinket_heavy_dumbell", "count": 1}], "entity_ids": ["minecraft:ravager"], "required_count": 10},
    {"unlock_title": "可恶的两格人", "name": "可恶的两格人", "rarity": "稀有", "reward_money": 10000.0, "reward_items": [{"item_name": "pb_gat:trinket_molten_heart", "count": 1}], "entity_ids": ["minecraft:iron_golem"], "required_count": 100},
    {"unlock_title": "风暴之神", "name": "风暴之神", "rarity": "史诗", "reward_money": 6000.0, "reward_items": [{"item_name": "pb_gat:trinket_fall", "count": 1}], "entity_ids": ["minecraft:breeze"], "required_count": 10},
    {"unlock_title": "海王", "name": "海王", "rarity": "史诗", "reward_money": 30000.0, "reward_items": [{"item_name": "pb_gat:trinket_fatigue", "count": 1}], "entity_ids": ["minecraft:elder_guardian", "minecraft:guardian"], "required_count": 50},
    {"unlock_title": "太空人", "name": "太空人", "rarity": "史诗", "reward_money": 20000.0, "reward_items": [{"item_name": "pb_gat:trinket_magnet", "count": 1}], "entity_ids": ["minecraft:shulker"], "required_count": 50},
    {"unlock_title": "恶魔领主", "name": "恶魔领主", "rarity": "史诗", "reward_money": 15000.0, "reward_items": [{"item_name": "pb_gat:trinket_feather", "count": 1}], "entity_ids": ["minecraft:vex"], "required_count": 50},
    {"unlock_title": "末地之主", "name": "末地之主", "rarity": "传奇", "reward_money": 10000.0, "reward_items": [{"item_name": "minecraft:dragon_egg", "count": 1}], "entity_ids": ["minecraft:ender_dragon"], "required_count": 1},
    {"unlock_title": "下界之主", "name": "下界之主", "rarity": "传奇", "reward_money": 30000.0, "reward_items": [{"item_name": "pb_gat:trinket_miracle_eye", "count": 1}], "entity_ids": ["minecraft:wither"], "required_count": 1},
    {"unlock_title": "幽匿之主", "name": "幽匿之主", "rarity": "传奇", "reward_money": 40000.0, "reward_items": [{"item_name": "pb_gat:trinket_boss_warden", "count": 1}], "entity_ids": ["minecraft:warden"], "required_count": 1},
]

DEFAULT_KILL_ACHIEVEMENT_ENTRY_COUNT = len(_DEFAULT_KILL_ACHIEVEMENT_BUNDLE)


class AchievementSystem:
    """
    成就系统（JSON 配置）：
    - 成就定义存到 achievements.json，服主可直接编辑
    - 条件类型：kill_entity（单种生物）；kill_entity_sum（多种生物击杀数相加达到 required_count）
    - 当前逻辑固定：all（列表内条件全部满足才解锁）
    """

    condition_type_kill_entity = "kill_entity"
    condition_type_kill_entity_sum = "kill_entity_sum"
    logic_all = "all"

    def __init__(self, database_manager, title_system, language_manager, unlock_title_func, main_path: str = "plugins/ARCCore"):
        self.database_manager = database_manager
        self.title_system = title_system
        self.language_manager = language_manager
        self.unlock_title_func = unlock_title_func

        self._main_path = Path(main_path)
        self._achievement_json_path = self._main_path / "achievements.json"

        self._table_stats = "player_achievement_stats"
        self._table_unlocked = "player_achievement_unlocked"
        self._table_meta = "achievement_meta"
        self._table_condition = "achievement_conditions"
        self._legacy_table_def = "achievement_definitions"

        # 生物类型 ID -> 可能受影响的成就 unlock_title（仅击杀类条件参与；配置变更后失效重建）
        self._kill_hot_index: Optional[Dict[str, Set[str]]] = None

    def ensure_tables(self) -> bool:
        try:
            self.database_manager.execute(
                "CREATE TABLE IF NOT EXISTS " + self._table_stats + " ("
                "xuid TEXT NOT NULL, "
                "stat_key TEXT NOT NULL, "
                "count INTEGER NOT NULL DEFAULT 0, "
                "PRIMARY KEY (xuid, stat_key)"
                ")"
            )
            self.database_manager.execute(
                "CREATE TABLE IF NOT EXISTS " + self._table_unlocked + " ("
                "xuid TEXT NOT NULL, "
                "unlock_title TEXT NOT NULL, "
                "unlocked_at TEXT, "
                "UNIQUE (xuid, unlock_title)"
                ")"
            )
            # 仅用于迁移旧数据
            self.database_manager.execute(
                "CREATE TABLE IF NOT EXISTS " + self._table_meta + " ("
                "unlock_title TEXT PRIMARY KEY, "
                "name TEXT NOT NULL, "
                "enabled INTEGER NOT NULL DEFAULT 1"
                ")"
            )
            self.database_manager.execute(
                "CREATE TABLE IF NOT EXISTS " + self._table_condition + " ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "unlock_title TEXT NOT NULL, "
                "condition_type TEXT NOT NULL, "
                "target_id TEXT NOT NULL, "
                "required_count INTEGER NOT NULL"
                ")"
            )
            self._migrate_legacy_definitions_to_db()
            self._ensure_json_definition_file()
            self._migrate_achievement_json_if_hidden_default()
            return True
        except Exception:
            return False

    @staticmethod
    def _safe_int(value: Any, default_value: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default_value

    def _xuid(self, player: Player) -> str:
        return str(player.xuid)

    def _default_config(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "achievements": [],
        }

    def _normalize_logic(self, logic_value: Any) -> str:
        _ = logic_value
        return self.logic_all

    @staticmethod
    def _normalize_target_ids_list(raw_value: Any) -> List[str]:
        if raw_value is None:
            return []
        if isinstance(raw_value, list):
            return [str(x).strip() for x in raw_value if str(x).strip()]
        if isinstance(raw_value, str):
            return [x.strip() for x in raw_value.split(",") if x.strip()]
        return []

    def _normalize_condition(self, condition_data: Dict[str, Any], fallback_id: int) -> Optional[Dict[str, Any]]:
        condition_type = str(condition_data.get("type") or condition_data.get("condition_type") or "").strip()
        required_count = self._safe_int(condition_data.get("required_count"), 0)
        condition_id = self._safe_int(condition_data.get("id"), fallback_id)
        if condition_id <= 0:
            condition_id = fallback_id

        if condition_type == self.condition_type_kill_entity_sum:
            target_ids = self._normalize_target_ids_list(condition_data.get("target_ids"))
            if not target_ids and condition_data.get("target_id"):
                target_ids = self._normalize_target_ids_list(str(condition_data.get("target_id") or ""))
            if len(target_ids) < 1 or required_count <= 0:
                return None
            return {
                "id": condition_id,
                "type": condition_type,
                "condition_type": condition_type,
                "target_ids": target_ids,
                "required_count": required_count,
            }

        if condition_type != self.condition_type_kill_entity:
            return None
        target_id = str(condition_data.get("target_id") or "").strip()
        if not target_id or required_count <= 0:
            return None
        return {
            "id": condition_id,
            "type": condition_type,
            "condition_type": condition_type,
            "target_id": target_id,
            "required_count": required_count,
        }

    def _load_json_config(self) -> Dict[str, Any]:
        try:
            if not self._achievement_json_path.exists():
                return self._default_config()
            raw_text = self._achievement_json_path.read_text(encoding="utf-8")
            raw_data = json.loads(raw_text)
            if not isinstance(raw_data, dict):
                return self._default_config()
            achievement_list = raw_data.get("achievements")
            if not isinstance(achievement_list, list):
                achievement_list = []

            normalized_list: List[Dict[str, Any]] = []
            used_unlock_title_set = set()
            used_condition_id_set = set()
            next_condition_id = 1

            for achievement_data in achievement_list:
                if not isinstance(achievement_data, dict):
                    continue
                name = str(achievement_data.get("name") or "").strip()
                unlock_title = str(achievement_data.get("unlock_title") or "").strip()
                enabled = bool(achievement_data.get("enabled", True))
                if_hidden = bool(achievement_data.get("if_hidden", False))
                logic_value = self._normalize_logic(achievement_data.get("logic"))
                raw_conditions = achievement_data.get("conditions")
                if not isinstance(raw_conditions, list):
                    raw_conditions = []
                if not name or not unlock_title:
                    continue
                if unlock_title in used_unlock_title_set:
                    continue
                used_unlock_title_set.add(unlock_title)

                normalized_conditions: List[Dict[str, Any]] = []
                for condition_data in raw_conditions:
                    if not isinstance(condition_data, dict):
                        continue
                    condition_obj = self._normalize_condition(condition_data, next_condition_id)
                    if condition_obj is None:
                        continue
                    while condition_obj["id"] in used_condition_id_set:
                        condition_obj["id"] += 1
                    used_condition_id_set.add(condition_obj["id"])
                    next_condition_id = max(next_condition_id, condition_obj["id"] + 1)
                    normalized_conditions.append(condition_obj)

                normalized_list.append(
                    {
                        "name": name,
                        "unlock_title": unlock_title,
                        "enabled": enabled,
                        "if_hidden": if_hidden,
                        "logic": logic_value,
                        "conditions": normalized_conditions,
                    }
                )

            return {
                "version": self._safe_int(raw_data.get("version"), 1),
                "achievements": normalized_list,
            }
        except Exception:
            return self._default_config()

    def _save_json_config(self, config_data: Dict[str, Any]) -> bool:
        try:
            self._main_path.mkdir(parents=True, exist_ok=True)
            self._achievement_json_path.write_text(
                json.dumps(config_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._invalidate_kill_hot_index()
            return True
        except Exception:
            return False

    def _invalidate_kill_hot_index(self) -> None:
        self._kill_hot_index = None

    def _ensure_kill_hot_index(self) -> None:
        if self._kill_hot_index is not None:
            return
        self._rebuild_kill_hot_index()

    def _rebuild_kill_hot_index(self) -> None:
        index: Dict[str, Set[str]] = {}
        for achievement_data in self.list_achievements():
            if not bool(achievement_data.get("enabled", True)):
                continue
            unlock_title = str(achievement_data.get("unlock_title") or "").strip()
            if not unlock_title:
                continue
            for condition_data in achievement_data.get("conditions") or []:
                if not isinstance(condition_data, dict):
                    continue
                condition_obj = self._build_condition_from_dict(condition_data)
                if condition_obj is None:
                    continue
                for entity_key in condition_obj.kill_index_entity_keys():
                    if entity_key not in index:
                        index[entity_key] = set()
                    index[entity_key].add(unlock_title)
        self._kill_hot_index = index

    def _build_condition_from_dict(self, raw_dict: Dict[str, Any]) -> Optional[AchievementConditionBase]:
        return build_achievement_condition_from_dict(
            raw_dict,
            self.condition_type_kill_entity,
            self.condition_type_kill_entity_sum,
            self._normalize_target_ids_list,
            self._safe_int,
        )

    def _migrate_legacy_definitions_to_db(self) -> None:
        """
        兼容旧版 achievement_definitions：
        - 先迁移到中间表 achievement_meta / achievement_conditions
        - 再由 _ensure_json_definition_file 导出到 achievements.json
        """
        try:
            meta_rows = self.database_manager.query_all(
                "SELECT unlock_title FROM " + self._table_meta + " LIMIT 1",
                (),
            )
            if meta_rows:
                return

            legacy_rows = self.database_manager.query_all(
                "SELECT name, stat_key, required_count, unlock_title, enabled "
                "FROM " + self._legacy_table_def,
                (),
            )
            if not legacy_rows:
                return

            for row in legacy_rows:
                name = str(row.get("name") or "").strip()
                stat_key = str(row.get("stat_key") or "").strip()
                unlock_title = str(row.get("unlock_title") or "").strip()
                required_count = self._safe_int(row.get("required_count"), 0)
                enabled = 1 if int(row.get("enabled") or 0) == 1 else 0
                if not name or not stat_key or not unlock_title or required_count <= 0:
                    continue

                parsed = self._parse_legacy_stat_key(stat_key)
                if parsed is None:
                    continue
                condition_type, target_id = parsed

                self.database_manager.execute(
                    "INSERT OR IGNORE INTO " + self._table_meta + " (unlock_title, name, enabled) VALUES (?, ?, ?)",
                    (unlock_title, name, enabled),
                )
                self.database_manager.execute(
                    "INSERT INTO " + self._table_condition + " (unlock_title, condition_type, target_id, required_count) "
                    "VALUES (?, ?, ?, ?)",
                    (unlock_title, condition_type, target_id, required_count),
                )
        except Exception:
            pass

    def _ensure_json_definition_file(self) -> None:
        config_data = self._load_json_config()
        if config_data.get("achievements"):
            return

        db_meta_rows = self.database_manager.query_all(
            "SELECT unlock_title, name, enabled FROM " + self._table_meta + " ORDER BY unlock_title ASC",
            (),
        )
        if not db_meta_rows:
            self._save_json_config(self._default_config())
            return

        condition_rows = self.database_manager.query_all(
            "SELECT id, unlock_title, condition_type, target_id, required_count "
            "FROM " + self._table_condition + " ORDER BY id ASC",
            (),
        )
        condition_group_dict: Dict[str, List[Dict[str, Any]]] = {}
        for condition_row in condition_rows:
            unlock_title = str(condition_row.get("unlock_title") or "").strip()
            condition_type = str(condition_row.get("condition_type") or "").strip()
            target_id = str(condition_row.get("target_id") or "").strip()
            required_count = self._safe_int(condition_row.get("required_count"), 0)
            condition_id = self._safe_int(condition_row.get("id"), 0)
            if (
                not unlock_title
                or condition_type != self.condition_type_kill_entity
                or not target_id
                or required_count <= 0
                or condition_id <= 0
            ):
                continue
            if unlock_title not in condition_group_dict:
                condition_group_dict[unlock_title] = []
            condition_group_dict[unlock_title].append(
                {
                    "id": condition_id,
                    "type": condition_type,
                    "target_id": target_id,
                    "required_count": required_count,
                }
            )

        achievement_list = []
        for meta_row in db_meta_rows:
            unlock_title = str(meta_row.get("unlock_title") or "").strip()
            name = str(meta_row.get("name") or "").strip()
            enabled = int(meta_row.get("enabled") or 0) == 1
            if not unlock_title or not name:
                continue
            achievement_list.append(
                {
                    "name": name,
                    "unlock_title": unlock_title,
                    "enabled": enabled,
                    "if_hidden": False,
                    "logic": self.logic_all,
                    "conditions": condition_group_dict.get(unlock_title, []),
                }
            )

        self._save_json_config({"version": 1, "achievements": achievement_list})

    def _migrate_achievement_json_if_hidden_default(self) -> None:
        """旧版 achievements.json 无 if_hidden 字段时写入未隐藏（直接读原始 JSON，避免归一化后误判）。"""
        try:
            if not self._achievement_json_path.exists():
                return
            raw_text = self._achievement_json_path.read_text(encoding="utf-8")
            raw_data = json.loads(raw_text)
            if not isinstance(raw_data, dict):
                return
            achievement_list = raw_data.get("achievements") or []
            if not isinstance(achievement_list, list):
                return
            changed = False
            for achievement_data in achievement_list:
                if isinstance(achievement_data, dict) and "if_hidden" not in achievement_data:
                    achievement_data["if_hidden"] = False
                    changed = True
            if changed:
                raw_data["achievements"] = achievement_list
                self._main_path.mkdir(parents=True, exist_ok=True)
                self._achievement_json_path.write_text(
                    json.dumps(raw_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self._invalidate_kill_hot_index()
        except Exception:
            pass

    def _build_stat_key(self, condition_type: str, target_id: str) -> str:
        condition_type = (condition_type or "").strip()
        target_id = (target_id or "").strip()
        if condition_type == self.condition_type_kill_entity:
            if target_id == "*":
                return "kill_total"
            return f"kill:{target_id}"
        return ""

    def _parse_legacy_stat_key(self, stat_key: str) -> Optional[Tuple[str, str]]:
        stat_key = (stat_key or "").strip()
        if stat_key == "kill_total":
            return self.condition_type_kill_entity, "*"
        if stat_key.startswith("kill:"):
            target_id = stat_key[len("kill:"):].strip()
            if target_id:
                return self.condition_type_kill_entity, target_id
        return None

    def _get_stat_count(self, xuid: str, stat_key: str) -> int:
        row = self.database_manager.query_one(
            "SELECT count FROM " + self._table_stats + " WHERE xuid = ? AND stat_key = ?",
            (xuid, stat_key),
        )
        if not row:
            return 0
        return self._safe_int(row.get("count", 0), 0)

    def _inc_stat(self, xuid: str, stat_key: str, delta: int = 1) -> int:
        delta = self._safe_int(delta, 1)
        if delta <= 0:
            return self._get_stat_count(xuid, stat_key)
        self.database_manager.execute(
            "INSERT OR IGNORE INTO " + self._table_stats + " (xuid, stat_key, count) VALUES (?, ?, 0)",
            (xuid, stat_key),
        )
        self.database_manager.execute(
            "UPDATE " + self._table_stats + " SET count = count + ? WHERE xuid = ? AND stat_key = ?",
            (delta, xuid, stat_key),
        )
        return self._get_stat_count(xuid, stat_key)

    def _is_unlocked(self, xuid: str, unlock_title: str) -> bool:
        row = self.database_manager.query_one(
            "SELECT 1 FROM " + self._table_unlocked + " WHERE xuid = ? AND unlock_title = ?",
            (xuid, unlock_title),
        )
        return row is not None

    def list_unlocked_titles_for_xuid(self, xuid: str) -> Set[str]:
        xuid_s = str(xuid or "").strip()
        if not xuid_s:
            return set()
        try:
            rows = self.database_manager.query_all(
                "SELECT unlock_title FROM " + self._table_unlocked + " WHERE xuid = ?",
                (xuid_s,),
            )
            titles = {
                str(r.get("unlock_title") or "").strip()
                for r in rows or []
                if str(r.get("unlock_title") or "").strip()
            }
            # 头衔已在 player_title_unlock_time 中但成就表未写入时补录（旧逻辑曾依赖 unlock API 返回值）
            for achievement_data in self.list_achievements():
                ut = str(achievement_data.get("unlock_title") or "").strip()
                if not ut or ut in titles:
                    continue
                try:
                    if self.title_system.has_unlocked_title_by_xuid(xuid_s, ut):
                        self._mark_unlocked(xuid_s, ut)
                        titles.add(ut)
                except Exception:
                    pass
            return titles
        except Exception:
            return set()

    def player_has_unlocked_title(self, xuid: str, unlock_title: str) -> bool:
        xs = str(xuid or "").strip()
        ut = str(unlock_title or "").strip()
        if not xs or not ut:
            return False
        if self._is_unlocked(xs, ut):
            return True
        try:
            if self.title_system.has_unlocked_title_by_xuid(xs, ut):
                self._mark_unlocked(xs, ut)
                return True
        except Exception:
            pass
        return False

    def set_achievement_if_hidden(self, unlock_title: str, if_hidden: bool) -> bool:
        unlock_title = (unlock_title or "").strip()
        if not unlock_title:
            return False
        config_data = self._load_json_config()
        achievement_list = config_data.get("achievements") or []
        for achievement_data in achievement_list:
            if str(achievement_data.get("unlock_title") or "").strip() == unlock_title:
                achievement_data["if_hidden"] = bool(if_hidden)
                config_data["achievements"] = achievement_list
                return self._save_json_config(config_data)
        return False

    def list_unlocked_achievements_for_player_ui(self, xuid: str) -> List[Dict[str, Any]]:
        """已解锁列表：含隐藏成就在解锁后可见。"""
        unlocked_set = self.list_unlocked_titles_for_xuid(xuid)
        result: List[Dict[str, Any]] = []
        for achievement_data in self.list_achievements():
            ut = str(achievement_data.get("unlock_title") or "").strip()
            if ut and ut in unlocked_set:
                result.append(achievement_data)
        return result

    def list_locked_achievements_for_player_ui(self, xuid: str) -> List[Dict[str, Any]]:
        """未解锁列表：隐藏且未解锁的不展示。"""
        unlocked_set = self.list_unlocked_titles_for_xuid(xuid)
        result: List[Dict[str, Any]] = []
        for achievement_data in self.list_achievements():
            ut = str(achievement_data.get("unlock_title") or "").strip()
            if not ut or ut in unlocked_set:
                continue
            if bool(achievement_data.get("if_hidden", False)):
                continue
            result.append(achievement_data)
        return result

    def _mark_unlocked(self, xuid: str, unlock_title: str) -> None:
        now_iso = datetime.now().isoformat()
        self.database_manager.execute(
            "INSERT OR IGNORE INTO " + self._table_unlocked + " (xuid, unlock_title, unlocked_at) VALUES (?, ?, ?)",
            (xuid, unlock_title, now_iso),
        )

    def _achievement_conditions_met(self, xuid: str, achievement_data: Dict[str, Any]) -> bool:
        condition_list = achievement_data.get("conditions") or []
        if not condition_list:
            return False
        ctx = AchievementCheckContext(self, xuid)
        for condition_data in condition_list:
            if not isinstance(condition_data, dict):
                return False
            condition_obj = self._build_condition_from_dict(condition_data)
            if condition_obj is None:
                return False
            if not condition_obj.check_if_satisfied(ctx):
                return False
        _ = achievement_data.get("logic")
        return True

    def _try_unlock_one_achievement(self, player: Player, achievement_data: Dict[str, Any]) -> None:
        xuid = self._xuid(player)
        unlock_title = str(achievement_data.get("unlock_title") or "").strip()
        enabled = bool(achievement_data.get("enabled", True))
        if not unlock_title or not enabled:
            return
        if self._is_unlocked(xuid, unlock_title):
            return
        if not self._achievement_conditions_met(xuid, achievement_data):
            return
        self.title_system.ensure_title_definition(unlock_title)
        try:
            self.unlock_title_func(player, unlock_title)
        except Exception:
            pass
        # 条件已达成即写入成就解锁表；头衔发放失败不应导致成就进度丢失
        self._mark_unlocked(xuid, unlock_title)
        try:
            msg = self.language_manager.GetText("ACHIEVEMENT_UNLOCKED_HINT")
            if msg:
                player.send_message(msg.format(unlock_title))
        except Exception:
            pass

    def _check_and_unlock_for_kill_related_titles(self, player: Player, unlock_titles: Set[str]) -> None:
        for unlock_title in unlock_titles:
            achievement_data = self.get_achievement(unlock_title)
            if not achievement_data:
                continue
            self._try_unlock_one_achievement(player, achievement_data)

    def _check_and_unlock(self, player: Player) -> None:
        """全量检查（少用）；击杀路径请用 _check_and_unlock_for_kill_related_titles。"""
        xuid = self._xuid(player)
        for achievement_data in self.list_achievements():
            unlock_title = str(achievement_data.get("unlock_title") or "").strip()
            if not unlock_title:
                continue
            if self._is_unlocked(xuid, unlock_title):
                continue
            self._try_unlock_one_achievement(player, achievement_data)

    # ---------- 统计入口 ----------
    def record_kill(self, player: Player, entity_type: str) -> None:
        if not player or not entity_type:
            return
        entity_type = str(entity_type).strip()
        if not entity_type:
            return
        xuid = self._xuid(player)
        self._inc_stat(xuid, "kill_total", 1)
        self._inc_stat(xuid, f"kill:{entity_type}", 1)
        self._ensure_kill_hot_index()
        related_titles: Set[str] = set()
        if self._kill_hot_index:
            related_titles |= self._kill_hot_index.get(entity_type, set())
            related_titles |= self._kill_hot_index.get("*", set())
        self._check_and_unlock_for_kill_related_titles(player, related_titles)

    def record_block_break(self, player: Player, block_id: str) -> None:
        _ = player
        _ = block_id

    # ---------- 成就（基础信息） ----------
    def list_achievements(self) -> List[Dict[str, Any]]:
        config_data = self._load_json_config()
        achievement_list = config_data.get("achievements") or []
        return sorted(
            achievement_list,
            key=lambda achievement_data: (
                0 if achievement_data.get("enabled", True) else 1,
                str(achievement_data.get("name") or ""),
                str(achievement_data.get("unlock_title") or ""),
            ),
        )

    def get_achievement(self, unlock_title: str) -> Optional[Dict[str, Any]]:
        unlock_title = (unlock_title or "").strip()
        if not unlock_title:
            return None
        for achievement_data in self.list_achievements():
            if str(achievement_data.get("unlock_title") or "").strip() == unlock_title:
                return achievement_data
        return None

    def create_achievement(
        self, name: str, unlock_title: str, enabled: bool = True, if_hidden: bool = False
    ) -> bool:
        name = (name or "").strip()
        unlock_title = (unlock_title or "").strip()
        if not name or not unlock_title:
            return False
        config_data = self._load_json_config()
        achievement_list = config_data.get("achievements") or []
        for achievement_data in achievement_list:
            if str(achievement_data.get("unlock_title") or "").strip() == unlock_title:
                return False
        achievement_list.append(
            {
                "name": name,
                "unlock_title": unlock_title,
                "enabled": bool(enabled),
                "if_hidden": bool(if_hidden),
                "logic": self.logic_all,
                "conditions": [],
            }
        )
        config_data["achievements"] = achievement_list
        return self._save_json_config(config_data)

    def update_achievement(
        self,
        old_unlock_title: str,
        name: str,
        new_unlock_title: str,
        enabled: bool,
        if_hidden: bool = False,
    ) -> bool:
        old_unlock_title = (old_unlock_title or "").strip()
        new_unlock_title = (new_unlock_title or "").strip()
        name = (name or "").strip()
        if not old_unlock_title or not new_unlock_title or not name:
            return False

        config_data = self._load_json_config()
        achievement_list = config_data.get("achievements") or []
        target_index = -1
        for index, achievement_data in enumerate(achievement_list):
            unlock_title = str(achievement_data.get("unlock_title") or "").strip()
            if unlock_title == old_unlock_title:
                target_index = index
            if unlock_title == new_unlock_title and unlock_title != old_unlock_title:
                return False
        if target_index < 0:
            return False

        achievement_list[target_index]["name"] = name
        achievement_list[target_index]["unlock_title"] = new_unlock_title
        achievement_list[target_index]["enabled"] = bool(enabled)
        achievement_list[target_index]["if_hidden"] = bool(if_hidden)
        achievement_list[target_index]["logic"] = self.logic_all

        config_data["achievements"] = achievement_list
        if not self._save_json_config(config_data):
            return False

        if old_unlock_title != new_unlock_title:
            self.database_manager.execute(
                "DELETE FROM " + self._table_unlocked + " WHERE unlock_title = ?",
                (old_unlock_title,),
            )
        return True

    def set_achievement_enabled(self, unlock_title: str, enabled: bool) -> bool:
        unlock_title = (unlock_title or "").strip()
        if not unlock_title:
            return False
        config_data = self._load_json_config()
        achievement_list = config_data.get("achievements") or []
        found = False
        for achievement_data in achievement_list:
            if str(achievement_data.get("unlock_title") or "").strip() == unlock_title:
                achievement_data["enabled"] = bool(enabled)
                found = True
                break
        if not found:
            return False
        config_data["achievements"] = achievement_list
        return self._save_json_config(config_data)

    def delete_achievement(self, unlock_title: str) -> bool:
        unlock_title = (unlock_title or "").strip()
        if not unlock_title:
            return False
        config_data = self._load_json_config()
        achievement_list = config_data.get("achievements") or []
        new_achievement_list = [
            achievement_data
            for achievement_data in achievement_list
            if str(achievement_data.get("unlock_title") or "").strip() != unlock_title
        ]
        if len(new_achievement_list) == len(achievement_list):
            return False
        config_data["achievements"] = new_achievement_list
        if not self._save_json_config(config_data):
            return False
        self.database_manager.execute(
            "DELETE FROM " + self._table_unlocked + " WHERE unlock_title = ?",
            (unlock_title,),
        )
        return True

    # ---------- 条件 ----------
    def _next_condition_id(self, achievement_list: List[Dict[str, Any]]) -> int:
        max_condition_id = 0
        for achievement_data in achievement_list:
            for condition_data in achievement_data.get("conditions") or []:
                max_condition_id = max(max_condition_id, self._safe_int(condition_data.get("id"), 0))
        return max_condition_id + 1

    def list_conditions(self, unlock_title: str) -> List[Dict[str, Any]]:
        achievement_data = self.get_achievement(unlock_title)
        if not achievement_data:
            return []
        condition_list = []
        for condition_data in achievement_data.get("conditions") or []:
            ct = str(condition_data.get("condition_type") or condition_data.get("type") or "")
            row = {
                "id": self._safe_int(condition_data.get("id"), 0),
                "unlock_title": str(achievement_data.get("unlock_title") or ""),
                "condition_type": ct,
                "target_id": str(condition_data.get("target_id") or ""),
                "required_count": self._safe_int(condition_data.get("required_count"), 0),
            }
            if ct == self.condition_type_kill_entity_sum:
                row["target_ids"] = list(condition_data.get("target_ids") or [])
            else:
                row["target_ids"] = []
            condition_list.append(row)
        return condition_list

    def get_condition(self, condition_id: int) -> Optional[Dict[str, Any]]:
        condition_id = int(condition_id)
        for achievement_data in self.list_achievements():
            unlock_title = str(achievement_data.get("unlock_title") or "")
            for condition_data in achievement_data.get("conditions") or []:
                if self._safe_int(condition_data.get("id"), 0) == condition_id:
                    ct = str(condition_data.get("condition_type") or condition_data.get("type") or "")
                    row = {
                        "id": condition_id,
                        "unlock_title": unlock_title,
                        "condition_type": ct,
                        "target_id": str(condition_data.get("target_id") or ""),
                        "required_count": self._safe_int(condition_data.get("required_count"), 0),
                    }
                    if ct == self.condition_type_kill_entity_sum:
                        row["target_ids"] = list(condition_data.get("target_ids") or [])
                    else:
                        row["target_ids"] = []
                    return row
        return None

    def create_condition(
        self,
        unlock_title: str,
        condition_type: str,
        target_id: str,
        required_count: int,
        target_ids: Optional[Union[str, List[str]]] = None,
    ) -> bool:
        unlock_title = (unlock_title or "").strip()
        condition_type = (condition_type or "").strip()
        target_id = (target_id or "").strip()
        required_count = self._safe_int(required_count, 0)
        if required_count <= 0:
            return False

        if condition_type == self.condition_type_kill_entity_sum:
            normalized_ids = self._normalize_target_ids_list(target_ids)
            if not normalized_ids and target_id:
                normalized_ids = self._normalize_target_ids_list(target_id)
            if len(normalized_ids) < 1:
                return False
        elif condition_type == self.condition_type_kill_entity:
            if not target_id:
                return False
        else:
            return False

        config_data = self._load_json_config()
        achievement_list = config_data.get("achievements") or []
        target_index = -1
        for index, achievement_data in enumerate(achievement_list):
            if str(achievement_data.get("unlock_title") or "").strip() == unlock_title:
                target_index = index
                break
        if target_index < 0:
            return False

        new_condition_id = self._next_condition_id(achievement_list)
        if "conditions" not in achievement_list[target_index] or not isinstance(achievement_list[target_index]["conditions"], list):
            achievement_list[target_index]["conditions"] = []
        if condition_type == self.condition_type_kill_entity_sum:
            new_condition_obj: Dict[str, Any] = {
                "id": new_condition_id,
                "type": condition_type,
                "condition_type": condition_type,
                "target_ids": normalized_ids,
                "required_count": required_count,
            }
        else:
            new_condition_obj = {
                "id": new_condition_id,
                "type": condition_type,
                "condition_type": condition_type,
                "target_id": target_id,
                "required_count": required_count,
            }
        achievement_list[target_index]["conditions"].append(new_condition_obj)
        config_data["achievements"] = achievement_list
        return self._save_json_config(config_data)

    def update_condition(
        self,
        condition_id: int,
        condition_type: str,
        target_id: str,
        required_count: int,
        target_ids: Optional[Union[str, List[str]]] = None,
    ) -> bool:
        condition_id = int(condition_id)
        condition_type = (condition_type or "").strip()
        target_id = (target_id or "").strip()
        required_count = self._safe_int(required_count, 0)
        if required_count <= 0:
            return False

        if condition_type == self.condition_type_kill_entity_sum:
            normalized_ids = self._normalize_target_ids_list(target_ids)
            if not normalized_ids and target_id:
                normalized_ids = self._normalize_target_ids_list(target_id)
            if len(normalized_ids) < 1:
                return False
        elif condition_type == self.condition_type_kill_entity:
            if not target_id:
                return False
        else:
            return False

        config_data = self._load_json_config()
        achievement_list = config_data.get("achievements") or []
        found = False
        for achievement_data in achievement_list:
            for condition_data in achievement_data.get("conditions") or []:
                if self._safe_int(condition_data.get("id"), 0) == condition_id:
                    condition_data["type"] = condition_type
                    condition_data["condition_type"] = condition_type
                    condition_data["required_count"] = required_count
                    if condition_type == self.condition_type_kill_entity_sum:
                        condition_data.pop("target_id", None)
                        condition_data["target_ids"] = normalized_ids
                    else:
                        condition_data.pop("target_ids", None)
                        condition_data["target_id"] = target_id
                    found = True
                    break
            if found:
                break
        if not found:
            return False
        config_data["achievements"] = achievement_list
        return self._save_json_config(config_data)

    def delete_condition(self, condition_id: int) -> bool:
        condition_id = int(condition_id)
        config_data = self._load_json_config()
        achievement_list = config_data.get("achievements") or []
        found = False
        for achievement_data in achievement_list:
            old_condition_list = achievement_data.get("conditions") or []
            new_condition_list = [
                condition_data
                for condition_data in old_condition_list
                if self._safe_int(condition_data.get("id"), 0) != condition_id
            ]
            if len(new_condition_list) != len(old_condition_list):
                achievement_data["conditions"] = new_condition_list
                found = True
                break
        if not found:
            return False
        config_data["achievements"] = achievement_list
        return self._save_json_config(config_data)

    def apply_default_kill_title_definitions(self, title_system) -> bool:
        """
        仅根据内置表写入头衔定义（title_definitions）：稀有度、介绍、金钱、物品。
        应在写入成就条件之前调用。
        """
        try:
            for entry in _DEFAULT_KILL_ACHIEVEMENT_BUNDLE:
                unlock_title = str(entry.get("unlock_title") or "").strip()
                if not unlock_title:
                    continue
                rarity = str(entry.get("rarity") or "普通").strip()
                description = str(entry.get("description") or "").strip()
                reward_money = float(entry.get("reward_money") or 0.0)
                reward_items = entry.get("reward_items") or []
                if not isinstance(reward_items, list):
                    reward_items = []
                title_system.set_title_definition(unlock_title, rarity, description, reward_money, reward_items)
            return True
        except Exception:
            return False

    def apply_default_kill_achievement_bundle(self, title_system) -> bool:
        """先写入默认头衔定义，再写入成就条件（多生物为击杀数相加）。"""
        try:
            if not self.apply_default_kill_title_definitions(title_system):
                return False
            config_data = self._load_json_config()
            achievement_list = config_data.get("achievements") or []
            if not isinstance(achievement_list, list):
                achievement_list = []
            title_index_map = {str(a.get("unlock_title") or "").strip(): idx for idx, a in enumerate(achievement_list)}
            next_condition_id = self._next_condition_id(achievement_list)
            for entry in _DEFAULT_KILL_ACHIEVEMENT_BUNDLE:
                unlock_title = str(entry.get("unlock_title") or "").strip()
                if not unlock_title:
                    continue
                name = str(entry.get("name") or unlock_title).strip()
                entity_ids_raw = entry.get("entity_ids") or []
                entity_ids = [str(x).strip() for x in entity_ids_raw if str(x).strip()]
                required_count = self._safe_int(entry.get("required_count"), 0)
                if required_count <= 0 or not entity_ids:
                    continue
                if len(entity_ids) > 1:
                    cond_obj: Dict[str, Any] = {
                        "id": next_condition_id,
                        "type": self.condition_type_kill_entity_sum,
                        "condition_type": self.condition_type_kill_entity_sum,
                        "target_ids": entity_ids,
                        "required_count": required_count,
                    }
                else:
                    cond_obj = {
                        "id": next_condition_id,
                        "type": self.condition_type_kill_entity,
                        "condition_type": self.condition_type_kill_entity,
                        "target_id": entity_ids[0],
                        "required_count": required_count,
                    }
                next_condition_id += 1
                if unlock_title in title_index_map:
                    idx = title_index_map[unlock_title]
                    achievement_list[idx]["name"] = name
                    achievement_list[idx]["unlock_title"] = unlock_title
                    achievement_list[idx]["enabled"] = True
                    achievement_list[idx]["if_hidden"] = False
                    achievement_list[idx]["logic"] = self.logic_all
                    achievement_list[idx]["conditions"] = [cond_obj]
                else:
                    achievement_list.append(
                        {
                            "name": name,
                            "unlock_title": unlock_title,
                            "enabled": True,
                            "if_hidden": False,
                            "logic": self.logic_all,
                            "conditions": [cond_obj],
                        }
                    )
                    title_index_map[unlock_title] = len(achievement_list) - 1
            config_data["achievements"] = achievement_list
            return self._save_json_config(config_data)
        except Exception:
            return False

    @staticmethod
    def get_default_kill_bundle_size() -> int:
        return DEFAULT_KILL_ACHIEVEMENT_ENTRY_COUNT

