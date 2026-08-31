# -*- coding: utf-8 -*-
"""跨服同步配置：模式解析与分项表映射"""
from typing import Dict, Iterable, List, Literal, Optional, Set, Tuple

SyncConsumerMode = Literal["none", "client"]

# 配置键 -> 同步类别
SYNC_CATEGORY_SETTING_KEYS: Dict[str, str] = {
    "SYNC_CLIENT_SYNC_PLAYER": "player",
    "SYNC_CLIENT_SYNC_ECONOMY": "economy",
    "SYNC_CLIENT_SYNC_TITLE": "title",
    "SYNC_CLIENT_SYNC_GUILD": "guild",
}

# 同步类别 -> 数据表（与 sync_protocol.TABLE_TO_ENUM 一致）
SYNC_CATEGORY_TABLES: Dict[str, List[str]] = {
    "player": ["player_basic_info"],
    "economy": ["player_economy"],
    "title": [
        "title_definitions",
        "player_title_unlock_time",
        "player_title_equipped",
    ],
    "guild": ["guilds", "guild_members", "guild_invites"],
}

# 同步类别 -> 全服统一规则（仅同步中心维护；从服只读，随对应数据开关下发）
# 会改写跨服共享资产/体验的规则；签到、传送、领地、邀请奖励等不在此列（各服本地 yml）
SYNC_CATEGORY_SHARED_SETTINGS: Dict[str, Tuple[str, ...]] = {
    "player": (),
    "economy": (
        "PLAYER_INIT_MONEY_NUM",
        "HIDE_OP_IN_MONEY_RANKING",
        "RICHEST_TITLE_NAME",
    ),
    "title": (
        "DEFAULT_TITLE",
        "OP_TITLE",
    ),
    "guild": (
        "GUILD_CREATE_COST",
        "GUILD_SIZE_SMALL_MAX",
        "GUILD_SIZE_MEDIUM_MAX",
        "GUILD_SIZE_LARGE_MAX",
        "GUILD_UPGRADE_TO_MEDIUM_COST",
        "GUILD_UPGRADE_TO_LARGE_COST",
        "GUILD_RENAME_COST",
    ),
}

ALL_SHARED_SETTING_KEYS: frozenset = frozenset(
    key
    for keys in SYNC_CATEGORY_SHARED_SETTINGS.values()
    for key in keys
)

SYNC_TABLE_TO_CATEGORY: Dict[str, str] = {
    table: category
    for category, tables in SYNC_CATEGORY_TABLES.items()
    for table in tables
}


def is_hub_rule_setting(key: str) -> bool:
    return str(key) in ALL_SHARED_SETTING_KEYS


def setting_bool(setting_manager, key: str, default: bool = False) -> bool:
    raw = setting_manager.GetSetting(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("true", "1", "yes")


def is_sync_hub_enabled(setting_manager) -> bool:
    return setting_bool(setting_manager, "ENABLE_SYNC_SERVER")


def resolve_sync_consumer_mode(setting_manager) -> SyncConsumerMode:
    """解析游戏服跨服消费方式：远程客户端 / 无。"""
    if setting_bool(setting_manager, "ENABLE_SYNC_CLIENT"):
        return "client"
    return "none"


def can_edit_setting_key(setting_manager, key: str) -> bool:
    """从服上的全服规则只读；同步中心与未开同步的本服均可改本地玩法。"""
    if not is_hub_rule_setting(key):
        return True
    if is_sync_hub_enabled(setting_manager):
        return True
    if resolve_sync_consumer_mode(setting_manager) == "client":
        return False
    return True


def get_client_sync_tables(setting_manager) -> Set[str]:
    """根据分项开关返回远程客户端需要同步的表名集合。"""
    tables: Set[str] = set()
    for setting_key, category in SYNC_CATEGORY_SETTING_KEYS.items():
        if setting_bool(setting_manager, setting_key, True):
            tables.update(SYNC_CATEGORY_TABLES[category])
    return tables


def get_client_sync_categories(setting_manager) -> Set[str]:
    """根据分项开关返回远程客户端启用的同步类别。"""
    categories: Set[str] = set()
    for setting_key, category in SYNC_CATEGORY_SETTING_KEYS.items():
        if setting_bool(setting_manager, setting_key, True):
            categories.add(category)
    return categories


def categories_from_tables(tables: Iterable[str]) -> Set[str]:
    return {SYNC_TABLE_TO_CATEGORY[t] for t in tables if t in SYNC_TABLE_TO_CATEGORY}


def shared_setting_keys_for_categories(categories: Iterable[str]) -> Set[str]:
    keys: Set[str] = set()
    for category in categories:
        keys.update(SYNC_CATEGORY_SHARED_SETTINGS.get(category, ()))
    return keys


def snapshot_shared_settings(setting_manager, categories: Iterable[str]) -> Dict[str, str]:
    """从同步中心配置快照指定类别的全服规则；缺失的键不发送。"""
    out: Dict[str, str] = {}
    getter = getattr(setting_manager, "get_existing", None)
    for key in shared_setting_keys_for_categories(categories):
        if getter is None:
            raw = setting_manager.GetSetting(key)
            if raw is None:
                continue
            out[key] = str(raw)
            continue
        existing = getter(key)
        if existing is None:
            continue
        out[key] = existing
    return out


def filter_incoming_settings(
    raw: Optional[Dict], categories: Iterable[str]
) -> Dict[str, str]:
    """只保留本机已启用同步类别、且在白名单内的全服规则键。"""
    if not isinstance(raw, dict):
        return {}
    allowed = shared_setting_keys_for_categories(categories)
    out: Dict[str, str] = {}
    for key, value in raw.items():
        name = str(key)
        if name in allowed:
            out[name] = "" if value is None else str(value)
    return out
