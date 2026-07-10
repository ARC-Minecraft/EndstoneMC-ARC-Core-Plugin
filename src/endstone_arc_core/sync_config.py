# -*- coding: utf-8 -*-
"""跨服同步配置：模式解析与分项表映射"""
from typing import Dict, List, Literal, Set, Tuple

SyncConsumerMode = Literal["none", "client", "file"]

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

FILE_PATH_SETTING_KEYS: Tuple[str, ...] = (
    "PLAYER_DATABASE_PATH",
    "PLAYER_ECONOMY_DATABASE_PATH",
    "PLAYER_TITLE_DATABASE_PATH",
    "GUILD_DATABASE_PATH",
)


def setting_bool(setting_manager, key: str, default: bool = False) -> bool:
    raw = setting_manager.GetSetting(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("true", "1", "yes")


def _non_empty_path(setting_manager, key: str) -> bool:
    raw = setting_manager.GetSetting(key)
    return bool(raw and str(raw).strip())


def has_file_path_sync(setting_manager) -> bool:
    return any(_non_empty_path(setting_manager, key) for key in FILE_PATH_SETTING_KEYS)


def resolve_sync_consumer_mode(setting_manager) -> Tuple[SyncConsumerMode, bool]:
    """解析游戏服跨服消费方式：远程客户端 / 共享文件 / 无。

    返回 (模式, 是否发生冲突)。客户端与文件路径同时启用时以客户端为准。
    """
    client_enabled = setting_bool(setting_manager, "ENABLE_SYNC_CLIENT")
    file_enabled = has_file_path_sync(setting_manager)
    if client_enabled and file_enabled:
        return "client", True
    if client_enabled:
        return "client", False
    if file_enabled:
        return "file", False
    return "none", False


def get_client_sync_tables(setting_manager) -> Set[str]:
    """根据分项开关返回远程客户端需要同步的表名集合。"""
    tables: Set[str] = set()
    for setting_key, category in SYNC_CATEGORY_SETTING_KEYS.items():
        if setting_bool(setting_manager, setting_key, True):
            tables.update(SYNC_CATEGORY_TABLES[category])
    return tables
