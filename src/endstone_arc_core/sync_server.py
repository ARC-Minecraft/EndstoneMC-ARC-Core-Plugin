# -*- coding: utf-8 -*-
"""跨服数据同步后端服务端"""
import json
import socket
import threading
import time
import uuid
from contextlib import suppress
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field

from endstone_arc_core.sync_protocol import (
    SyncMessageType,
    SyncTable,
    TABLE_TO_ENUM,
    ENUM_TO_TABLE,
    decode_message,
    encode_message,
    build_auth_response,
    build_query_response,
    build_data_response,
    build_batch_sync_response,
    build_full_sync_response,
    build_heartbeat,
    build_push_notify,
    build_qq_chat_downstream,
    build_error_response,
)
from endstone_arc_core.sync_write import iter_mirror_write_actions, query_sync_table, select_all_sync_table


@dataclass(eq=False)
class ConnectedClient:
    """已连接的客户端（按对象身份参与 set，字段可变）"""
    conn: socket.socket
    addr: tuple
    server_id: str = ""
    server_name: str = ""
    authenticated: bool = False
    last_heartbeat: float = field(default_factory=time.time)
    sync_tables: Set[str] = field(default_factory=set)
    
    def is_alive(self) -> bool:
        """检查连接是否存活（心跳超时 60 秒）"""
        return time.time() - self.last_heartbeat < 60


