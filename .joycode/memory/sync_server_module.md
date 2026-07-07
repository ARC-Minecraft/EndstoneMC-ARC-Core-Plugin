---
name: ARC Core 后端同步模块
description: 为 ARCCore 插件添加跨服数据同步后端服务
type: project
---

## 模块文件

| 文件 | 用途 |
|---|---|
| `sync_protocol.py` | 同步协议定义（消息类型、表枚举、编解码） |
| `sync_server.py` | 后端服务端实现（TCP监听、客户端管理、广播推送） |

## SyncServer 核心设计

- **多线程架构**：主线程监听 + 每个客户端独立线程处理
- **认证机制**：可选 auth_key 验证
- **心跳检测**：60秒超时断开
- **广播推送**：数据变更实时推送给所有客户端（除发起者）
- **粘包处理**：4字节长度字段 + 缓冲区循环解码

## 配置项 (core_setting.yml)

```yaml
# 服务器端模式
ENABLE_SYNC_SERVER=False
SYNC_SERVER_PORT=19999
SYNC_SERVER_AUTH_KEY=

# 客户端模式（待实现 sync_client.py）
ENABLE_SYNC_CLIENT=False
SYNC_SERVER_IP=127.0.0.1
SYNC_CLIENT_SERVER_ID=server_001
SYNC_CLIENT_SERVER_NAME=服务器01
SYNC_CLIENT_AUTH_KEY=
```

## 已集成

- ✅ `arc_core_plugin.py`：导入 SyncServer，添加 `_init_sync_service()` 初始化
- ✅ `README.md`：添加配置示例文档