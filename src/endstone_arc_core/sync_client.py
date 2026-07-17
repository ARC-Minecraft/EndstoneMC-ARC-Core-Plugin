# -*- coding: utf-8 -*-
"""跨服数据同步客户端：连接同步中心并拉取/接收推送"""
import socket
import threading
import time
from contextlib import suppress
from typing import Any, Dict, Optional, Set

from endstone_arc_core.sync_config import get_client_sync_tables, get_qq_relay_mode
from endstone_arc_core.sync_protocol import (
    SyncMessageType,
    SyncTable,
    TABLE_TO_ENUM,
    ENUM_TO_TABLE,
    build_auth_request,
    build_data_request,
    build_event_forward,
    build_full_sync_request,
    build_heartbeat,
    decode_message,
)
from endstone_arc_core.sync_write import iter_mirror_write_actions


class SyncClient:
    """连接远程同步中心，按配置分项同步数据到本地数据库。

    断线或主机不可达时，按 SYNC_CLIENT_RECONNECT_INTERVAL 秒定时重连。
    """

    def __init__(self, database_manager, setting_manager, logger=None, on_qq_chat=None):
        self.db = database_manager
        self.settings = setting_manager
        self.logger = logger
        self.on_qq_chat = on_qq_chat

        self.server_ip = str(setting_manager.GetSetting("SYNC_SERVER_IP") or "127.0.0.1").strip()
        self.server_id = str(setting_manager.GetSetting("SYNC_CLIENT_SERVER_ID") or "server_001").strip()
        self.server_name = str(
            setting_manager.GetSetting("SYNC_CLIENT_SERVER_NAME") or "服务器01"
        ).strip()
        self.auth_key = str(setting_manager.GetSetting("SYNC_CLIENT_AUTH_KEY") or "").strip()
        self.server_port = self._setting_int("SYNC_CLIENT_PORT", 19999, fallback_key="SYNC_SERVER_PORT")
        self.reconnect_interval = max(1, self._setting_int("SYNC_CLIENT_RECONNECT_INTERVAL", 10))

        self.enabled_tables: Set[str] = get_client_sync_tables(setting_manager)
        self.qq_relay_host = get_qq_relay_mode(setting_manager) == "host"

        self._socket: Optional[socket.socket] = None
        self._active = False  # 希望保持连接（允许断线重连）
        self._worker_thread: Optional[threading.Thread] = None
        self._socket_lock = threading.Lock()

    def _setting_int(self, key: str, default: int, fallback_key: str = "") -> int:
        raw = self.settings.GetSetting(key)
        if (raw is None or not str(raw).strip()) and fallback_key:
            raw = self.settings.GetSetting(fallback_key)
        try:
            return int(raw) if raw is not None and str(raw).strip() else default
        except (ValueError, TypeError):
            return default

    def _log(self, level: str, message: str) -> None:
        if self.logger:
            getattr(self.logger, level.lower(), self.logger.info)(f"[ARC SyncClient] {message}")
        else:
            print(f"[{level.upper()}] [ARC SyncClient] {message}")

    def start(self) -> bool:
        """启动客户端后台线程（断线后自动重连）。"""
        if self._active:
            return True
        if not self.enabled_tables and not self.qq_relay_host:
            self._log(
                "warning",
                "No sync categories enabled (SYNC_CLIENT_SYNC_* all False) "
                "and QQ_RELAY_MODE is not host; client not started",
            )
            return False

        self._active = True
        self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._worker_thread.start()
        self._log(
            "info",
            f"Sync client started → {self.server_ip}:{self.server_port} "
            f"(reconnect every {self.reconnect_interval}s)",
        )
        return True

    def stop(self) -> None:
        """停止客户端并取消重连。"""
        self._active = False
        self._close_socket()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=self.reconnect_interval + 5)
        self._worker_thread = None

    def is_running(self) -> bool:
        """当前是否已与同步中心建立连接。"""
        with self._socket_lock:
            return self._active and self._socket is not None

    def send_event_forward(
        self,
        event_type: str,
        display_name: str,
        raw_player_name: str,
        message: str = "",
    ) -> bool:
        """将 QQ/群相关游戏事件转发到同步中心（由主机 qqsync 发送）。"""
        if not self.is_running():
            return False
        try:
            self._send(
                build_event_forward(
                    event_type=event_type,
                    display_name=display_name,
                    raw_player_name=raw_player_name,
                    message=message,
                    server_id=self.server_id,
                    server_name=self.server_name,
                )
            )
            return True
        except Exception as e:
            self._log("error", f"Send event forward error: {e}")
            return False

    def mirror_local_write(self, kind: str, table: str, **kwargs) -> None:
        """本地业务写库后上行到同步中心（fire-and-forget，响应由监听线程丢弃）。"""
        if table not in self.enabled_tables or not self.is_running():
            return
        table_enum = TABLE_TO_ENUM.get(table)
        if table_enum is None:
            return
        try:
            for action in iter_mirror_write_actions(self.db, kind, table, **kwargs):
                if action[0] == "delete":
                    _, where, params = action
                    self._send(
                        build_data_request(
                            SyncMessageType.DELETE_REQUEST,
                            table_enum,
                            {},
                            where=where,
                            params=params,
                        )
                    )
                else:
                    self._send(
                        build_data_request(
                            SyncMessageType.INSERT_REQUEST,
                            table_enum,
                            dict(action[1]),
                        )
                    )
        except Exception as e:
            self._log("error", f"Mirror local write {table}/{kind} error: {e}")

    def _close_socket(self) -> None:
        with self._socket_lock:
            sock = self._socket
            self._socket = None
        if sock:
            with suppress(OSError):
                sock.close()

    def _interruptible_sleep(self, seconds: int) -> None:
        end = time.time() + seconds
        while self._active and time.time() < end:
            time.sleep(min(1.0, end - time.time()))

    def _run_loop(self) -> None:
        """连接 → 监听；失败或断线后等待间隔再重连。"""
        while self._active:
            try:
                if self._connect_session():
                    self._listen_loop()
            except Exception as e:
                if self._active:
                    self._log("error", f"Session error: {e}")
            finally:
                self._close_socket()

            if not self._active:
                break
            self._log(
                "info",
                f"Disconnected; retry in {self.reconnect_interval}s "
                f"→ {self.server_ip}:{self.server_port}",
            )
            self._interruptible_sleep(self.reconnect_interval)

        self._log("info", "Sync client stopped")

    def _connect_session(self) -> bool:
        """建立连接、认证、全量同步。成功返回 True。"""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30.0)
            sock.connect((self.server_ip, self.server_port))
            with self._socket_lock:
                self._socket = sock
            sock = None  # ownership transferred

            if not self._authenticate():
                self._log("error", "Authentication failed")
                return False

            self._perform_full_sync()

            with self._socket_lock:
                if self._socket:
                    self._socket.settimeout(5.0)

            extras = []
            if self.enabled_tables:
                extras.append(f"syncing {len(self.enabled_tables)} table(s)")
            if self.qq_relay_host:
                extras.append("QQ relay via host")
            self._log(
                "info",
                f"Connected to {self.server_ip}:{self.server_port}"
                + (f"; {'; '.join(extras)}" if extras else ""),
            )
            return True
        except Exception as e:
            self._log("warning", f"Connect failed: {e}")
            return False
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    def _send(self, payload: bytes) -> None:
        with self._socket_lock:
            if not self._socket:
                raise ConnectionError("Sync client socket is closed")
            self._socket.sendall(payload)

    def _recv_message_unlocked(self, sock: socket.socket) -> Optional[tuple]:
        buffer = b""
        while len(buffer) < 5:
            chunk = sock.recv(4096)
            if not chunk:
                return None
            buffer += chunk
        msg_len = int.from_bytes(buffer[:4], "big")
        while len(buffer) < 5 + msg_len:
            chunk = sock.recv(4096)
            if not chunk:
                return None
            buffer += chunk
        return decode_message(buffer[: 5 + msg_len])

    def _request_response(self, payload: bytes) -> tuple:
        """在已连接会话内发送请求并同步等待响应（连接阶段单线程使用）。"""
        with self._socket_lock:
            if not self._socket:
                raise ConnectionError("Sync client socket is closed")
            self._socket.sendall(payload)
            result = self._recv_message_unlocked(self._socket)
        if result is None:
            raise ConnectionError("Sync server closed connection")
        return result

    def _authenticate(self) -> bool:
        payload = build_auth_request(
            self.server_id,
            self.server_name,
            self.auth_key,
            sorted(self.enabled_tables),
        )
        msg_type, data = self._request_response(payload)
        if msg_type != SyncMessageType.AUTH_RESPONSE:
            self._log("error", f"Unexpected auth response type: {msg_type}")
            return False
        if not data.get("success"):
            self._log("error", f"Authentication failed: {data.get('message', '')}")
            return False
        return True

    def _perform_full_sync(self) -> None:
        for table_name in sorted(self.enabled_tables):
            table_enum = TABLE_TO_ENUM.get(table_name)
            if table_enum is None:
                continue
            try:
                msg_type, data = self._request_response(build_full_sync_request(table_enum))
                if msg_type != SyncMessageType.FULL_SYNC_RESPONSE:
                    self._log("warning", f"Full sync {table_name}: unexpected response {msg_type}")
                    continue
                if not data.get("success"):
                    self._log("warning", f"Full sync {table_name} failed: {data.get('error', '')}")
                    continue
                rows = data.get("rows", [])
                applied = 0
                for row in rows:
                    if self._upsert_row(table_name, row):
                        applied += 1
                self._log("info", f"Full sync {table_name}: {applied}/{len(rows)} rows applied")
            except Exception as e:
                self._log("error", f"Full sync {table_name} error: {e}")

    def _upsert_row(self, table: str, row: Dict[str, Any]) -> bool:
        if not row:
            return False
        with self.db.suppress_write_notify():
            return self.db.upsert(table, row)

    def _apply_push_update(self, table_name: str, data: Dict[str, Any]) -> None:
        row_data = {k: v for k, v in data.items() if not k.startswith("_")}
        where = data.get("_where", "")
        params = tuple(data.get("_params", []))
        if where and row_data:
            self.db.update(table_name, row_data, where, params)
        elif row_data:
            self._upsert_row(table_name, row_data)

    def _apply_push_delete(self, table_name: str, data: Dict[str, Any]) -> None:
        where = data.get("_where", "")
        if where:
            self.db.delete(table_name, where, tuple(data.get("_params", [])))

    def _apply_push(self, table_enum: SyncTable, operation: str, data: Dict[str, Any]) -> None:
        table_name = ENUM_TO_TABLE.get(table_enum)
        if not table_name or table_name not in self.enabled_tables:
            return
        apply_fn = {
            "insert": lambda: self._upsert_row(table_name, data),
            "update": lambda: self._apply_push_update(table_name, data),
            "delete": lambda: self._apply_push_delete(table_name, data),
        }.get(operation)
        if not apply_fn:
            return
        try:
            with self.db.suppress_write_notify():
                apply_fn()
        except Exception as e:
            self._log("error", f"Apply push {table_name}/{operation} error: {e}")

    def _dispatch_listen_message(self, msg_type, data: Dict[str, Any], heartbeat_ts: float) -> float:
        """处理监听循环中的单条消息，返回可能更新后的 heartbeat 时间戳。"""
        if msg_type == SyncMessageType.PUSH_NOTIFY:
            self._apply_push(
                SyncTable(data.get("table", 0)),
                data.get("operation", ""),
                data.get("data", {}),
            )
        elif msg_type == SyncMessageType.QQ_CHAT_DOWNSTREAM:
            if self.on_qq_chat:
                try:
                    self.on_qq_chat(data)
                except Exception as e:
                    self._log("error", f"QQ chat downstream handler error: {e}")
        elif msg_type == SyncMessageType.HEARTBEAT:
            return time.time()
        return heartbeat_ts

    def _listen_loop(self) -> None:
        buffer = b""
        last_heartbeat = time.time()
        while self._active:
            with self._socket_lock:
                sock = self._socket
            if not sock:
                break
            try:
                if time.time() - last_heartbeat > 30:
                    try:
                        self._send(build_heartbeat())
                    except Exception:
                        break
                    last_heartbeat = time.time()

                sock.settimeout(5.0)
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk

                while len(buffer) >= 5:
                    msg_len = int.from_bytes(buffer[:4], "big")
                    if len(buffer) < 5 + msg_len:
                        break
                    raw_msg = buffer[: 5 + msg_len]
                    buffer = buffer[5 + msg_len :]
                    msg_type, data = decode_message(raw_msg)
                    last_heartbeat = self._dispatch_listen_message(
                        msg_type, data, last_heartbeat
                    )
            except socket.timeout:
                continue
            except Exception as e:
                if self._active:
                    self._log("error", f"Listen loop error: {e}")
                break

        self._log("info", "Sync client session ended")