class SyncServer:
    """跨服数据同步后端服务端
    
    运行在独立的线程中，接收来自多个插件端服务器的连接请求，
    并将数据变更同步给所有已连接的客户端。
    """

    def __init__(
        self,
        database_manager,
        auth_key: str = "",
        bind_host: str = "0.0.0.0",  # nosec B104 — 跨服同步中心需监听所有网卡
        bind_port: int = 19999,
        logger=None,
        on_event_forward: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """
        初始化同步服务器
        
        :param database_manager: 数据库管理器实例
        :param auth_key: 认证密钥
        :param bind_host: 绑定地址
        :param bind_port: 绑定端口
        :param logger: 日志记录器
        :param on_event_forward: 子服 EVENT_FORWARD 回调（主机侧转 qqsync）
        """
        self.db = database_manager
        self.auth_key = auth_key
        self.bind_host = bind_host
        self.bind_port = bind_port
        self.logger = logger
        self.on_event_forward = on_event_forward
        
        self._socket: Optional[socket.socket] = None
        self._running = False
        self._server_thread: Optional[threading.Thread] = None
        self._clients: Set[ConnectedClient] = set()
        self._clients_lock = threading.Lock()
        
        # 需要同步的表列表
        self._sync_tables = set(TABLE_TO_ENUM.keys())
        
        # 变更记录队列（用于异步推送给客户端）
        self._change_queue: List[Dict[str, Any]] = []
        self._change_queue_lock = threading.Lock()
        
        # 全量同步锁（防止同步期间数据不一致）
        self._full_sync_lock = threading.Lock()

    def _log(self, level: str, message: str):
        """安全日志记录"""
        if self.logger:
            getattr(self.logger, level.lower(), self.logger.info)(f"[ARC SyncServer] {message}")
        else:
            print(f"[{level.upper()}] [ARC SyncServer] {message}")

    def start(self) -> bool:
        """启动同步服务器"""
        if self._running:
            self._log("warning", "Server is already running")
            return True
        
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self.bind_host, self.bind_port))
            self._socket.listen(10)
            self._socket.settimeout(5.0)  # 5秒超时，用于检查_running标志
            
            self._running = True
            self._server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self._server_thread.start()
            
            self._log("info", f"Sync server started on {self.bind_host}:{self.bind_port}")
            return True
        except Exception as e:
            self._log("error", f"Failed to start sync server: {e}")
            self._running = False
            return False

    def stop(self):
        """停止同步服务器"""
        if not self._running:
            return
        
        self._running = False
        
        # 关闭所有客户端连接
        with self._clients_lock:
            for client in self._clients:
                with suppress(OSError):
                    client.conn.close()
            self._clients.clear()

        if self._socket:
            with suppress(OSError):
                self._socket.close()
            self._socket = None
        
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=5)
        
        self._log("info", "Sync server stopped")

    def is_running(self) -> bool:
        """检查服务器是否运行中"""
        return self._running

    def _server_loop(self):
        """服务器主循环"""
        while self._running:
            try:
                client_socket, addr = self._socket.accept()
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, addr),
                    daemon=True
                )
                client_thread.start()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    self._log("error", f"Accept connection error: {e}")
                break
        
        # 清理客户端
        self._cleanup_dead_clients()

    def _handle_client(self, conn: socket.socket, addr: tuple):
        """处理客户端连接"""
        client = ConnectedClient(conn=conn, addr=addr)
        buffer = b""
        
        try:
            conn.settimeout(30.0)
            
            while self._running:
                try:
                    data = conn.recv(4096)
                    if not data:
                        break
                    
                    buffer += data
                    
                    # 处理粘包
                    while len(buffer) >= 5:
                        msg_len = int.from_bytes(buffer[:4], 'big')
                        if len(buffer) < 5 + msg_len:
                            break  # 数据不完整，等待更多数据
                        
                        raw_msg = buffer[:5 + msg_len]
                        buffer = buffer[5 + msg_len:]
                        
                        self._process_message(client, raw_msg)
                        
                except socket.timeout:
                    if not client.authenticated:
                        break  # 未认证的客户端超时断开
                    continue
                except Exception as e:
                    self._log("error", f"Client {addr} error: {e}")
                    break
            
        except Exception as e:
            self._log("error", f"Client {addr} handler error: {e}")
        finally:
            # 移除客户端
            with self._clients_lock:
                self._clients.discard(client)
            try:
                conn.close()
            except Exception:
                pass
            self._log("info", f"Client {addr} disconnected")

    def _process_message(self, client: ConnectedClient, raw_msg: bytes):
        """处理接收到的消息"""
        try:
            msg_type, data = decode_message(raw_msg)
            client.last_heartbeat = time.time()

            if msg_type == SyncMessageType.AUTH_REQUEST:
                self._handle_auth(client, data)
                return
            if msg_type == SyncMessageType.HEARTBEAT:
                self._handle_heartbeat(client)
                return
            if not client.authenticated:
                client.conn.sendall(build_error_response(1, "Not authenticated"))
                return

            handler = self._AUTHED_HANDLERS.get(msg_type)
            if handler:
                handler(self, client, data)
            else:
                client.conn.sendall(
                    build_error_response(2, f"Unknown message type: {msg_type}")
                )
        except Exception as e:
            self._log("error", f"Process message error: {e}")
            try:
                client.conn.sendall(build_error_response(3, str(e)))
            except Exception:
                pass

    # 已认证后的消息分发（避免长 elif 链抬高圈复杂度）
    _AUTHED_HANDLERS = {
        SyncMessageType.QUERY_REQUEST: lambda self, c, d: self._handle_query(c, d),
        SyncMessageType.INSERT_REQUEST: lambda self, c, d: self._handle_insert(c, d),
        SyncMessageType.UPDATE_REQUEST: lambda self, c, d: self._handle_update(c, d),
        SyncMessageType.DELETE_REQUEST: lambda self, c, d: self._handle_delete(c, d),
        SyncMessageType.BATCH_SYNC_REQUEST: lambda self, c, d: self._handle_batch_sync(c, d),
        SyncMessageType.FULL_SYNC_REQUEST: lambda self, c, d: self._handle_full_sync(c, d),
        SyncMessageType.PULL_REQUEST: lambda self, c, d: self._handle_pull(c, d),
        SyncMessageType.EVENT_FORWARD: lambda self, c, d: self._handle_event_forward(c, d),
    }

    def _handle_auth(self, client: ConnectedClient, data: Dict):
        """处理认证请求"""
        server_id = data.get('server_id', '')
        server_name = data.get('server_name', '')
        auth_key = data.get('auth_key', '')
        
        if self.auth_key and auth_key != self.auth_key:
            client.conn.sendall(build_auth_response(False, "Invalid auth key"))
            self._log("warning", f"Auth failed for {client.addr}: invalid key")
            return
        
        client.server_id = server_id
        client.server_name = server_name
        client.authenticated = True

        requested_tables = data.get('sync_tables')
        if isinstance(requested_tables, list):
            # 空列表表示仅事件转发、不同步任何表
            client.sync_tables = {
                str(t) for t in requested_tables if str(t) in self._sync_tables
            }
        else:
            client.sync_tables = set(self._sync_tables)
        
        with self._clients_lock:
            self._clients.add(client)
        
        client.conn.sendall(build_auth_response(True, "Authentication successful"))
        self._log("info", f"Client authenticated: {server_name} ({server_id}) from {client.addr}")

    def _handle_heartbeat(self, client: ConnectedClient):
        """处理心跳包"""
        client.last_heartbeat = time.time()
        try:
            client.conn.sendall(build_heartbeat())
        except Exception:
            pass

    def _handle_event_forward(self, client: ConnectedClient, data: Dict):
        """处理子服 QQ/群事件转发（不要求响应，避免与数据同步阻塞）"""
        if not self.on_event_forward:
            self._log(
                "warning",
                f"EVENT_FORWARD from {client.server_name or data.get('server_name') or '?'} "
                "ignored (no handler)",
            )
            return
        try:
            self.on_event_forward(
                {
                    "event_type": str(data.get("event_type") or "custom"),
                    "display_name": str(data.get("display_name") or ""),
                    "raw_player_name": str(data.get("raw_player_name") or ""),
                    "message": str(data.get("message") or ""),
                    "server_id": client.server_id or str(data.get("server_id") or ""),
                    "server_name": client.server_name or str(data.get("server_name") or ""),
                }
            )
        except Exception as e:
            self._log("error", f"EVENT_FORWARD handler error: {e}")

    def _handle_query(self, client: ConnectedClient, data: Dict):
        """处理查询请求"""
        try:
            table_enum = SyncTable(data.get('table', 0))
            table_name = ENUM_TO_TABLE.get(table_enum)
            where = data.get('where', '1=1')
            params = data.get('params', [])
            
            if table_name not in self._sync_tables:
                client.conn.sendall(build_query_response(False, [], "Table not allowed"))
                return
            
            results = query_sync_table(self.db, table_name, where, tuple(params))
            client.conn.sendall(build_query_response(True, results))
        except Exception as e:
            client.conn.sendall(build_query_response(False, [], str(e)))
            self._log("error", f"Query error: {e}")

    def _apply_client_mutation(
        self,
        client: ConnectedClient,
        data: Dict,
        *,
        log_label: str,
        mutate,
        push_op: str,
        push_data: Dict,
    ) -> None:
        """校验表权限 → 抑制通知写库 → 成功则广播 → 回响应。"""
        try:
            table_enum = SyncTable(data.get('table', 0))
            table_name = ENUM_TO_TABLE.get(table_enum)
            if table_name not in self._sync_tables:
                client.conn.sendall(build_data_response(False, 0, "Table not allowed"))
                return
            with self.db.suppress_write_notify():
                success = mutate(table_name)
            if success:
                self._broadcast_push(
                    SyncTable(table_enum), push_op, push_data, exclude=client
                )
            client.conn.sendall(build_data_response(success, 1 if success else 0))
        except Exception as e:
            client.conn.sendall(build_data_response(False, 0, str(e)))
            self._log("error", f"{log_label} error: {e}")

    def _handle_insert(self, client: ConnectedClient, data: Dict):
        """处理插入/整行 upsert 请求"""
        row_data = data.get('data', {})
        self._apply_client_mutation(
            client,
            data,
            log_label="Insert",
            mutate=lambda t: self.db.upsert(t, row_data),
            push_op="insert",
            push_data=row_data,
        )

    def _handle_update(self, client: ConnectedClient, data: Dict):
        """处理更新请求"""
        row_data = data.get('data', {})
        where = data.get('where', '')
        params = data.get('params', [])
        self._apply_client_mutation(
            client,
            data,
            log_label="Update",
            mutate=lambda t: self.db.update(t, row_data, where, tuple(params)),
            push_op="update",
            push_data={**row_data, '_where': where, '_params': params},
        )

    def _handle_delete(self, client: ConnectedClient, data: Dict):
        """处理删除请求"""
        where = data.get('where', '')
        params = data.get('params', [])
        self._apply_client_mutation(
            client,
            data,
            log_label="Delete",
            mutate=lambda t: self.db.delete(t, where, tuple(params)),
            push_op="delete",
            push_data={'_where': where, '_params': params},
        )

    def _run_batch_op(self, op_type: str, table_name: str, op: Dict) -> Dict:
        runners = {
            "insert": lambda: self.db.upsert(table_name, op.get("data", {})),
            "update": lambda: self.db.update(
                table_name,
                op.get("data", {}),
                op.get("where", ""),
                tuple(op.get("params", [])),
            ),
            "delete": lambda: self.db.delete(
                table_name, op.get("where", ""), tuple(op.get("params", []))
            ),
        }
        runner = runners.get(op_type)
        if not runner:
            return {"success": False, "error": "Unknown operation type"}
        with self.db.suppress_write_notify():
            return {"success": runner()}

    def _broadcast_batch_op(self, client: ConnectedClient, op: Dict) -> None:
        table_enum = SyncTable(op.get("table", 0))
        op_type = op.get("type")
        if op_type == "insert":
            self._broadcast_push(table_enum, "insert", op.get("data", {}), exclude=client)
        elif op_type == "update":
            self._broadcast_push(table_enum, "update", op.get("data", {}), exclude=client)
        elif op_type == "delete":
            self._broadcast_push(
                table_enum,
                "delete",
                {"_where": op.get("where", ""), "_params": op.get("params", [])},
                exclude=client,
            )

    def _handle_batch_sync(self, client: ConnectedClient, data: Dict):
        """处理批量同步请求"""
        try:
            operations = data.get("operations", [])
            results = []
            for op in operations:
                table_name = ENUM_TO_TABLE.get(SyncTable(op.get("table", 0)))
                if table_name not in self._sync_tables:
                    results.append({"success": False, "error": "Table not allowed"})
                    continue
                results.append(self._run_batch_op(op.get("type"), table_name, op))

            client.conn.sendall(build_batch_sync_response(True, results))
            for op, result in zip(operations, results):
                if result.get("success"):
                    self._broadcast_batch_op(client, op)
        except Exception as e:
            client.conn.sendall(build_batch_sync_response(False, [], str(e)))
            self._log("error", f"Batch sync error: {e}")

    def _handle_full_sync(self, client: ConnectedClient, data: Dict):
        """处理全量同步请求"""
        with self._full_sync_lock:
            try:
                table_enum = SyncTable(data.get('table', 0))
                table_name = ENUM_TO_TABLE.get(table_enum)
                
                if table_name not in self._sync_tables:
                    client.conn.sendall(build_full_sync_response(False, [], "Table not allowed"))
                    return
                
                rows = select_all_sync_table(self.db, table_name)
                client.conn.sendall(build_full_sync_response(True, rows))
                self._log("info", f"Full sync for {table_name}: {len(rows)} rows to {client.server_name}")
            except Exception as e:
                client.conn.sendall(build_full_sync_response(False, [], str(e)))
                self._log("error", f"Full sync error: {e}")

    def _handle_pull(self, client: ConnectedClient, data: Dict):
        """处理拉取请求"""
        try:
            table_enum = SyncTable(data.get('table', 0))
            where = data.get('where', '1=1')
            params = data.get('params', [])
            
            table_name = ENUM_TO_TABLE.get(table_enum)
            if table_name not in self._sync_tables:
                client.conn.sendall(build_query_response(False, [], "Table not allowed"))
                return
            
            results = query_sync_table(self.db, table_name, where, tuple(params))
            client.conn.sendall(build_query_response(True, results))
        except Exception as e:
            client.conn.sendall(build_query_response(False, [], str(e)))

    def _broadcast_push(self, table: SyncTable, operation: str, data: Dict, exclude: Optional[ConnectedClient] = None):
        """广播推送通知给所有已连接的客户端"""
        table_name = ENUM_TO_TABLE.get(table)
        msg = build_push_notify(table, operation, data)
        disconnected = []
        
        with self._clients_lock:
            for client in self._clients:
                if client is exclude:
                    continue
                if table_name and client.sync_tables and table_name not in client.sync_tables:
                    continue
                if not client.is_alive():
                    disconnected.append(client)
                    continue
                try:
                    client.conn.sendall(msg)
                except Exception:
                    disconnected.append(client)
            
            # 移除断开的客户端
            for client in disconnected:
                self._clients.discard(client)

    def _cleanup_dead_clients(self):
        """清理已断开的客户端"""
        disconnected = []
        
        with self._clients_lock:
            for client in self._clients:
                if not client.is_alive():
                    disconnected.append(client)
            
            for client in disconnected:
                self._clients.discard(client)
                try:
                    client.conn.close()
                except Exception:
                    pass
        
        if disconnected:
            self._log("info", f"Cleaned up {len(disconnected)} dead clients")

    def mirror_local_write(self, kind: str, table: str, **kwargs) -> None:
        """主机本地写库后广播给已连接的子服（库已改好，只推送）。"""
        if table not in self._sync_tables:
            return
        table_enum = TABLE_TO_ENUM.get(table)
        if table_enum is None:
            return
        try:
            for action in iter_mirror_write_actions(self.db, kind, table, **kwargs):
                if action[0] == "delete":
                    _, where, params = action
                    self._broadcast_push(
                        table_enum, "delete", {"_where": where, "_params": params}
                    )
                else:
                    self._broadcast_push(table_enum, "insert", action[1])
        except Exception as e:
            self._log("error", f"Mirror local write {table}/{kind} error: {e}")

    def broadcast_qq_chat(
        self, display_name: str, message: str, group_name: str = ""
    ) -> None:
        """将 QQ 群聊下发给所有已认证子服。"""
        if not display_name or not message:
            return
        msg = build_qq_chat_downstream(display_name, message, group_name)
        disconnected = []
        with self._clients_lock:
            for client in self._clients:
                if not client.authenticated:
                    continue
                try:
                    client.conn.sendall(msg)
                except Exception:
                    disconnected.append(client)
            for client in disconnected:
                self._clients.discard(client)

    def get_connected_count(self) -> int:
        """获取已连接的客户端数量"""
        with self._clients_lock:
            return len([c for c in self._clients if c.authenticated])

    def get_client_list(self) -> List[Dict[str, str]]:
        """获取客户端列表"""
        with self._clients_lock:
            return [
                {
                    'server_id': c.server_id,
                    'server_name': c.server_name,
                    'addr': f"{c.addr[0]}:{c.addr[1]}",
                    'last_heartbeat': c.last_heartbeat,
                }
                for c in self._clients if c.authenticated
            ]