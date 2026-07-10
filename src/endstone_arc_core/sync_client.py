# -*- coding: utf-8 -*-
"""跨服数据同步客户端：连接同步中心并拉取/接收推送"""
import socket
import threading
import time
from typing import Any, Dict, List, Optional, Set

from endstone_arc_core.sync_config import get_client_sync_tables
from endstone_arc_core.sync_protocol import (
    SyncMessageType,
    SyncTable,
    TABLE_TO_ENUM,
    ENUM_TO_TABLE,
    build_auth_request,
    build_full_sync_request,
    build_heartbeat,
    decode_message,
)


class SyncClient:
    """连接远程同步中心，按配置分项同步数据到本地数据库。"""

    def __init__(self, database_manager, setting_manager, logger=None):
        self.db = database_manager
        self.settings = setting_manager
        self.logger = logger

        self.server_ip = str(setting_manager.GetSetting("SYNC_SERVER_IP") or "127.0.0.1").strip()
        self.server_id = str(setting_manager.GetSetting("SYNC_CLIENT_SERVER_ID") or "server_001").strip()
        self.server_name = str(
            setting_manager.GetSetting("SYNC_CLIENT_SERVER_NAME") or "服务器01"
        ).strip()
        self.auth_key = str(setting_manager.GetSetting("SYNC_CLIENT_AUTH_KEY") or "").strip()

        port_raw = setting_manager.GetSetting("SYNC_CLIENT_PORT")
        if port_raw is None or not str(port_raw).strip():
            port_raw = setting_manager.GetSetting("SYNC_SERVER_PORT")
        try:
            self.server_port = int(port_raw) if port_raw else 19999
        except (ValueError, TypeError):
            self.server_port = 19999

        self.enabled_tables: Set[str] = get_client_sync_tables(setting_manager)

        self._socket: Optional[socket.socket] = None
        self._running = False
        self._listener_thread: Optional[threading.Thread] = None
        self._socket_lock = threading.Lock()

    def _log(self, level: str, message: str) -> None:
        if self.logger:
            getattr(self.logger, level.lower(), self.logger.info)(f"[ARC SyncClient] {message}")
        else:
            print(f"[{level.upper()}] [ARC SyncClient] {message}")

    def start(self) -> bool:
        if self._running:
            return True
        if not self.enabled_tables:
            self._log(
                "warning",
                "No sync categories enabled (SYNC_CLIENT_SYNC_* all False); client not started",
            )
            return False

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30.0)
            sock.connect((self.server_ip, self.server_port))
            self._socket = sock
            self._running = True

            if not self._authenticate():
                self.stop()
                return False

            self._perform_full_sync()

            sock.settimeout(30.0)
            self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._listener_thread.start()

            self._log(
                "info",
                f"Connected to {self.server_ip}:{self.server_port}; "
                f"syncing {len(self.enabled_tables)} table(s)",
            )
            return True
        except Exception as e:
            self._log("error", f"Failed to start sync client: {e}")
            self.stop()
            return False

    def stop(self) -> None:
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=5)
        self._listener_thread = None

    def is_running(self) -> bool:
        return self._running and self._socket is not None

    def _send(self, payload: bytes) -> None:
        with self._socket_lock:
            if not self._socket:
                raise ConnectionError("Sync client socket is closed")
            self._socket.sendall(payload)

    def _recv_message(self) -> Optional[tuple]:
        if not self._socket:
            return None
        buffer = b""
        while len(buffer) < 5:
            chunk = self._socket.recv(4096)
            if not chunk:
                return None
            buffer += chunk
        msg_len = int.from_bytes(buffer[:4], "big")
        while len(buffer) < 5 + msg_len:
            chunk = self._socket.recv(4096)
            if not chunk:
                return None
            buffer += chunk
        return decode_message(buffer[: 5 + msg_len])

    def _request_response(self, payload: bytes) -> tuple:
        with self._socket_lock:
            self._socket.sendall(payload)
            result = self._recv_message()
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
        cols = list(row.keys())
        placeholders = ",".join(["?"] * len(cols))
        sql = f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
        return self.db.execute(sql, tuple(row.values()))

    def _apply_push(self, table_enum: SyncTable, operation: str, data: Dict[str, Any]) -> None:
        table_name = ENUM_TO_TABLE.get(table_enum)
        if not table_name or table_name not in self.enabled_tables:
            return
        try:
            if operation == "insert":
                self._upsert_row(table_name, data)
            elif operation == "update":
                row_data = {k: v for k, v in data.items() if not k.startswith("_")}
                where = data.get("_where", "")
                params = tuple(data.get("_params", []))
                if where and row_data:
                    self.db.update(table_name, row_data, where, params)
            elif operation == "delete":
                where = data.get("_where", "")
                params = tuple(data.get("_params", []))
                if where:
                    self.db.delete(table_name, where, params)
        except Exception as e:
            self._log("error", f"Apply push {table_name}/{operation} error: {e}")

    def _listen_loop(self) -> None:
        buffer = b""
        last_heartbeat = time.time()
        while self._running and self._socket:
            try:
                if time.time() - last_heartbeat > 30:
                    try:
                        self._send(build_heartbeat())
                    except Exception:
                        break
                    last_heartbeat = time.time()

                self._socket.settimeout(5.0)
                chunk = self._socket.recv(4096)
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

                    if msg_type == SyncMessageType.PUSH_NOTIFY:
                        table_enum = SyncTable(data.get("table", 0))
                        self._apply_push(table_enum, data.get("operation", ""), data.get("data", {}))
                    elif msg_type == SyncMessageType.HEARTBEAT:
                        last_heartbeat = time.time()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    self._log("error", f"Listen loop error: {e}")
                break

        self._running = False
        self._log("info", "Sync client disconnected from server")
