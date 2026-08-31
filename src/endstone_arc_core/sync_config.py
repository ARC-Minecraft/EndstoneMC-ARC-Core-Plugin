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

# 同步类别 -> 须以同步中心为准的玩法配置（不含本机路径/端口/身份）
SYNC_CATEGORY_SHARED_SETTINGS: Dict[str, Tuple[str, ...]] = {
    "player": (
        "INVITE_REWARD_ITEM_NAME",
        "INVITE_REWARD_ITEM_COUNT",
        "INVITE_REWARD_MONEY",
        "INVITE_REWARD_FREE_LAND_BLOCKS",
    ),
    "economy": (
        "PLAYER_INIT_MONEY_NUM",
        "HIDE_OP_IN_MONEY_RANKING",
        "RICHEST_TITLE_NAME",
        "SMALL_HORN_PRICE_PER_HOUR",
        "CHECKIN_DAILY_MONEY",
        "CHECKIN_TOP_RANK_LIMIT",
        "CHECKIN_TOP_RANK_BONUS_ITEM_COUNT",
        "CHECKIN_TOP_RANK_BONUS_MONEY_STEP",
        "CHECKIN_CONTINUOUS_DAYS_MONEY_INCREMENT",
        "CHECKIN_REWARD_PICK_MIN",
        "CHECKIN_REWARD_PICK_MAX",
        "CHECKIN_REWARD_LIST",
        "TELEPORT_COST_PUBLIC_WARP",
        "TELEPORT_COST_HOME",
        "TELEPORT_COST_LAND",
        "TELEPORT_COST_DEATH_LOCATION",
        "TELEPORT_COST_RANDOM",
        "TELEPORT_COST_PLAYER",
        "LAND_PRICE",
        "LAND_SELL_REFUND_COEFFICIENT",
        "LAND_SALE_VAT_RATE",
    ),
    "title": (
        "DEFAULT_TITLE",
        "OP_TITLE",
        "RICHEST_TITLE_NAME",
    ),
    "guild": (
        "GUILD_CREATE_COST",
        "GUILD_SIZE_SMALL_MAX",
        "GUILD_SIZE_MEDIUM_MAX",
        "GUILD_SIZE_LARGE_MAX",
        "GUILD_UPGRADE_TO_MEDIUM_COST",
        "GUILD_UPGRADE_TO_LARGE_COST",
        "GUILD_RENAME_COST",
        "GUILD_LAND_TELEPORT_CONTRIB_COST",
        "KILL_REWARD_GUILD_CONTRIB_RATIO",
        "CHECKIN_GUILD_CONTRIBUTION_POINTS",
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


def setting_bool(setting_manager, key: str, default: bool = False) -> bool:
    raw = setting_manager.GetSetting(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("true", "1", "yes")


def resolve_sync_consumer_mode(setting_manager) -> SyncConsumerMode:
    """解析游戏服跨服消费方式：远程客户端 / 无。"""
    if setting_bool(setting_manager, "ENABLE_SYNC_CLIENT"):
        return "client"
    return "none"


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
    """从同步中心配置快照指定类别的玩法键；缺失的键不发送。"""
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
    """只保留本机已启用同步类别、且在白名单内的配置键。"""
    if not isinstance(raw, dict):
        return {}
    allowed = shared_setting_keys_for_categories(categories)
    out: Dict[str, str] = {}
    for key, value in raw.items():
        name = str(key)
        if name in allowed:
            out[name] = "" if value is None else str(value)
    return out
