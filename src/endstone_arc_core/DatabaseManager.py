import re
import sqlite3
from typing import Any, List, Dict, Optional
import threading
from pathlib import Path


class DatabaseManager:
    def __init__(self, db_path: str):
        """
        初始化数据库管理器
        :param db_path: 默认数据库文件路径
        """
        self.db_path = db_path
        self._local = threading.local()  # 线程本地存储

        # 表路由：table_name -> db_path。未注册的表使用默认 db_path。
        self._table_routes: Dict[str, str] = {}

        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """确保默认数据库文件存在"""
        db_file = Path(self.db_path)
        if not db_file.parent.exists():
            db_file.parent.mkdir(parents=True)

    def add_route(self, table_name: str, db_path: str) -> None:
        """
        为指定表注册路由到另一个数据库。
        :param table_name: 表名
        :param db_path: 目标数据库路径
        """
        db_path_str = str(db_path)
        self._table_routes[table_name.lower()] = db_path_str
        # 确保目标数据库目录存在
        db_file = Path(db_path_str)
        if not db_file.parent.exists():
            db_file.parent.mkdir(parents=True)

    def _get_connection(self, db_path: str) -> sqlite3.Connection:
        """获取指定路径的数据库连接（线程本地，每个线程每个路径独立连接）"""
        if not hasattr(self._local, 'connections'):
            self._local.connections: Dict[str, sqlite3.Connection] = {}
        conns = self._local.connections
        conn = conns.get(db_path)
        if conn is not None:
            return conn
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conns[db_path] = conn
        return conn

    def _resolve_connection(self, sql: str) -> sqlite3.Connection:
        """根据 SQL 语句解析表名，返回对应数据库的连接"""
        table_name = self._extract_table_name(sql)
        if table_name and table_name in self._table_routes:
            target_path = self._table_routes[table_name]
            return self._get_connection(target_path)
        return self._get_connection(self.db_path)

    @staticmethod
    def _extract_table_name(sql: str) -> Optional[str]:
        """从 SQL 语句中提取主表名"""
        s = sql.strip()
        # INSERT OR REPLACE INTO / INSERT INTO
        m = re.search(r'\bINSERT\s+(?:OR\s+\w+\s+)?INTO\s+[`"\[]?(\w+)', s, re.IGNORECASE)
        if m:
            return m.group(1).lower()
        # UPDATE
        m = re.search(r'\bUPDATE\s+[`"\[]?(\w+)', s, re.IGNORECASE)
        if m:
            return m.group(1).lower()
        # DELETE FROM
        m = re.search(r'\bDELETE\s+FROM\s+[`"\[]?(\w+)', s, re.IGNORECASE)
        if m:
            return m.group(1).lower()
        # SELECT ... FROM / JOIN / FROM
        m = re.search(r'\bFROM\s+[`"\[]?(\w+)', s, re.IGNORECASE)
        if m:
            return m.group(1).lower()
        return None

    # ---- 旧的线程本地连接（兼容未路由的调用） ----

    @property
    def connection(self) -> sqlite3.Connection:
        """获取当前线程的默认数据库连接（兼容旧代码）"""
        if not hasattr(self._local, 'default_connection'):
            self._local.default_connection = self._get_connection(self.db_path)
        return self._local.default_connection

    def close(self):
        """关闭当前线程的所有数据库连接"""
        if hasattr(self._local, 'connections'):
            for conn in self._local.connections.values():
                try:
                    conn.close()
                except Exception:
                    pass
            self._local.connections.clear()
        if hasattr(self._local, 'default_connection'):
            self._local.default_connection.close()
            delattr(self._local, 'default_connection')

    def execute(self, sql: str, params: tuple = ()) -> bool:
        """
        执行SQL语句
        :param sql: SQL语句
        :param params: SQL参数
        :return: 是否执行成功
        """
        try:
            conn = self._resolve_connection(sql)
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            return True
        except Exception as e:
            print(f"Execute SQL error: {str(e)}")
            try:
                self._resolve_connection(sql).rollback()
            except Exception:
                pass
            return False

    def execute_and_get_rowcount(self, sql: str, params: tuple = ()) -> int:
        """
        执行 SQL 并返回 cursor.rowcount（常用于 INSERT OR IGNORE 判断是否实际插入一行）。
        失败时返回 -1。
        """
        try:
            conn = self._resolve_connection(sql)
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            rowcount = cursor.rowcount
            if rowcount is None:
                return 0
            return int(rowcount)
        except Exception as e:
            print(f"Execute SQL error: {str(e)}")
            try:
                self._resolve_connection(sql).rollback()
            except Exception:
                pass
            return -1

    def query_one(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """
        查询单条记录
        :param sql: SQL语句
        :param params: SQL参数
        :return: 查询结果字典或None
        """
        try:
            conn = self._resolve_connection(sql)
            cursor = conn.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            print(f"Query one error: {str(e)}")
            return None

    def query_all(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """
        查询多条记录
        :param sql: SQL语句
        :param params: SQL参数
        :return: 查询结果列表
        """
        try:
            conn = self._resolve_connection(sql)
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"Query all error: {str(e)}")
            return []

    def insert(self, table: str, data: Dict[str, Any]) -> bool:
        """
        插入数据
        :param table: 表名
        :param data: 要插入的数据字典
        :return: 是否插入成功
        """
        fields = ','.join(data.keys())
        placeholders = ','.join(['?' for _ in data])
        sql = f"INSERT INTO {table} ({fields}) VALUES ({placeholders})"
        try:
            conn = self._resolve_connection(sql)
            cursor = conn.cursor()
            cursor.execute(sql, tuple(data.values()))
            conn.commit()
            return True
        except Exception as e:
            print(f"Execute SQL error: {str(e)}")
            try:
                self._resolve_connection(sql).rollback()
            except Exception:
                pass
            return False

    def update(self, table: str, data: Dict[str, Any], where: str, params: tuple = ()) -> bool:
        """
        更新数据
        :param table: 表名
        :param data: 要更新的数据字典
        :param where: WHERE子句
        :param params: WHERE子句的参数
        :return: 是否更新成功
        """
        set_clause = ','.join([f"{k}=?" for k in data.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
        return self.execute(sql, tuple(data.values()) + params)

    def delete(self, table: str, where: str, params: tuple = ()) -> bool:
        """
        删除数据
        :param table: 表名
        :param where: WHERE子句
        :param params: WHERE子句的参数
        :return: 是否删除成功
        """
        sql = f"DELETE FROM {table} WHERE {where}"
        return self.execute(sql, params)

    def create_table(self, table: str, fields: Dict[str, str]) -> bool:
        """
        创建表
        :param table: 表名
        :param fields: 字段定义字典，key为字段名，value为字段类型定义
        :return: 是否创建成功
        """
        field_defs = ','.join([f"{k} {v}" for k, v in fields.items()])
        sql = f"CREATE TABLE IF NOT EXISTS {table} ({field_defs})"
        return self.execute(sql)

    def table_exists(self, table: str) -> bool:
        """
        检查表是否存在
        :param table: 表名
        :return: 表是否存在
        """
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        return self.query_one(sql, (table,)) is not None
