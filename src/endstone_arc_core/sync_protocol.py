# -*- coding: utf-8 -*-
"""跨服数据同步协议定义"""
from enum import IntEnum
from typing import Any, Dict, List, Optional


class SyncMessageType(IntEnum):
    """同步消息类型枚举"""
    # 认证相关
    AUTH_REQUEST = 0x01          # 客户端认证请求
    AUTH_RESPONSE = 0x02          # 认证响应

    # 数据操作
    QUERY_REQUEST = 0x10         # 查询数据请求
    QUERY_RESPONSE = 0x11         # 查询数据响应
    INSERT_REQUEST = 0x12        # 插入数据请求
    INSERT_RESPONSE = 0x13        # 插入数据响应
    UPDATE_REQUEST = 0x14         # 更新数据请求
    UPDATE_RESPONSE = 0x15        # 更新数据响应
    DELETE_REQUEST = 0x16        # 删除数据请求
    DELETE_RESPONSE = 0x17        # 删除数据响应

    # 批量操作
    BATCH_SYNC_REQUEST = 0x20     # 批量同步请求
    BATCH_SYNC_RESPONSE = 0x21    # 批量同步响应
    FULL_SYNC_REQUEST = 0x22      # 全量同步请求（用于首次连接）
    FULL_SYNC_RESPONSE = 0x23    # 全量同步响应

    # 心跳和状态
    HEARTBEAT = 0x30              # 心跳包
    SERVER_STATUS = 0x31         # 服务器状态查询
    PULL_REQUEST = 0x32          # 拉取数据请求（客户端主动拉取）
    PUSH_NOTIFY = 0x33           # 服务器推送通知（服务器端数据变更）

    # 错误和响应
    ERROR_RESPONSE = 0xFF         # 错误响应


class SyncTable(IntEnum):
    """可同步的数据表枚举"""
    PLAYER_BASIC_INFO = 0x01      # 玩家基本信息
    PLAYER_ECONOMY = 0x02         # 玩家经济数据
    PLAYER_TITLE = 0x03           # 玩家称号数据
    TITLE_DEFINITIONS = 0x04      # 称号定义
    PLAYER_TITLE_UNLOCK_TIME = 0x05  # 玩家称号解锁时间
    PLAYER_TITLE_EQUIPPED = 0x06  # 玩家佩戴称号
    GUILD = 0x10                  # 公会信息
    GUILD_MEMBERS = 0x11          # 公会成员
    GUILD_INVITES = 0x12          # 公会邀请


# 表名到枚举的映射
TABLE_TO_ENUM = {
    'player_basic_info': SyncTable.PLAYER_BASIC_INFO,
    'player_economy': SyncTable.PLAYER_ECONOMY,
    'player_title': SyncTable.PLAYER_TITLE,
    'title_definitions': SyncTable.TITLE_DEFINITIONS,
    'player_title_unlock_time': SyncTable.PLAYER_TITLE_UNLOCK_TIME,
    'player_title_equipped': SyncTable.PLAYER_TITLE_EQUIPPED,
    'guilds': SyncTable.GUILD,
    'guild_members': SyncTable.GUILD_MEMBERS,
    'guild_invites': SyncTable.GUILD_INVITES,
}

ENUM_TO_TABLE = {v: k for k, v in TABLE_TO_ENUM.items()}


def encode_message(msg_type: SyncMessageType, data: Dict[str, Any]) -> bytes:
    """将消息编码为字节流
    
    格式: [4字节长度][1字节类型][JSON数据]
    """
    import json
    json_bytes = json.dumps(data, ensure_ascii=False).encode('utf-8')
    # 4字节长度 (大端序)
    length_bytes = len(json_bytes).to_bytes(4, 'big')
    # 1字节类型
    type_byte = bytes([msg_type])
    return length_bytes + type_byte + json_bytes


