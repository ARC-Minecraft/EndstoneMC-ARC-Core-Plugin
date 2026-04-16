# -*- coding: utf-8 -*-
"""成就条件：基类 + 各类型子类，便于扩展新条件类型。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from endstone_arc_core.AchievementSystem import AchievementSystem


class AchievementCheckContext:
    """供条件判断时读取统计等数据。"""

    def __init__(self, achievement_system: "AchievementSystem", xuid: str):
        self.achievement_system = achievement_system
        self.xuid = xuid


def _safe_int(value: Any, default_value: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default_value


class AchievementConditionBase(ABC):
    """成就条件抽象基类：子类实现 check_if_satisfied 与击杀索引键。"""

    def __init__(self, condition_id: int, raw_dict: Dict[str, Any]):
        self.condition_id = int(condition_id)
        self.raw_dict = raw_dict

    @property
    @abstractmethod
    def condition_type(self) -> str:
        """与 JSON 中 condition_type / type 一致。"""

    @abstractmethod
    def check_if_satisfied(self, ctx: AchievementCheckContext) -> bool:
        """当前玩家是否满足该条条件。"""

    def kill_index_entity_keys(self) -> List[str]:
        """
        建立「生物类型 → 成就 unlock_title」索引时用到的键。
        仅击杀类条件返回非空；其它类型返回 []。
        键为 minecraft:xxx 或 '*'（任意生物累计，对应 kill_total）。
        """
        return []


class KillEntityKillCountCondition(AchievementConditionBase):
    """单目标击杀累计：kill_entity，target_id 可为 * 表示任意生物总击杀。"""

    def __init__(self, condition_id: int, raw_dict: Dict[str, Any], type_key: str):
        super().__init__(condition_id, raw_dict)
        self._type_key = type_key
        self.target_id = str(raw_dict.get("target_id") or "").strip()
        self.required_count = _safe_int(raw_dict.get("required_count"), 0)

    @property
    def condition_type(self) -> str:
        return self._type_key

    def check_if_satisfied(self, ctx: AchievementCheckContext) -> bool:
        if self.required_count <= 0:
            return False
        sys = ctx.achievement_system
        stat_key = sys._build_stat_key(self._type_key, self.target_id)
        if not stat_key:
            return False
        return sys._get_stat_count(ctx.xuid, stat_key) >= self.required_count

    def kill_index_entity_keys(self) -> List[str]:
        if not self.target_id:
            return []
        return [self.target_id]


class KillEntityKillCountSumCondition(AchievementConditionBase):
    """多目标击杀数相加：kill_entity_sum。"""

    def __init__(self, condition_id: int, raw_dict: Dict[str, Any], type_key: str, target_ids: List[str]):
        super().__init__(condition_id, raw_dict)
        self._type_key = type_key
        self.target_ids = list(target_ids)
        self.required_count = _safe_int(raw_dict.get("required_count"), 0)

    @property
    def condition_type(self) -> str:
        return self._type_key

    def check_if_satisfied(self, ctx: AchievementCheckContext) -> bool:
        if self.required_count <= 0 or not self.target_ids:
            return False
        sys = ctx.achievement_system
        single = sys.condition_type_kill_entity
        total_sum = 0
        for entity_id in self.target_ids:
            stat_key = sys._build_stat_key(single, entity_id)
            if stat_key:
                total_sum += sys._get_stat_count(ctx.xuid, stat_key)
        return total_sum >= self.required_count

    def kill_index_entity_keys(self) -> List[str]:
        return list(self.target_ids)


def build_achievement_condition_from_dict(
    raw_dict: Dict[str, Any],
    kill_entity_type: str,
    kill_entity_sum_type: str,
    normalize_target_ids_fn,
    safe_int_fn,
) -> Optional[AchievementConditionBase]:
    """
    由 JSON 条件字典构造条件对象；未知类型返回 None。
    normalize_target_ids_fn: 与 AchievementSystem._normalize_target_ids_list 相同签名。
    """
    condition_type = str(raw_dict.get("type") or raw_dict.get("condition_type") or "").strip()
    condition_id = safe_int_fn(raw_dict.get("id"), 0)
    if condition_id <= 0:
        return None
    required_count = safe_int_fn(raw_dict.get("required_count"), 0)

    if condition_type == kill_entity_sum_type:
        target_ids = normalize_target_ids_fn(raw_dict.get("target_ids"))
        if not target_ids and raw_dict.get("target_id"):
            target_ids = normalize_target_ids_fn(str(raw_dict.get("target_id") or ""))
        if len(target_ids) < 1 or required_count <= 0:
            return None
        return KillEntityKillCountSumCondition(condition_id, raw_dict, kill_entity_sum_type, target_ids)

    if condition_type == kill_entity_type:
        target_id = str(raw_dict.get("target_id") or "").strip()
        if not target_id or required_count <= 0:
            return None
        return KillEntityKillCountCondition(condition_id, raw_dict, kill_entity_type)

    return None