def decode_message(raw: bytes) -> tuple[SyncMessageType, Dict[str, Any]]:
    """解码字节流为消息
    
    返回: (消息类型, 数据字典)
    """
    import json
    if len(raw) < 5:
        raise ValueError("消息长度不足")
    
    # 跳过4字节长度
    json_bytes = raw[5:]
    msg_type = SyncMessageType(raw[4])
    data = json.loads(json_bytes.decode('utf-8'))
    return msg_type, data


def build_auth_request(
    server_id: str,
    server_name: str,
    auth_key: str,
    sync_tables: Optional[List[str]] = None,
) -> bytes:
    """构建认证请求"""
    payload = {
        'server_id': server_id,
        'server_name': server_name,
        'auth_key': auth_key,
    }
    if sync_tables is not None:
        payload['sync_tables'] = sync_tables
    return encode_message(SyncMessageType.AUTH_REQUEST, payload)


def build_auth_response(success: bool, message: str = "") -> bytes:
    """构建认证响应"""
    return encode_message(SyncMessageType.AUTH_RESPONSE, {
        'success': success,
        'message': message,
    })


def build_query_request(table: SyncTable, where: str, params: List) -> bytes:
    """构建查询请求"""
    return encode_message(SyncMessageType.QUERY_REQUEST, {
        'table': int(table),
        'where': where,
        'params': params,
    })


def build_query_response(success: bool, results: List[Dict], error: str = "") -> bytes:
    """构建查询响应"""
    return encode_message(SyncMessageType.QUERY_RESPONSE, {
        'success': success,
        'results': results,
        'error': error,
    })


def build_data_request(
    msg_type: SyncMessageType,
    table: SyncTable,
    data: Dict[str, Any],
    where: str = "",
    params: List = None
) -> bytes:
    """构建数据操作请求（插入/更新/删除）"""
    payload = {
        'table': int(table),
        'data': data,
    }
    if where:
        payload['where'] = where
    if params:
        payload['params'] = params
    return encode_message(msg_type, payload)


def build_data_response(success: bool, affected_rows: int = 0, error: str = "") -> bytes:
    """构建数据操作响应"""
    return encode_message(SyncMessageType.ERROR_RESPONSE, {
        'success': success,
        'affected_rows': affected_rows,
        'error': error,
    })


def build_batch_sync_request(operations: List[Dict[str, Any]]) -> bytes:
    """构建批量同步请求"""
    return encode_message(SyncMessageType.BATCH_SYNC_REQUEST, {
        'operations': operations,
    })


def build_batch_sync_response(success: bool, results: List[Dict], error: str = "") -> bytes:
    """构建批量同步响应"""
    return encode_message(SyncMessageType.BATCH_SYNC_RESPONSE, {
        'success': success,
        'results': results,
        'error': error,
    })


def build_full_sync_request(table: SyncTable) -> bytes:
    """构建全量同步请求"""
    return encode_message(SyncMessageType.FULL_SYNC_REQUEST, {
        'table': int(table),
    })


def build_full_sync_response(success: bool, rows: List[Dict], error: str = "") -> bytes:
    """构建全量同步响应"""
    return encode_message(SyncMessageType.FULL_SYNC_RESPONSE, {
        'success': success,
        'rows': rows,
        'error': error,
    })


def build_heartbeat() -> bytes:
    """构建心跳包"""
    return encode_message(SyncMessageType.HEARTBEAT, {})


def build_error_response(error_code: int, error_message: str) -> bytes:
    """构建错误响应"""
    return encode_message(SyncMessageType.ERROR_RESPONSE, {
        'error_code': error_code,
        'message': error_message,
    })


def build_push_notify(table: SyncTable, operation: str, row_data: Dict) -> bytes:
    """构建推送通知"""
    return encode_message(SyncMessageType.PUSH_NOTIFY, {
        'table': int(table),
        'operation': operation,  # 'insert', 'update', 'delete'
        'data': row_data,
    })