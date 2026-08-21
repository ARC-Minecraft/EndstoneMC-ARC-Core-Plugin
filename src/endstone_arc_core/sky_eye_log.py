# -*- coding: utf-8 -*-
"""天眼系统：独立 SQLite（plugins/ARCCore/sky_eye/skyeye.db）滚动存储，并清理旧的按日 txt。"""
import re
import sqlite3
import threading
from contextlib import suppress
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_file_lock = threading.Lock()
_last_txt_prune_date: Optional[date] = None
_date_filename_re = re.compile(r"^(\d{8})\.txt$")

ACTION_LABELS = {
    "PlayerJoin": "进服",
    "PlayerQuit": "离服",
    "BlockBreak": "破坏方块",
    "BlockPlace": "放置方块",
    "BlockInteract": "方块交互",
    "AirInteract": "空气交互",
    "ActorInteract": "实体交互",
    "ActorDamage": "攻击",
    "PlayerDeath": "死亡",
    "EconomyChange": "银行变动",
    "LandCreate": "创建领地",
    "LandDelete": "删除领地",
    "LandUpdate": "领地设置",
    "TeleportUse": "传送",
    "ShopTrade": "按钮商店",
    "ItemDrop": "丢弃物品",
    "ItemPickup": "拾取物品",
    "ItemHeldChange": "切换主手",
    "ItemConsume": "消耗物品",
    "AiAgent": "弧光天星",
    "AgentCommand": "天星指令",
    "PlayerTeleport": "玩家传送",
    "PlayerChat": "聊天",
    "PlayerCommand": "玩家指令",
    "ConsoleCommand": "控制台指令",
    "GameModeChange": "游戏模式",
}


def prune_sky_eye_logs(log_dir: Path, retention_days: int) -> None:
    """删除日期文件名早于「今天 − retention_days」的旧 txt（兼容升级前日志）。"""
    if retention_days <= 0 or not log_dir.is_dir():
        return
    boundary = date.today() - timedelta(days=retention_days)
    for path in log_dir.iterdir():
        if not path.is_file():
            continue
        match = _date_filename_re.match(path.name)
        if not match:
            continue
        try:
            file_date = datetime.strptime(match.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        if file_date <= boundary:
            with suppress(OSError):
                path.unlink()


def _clean_text(value: Any, fallback: str = "") -> str:
    text = str(value if value is not None else fallback)
    return text.replace("\t", " ").replace("\n", " ").strip()


def _parse_time_point(raw: str, *, end_of_day: bool = False) -> Optional[int]:
    text = str(raw or "").strip()
    if not text:
        return None
    now = datetime.now()
    candidates = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%H:%M:%S",
        "%H:%M",
    )
    for fmt in candidates:
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt in ("%H:%M:%S", "%H:%M"):
                parsed = parsed.replace(year=now.year, month=now.month, day=now.day)
            elif fmt == "%Y-%m-%d":
                if end_of_day:
                    parsed = parsed.replace(hour=23, minute=59, second=59)
            return int(parsed.timestamp())
        except ValueError:
            continue
    return None


class SkyEyeStore:
    """独立天眼 SQLite：写入事件、按保留天数滚动删除、提供查询。"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._last_prune_date: Optional[date] = None
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=3000")
        self._conn = conn
        return conn

    def _ensure_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sky_eye_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    ts_unix INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    player_name TEXT NOT NULL,
                    player_xuid TEXT NOT NULL,
                    dimension TEXT NOT NULL,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    z REAL NOT NULL,
                    hand TEXT,
                    detail TEXT,
                    in_land INTEGER NOT NULL DEFAULT 0,
                    land_id INTEGER,
                    land_name TEXT,
                    land_owner TEXT,
                    target_name TEXT,
                    target_xuid TEXT,
                    target_type TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sky_eye_player_time "
                "ON sky_eye_events(player_name, ts_unix)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sky_eye_xuid_time "
                "ON sky_eye_events(player_xuid, ts_unix)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sky_eye_action_time "
                "ON sky_eye_events(action, ts_unix)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sky_eye_target_time "
                "ON sky_eye_events(target_name, ts_unix)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sky_eye_dim_time "
                "ON sky_eye_events(dimension, ts_unix)"
            )
            conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                with suppress(sqlite3.Error):
                    self._conn.close()
                self._conn = None

    def prune(self, retention_days: int) -> None:
        """删除早于保留天数的 SQLite 行，并清理旧 txt。"""
        today = date.today()
        with self._lock:
            if retention_days > 0:
                cutoff = datetime.combine(
                    today - timedelta(days=retention_days), datetime.min.time()
                )
                cutoff_unix = int(cutoff.timestamp())
                conn = self._connect()
                conn.execute(
                    "DELETE FROM sky_eye_events WHERE ts_unix < ?", (cutoff_unix,)
                )
                conn.commit()
            self._last_prune_date = today
        prune_sky_eye_logs(self.db_path.parent, retention_days)

    def append(
        self,
        retention_days: int,
        action: str,
        player_name: str,
        player_xuid: str,
        dimension: str,
        pos_x: float,
        pos_y: float,
        pos_z: float,
        held_item: str = "",
        detail: str = "",
        in_land: bool = False,
        land_id: Optional[int] = None,
        land_name: str = "",
        land_owner: str = "",
        target_name: str = "",
        target_xuid: str = "",
        target_type: str = "",
    ) -> None:
        now = datetime.now()
        today = now.date()
        row = (
            now.strftime("%Y-%m-%d %H:%M:%S"),
            int(now.timestamp()),
            _clean_text(action, "Unknown"),
            _clean_text(player_name, "?"),
            _clean_text(player_xuid),
            _clean_text(dimension, "-"),
            float(pos_x),
            float(pos_y),
            float(pos_z),
            _clean_text(held_item, "-") or "-",
            _clean_text(detail),
            1 if in_land else 0,
            int(land_id) if land_id is not None else None,
            _clean_text(land_name),
            _clean_text(land_owner),
            _clean_text(target_name),
            _clean_text(target_xuid),
            _clean_text(target_type),
        )
        with self._lock:
            if self._last_prune_date != today:
                self._last_prune_date = today
                should_prune = True
            else:
                should_prune = False
            conn = self._connect()
            conn.execute(
                """
                INSERT INTO sky_eye_events (
                    ts, ts_unix, action, player_name, player_xuid, dimension,
                    x, y, z, hand, detail, in_land, land_id, land_name, land_owner,
                    target_name, target_xuid, target_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            conn.commit()
        if should_prune:
            self.prune(retention_days)

    def query(
        self,
        *,
        player_name: str = "",
        player_xuid: str = "",
        target_name: str = "",
        action: str = "",
        combat_role: str = "",
        minutes: Optional[int] = None,
        time_from: str = "",
        time_to: str = "",
        dimension: str = "",
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        radius: Optional[float] = None,
        in_land: Optional[bool] = None,
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        now_unix = int(datetime.now().timestamp())
        start_unix = _parse_time_point(time_from)
        end_unix = _parse_time_point(time_to, end_of_day=True)
        if start_unix is None and end_unix is None:
            window = 30 if minutes is None else max(1, int(minutes))
            start_unix = now_unix - window * 60
            end_unix = now_unix
        elif start_unix is None:
            start_unix = now_unix - 24 * 3600
        elif end_unix is None:
            end_unix = now_unix
        clauses.append("ts_unix >= ? AND ts_unix <= ?")
        params.extend([start_unix, end_unix])

        name = _clean_text(player_name)
        xuid = _clean_text(player_xuid)
        tname = _clean_text(target_name)
        role = _clean_text(combat_role).lower()
        if role in ("hit", "attacker", "打了谁"):
            if xuid:
                clauses.append("player_xuid = ?")
                params.append(xuid)
            elif name:
                clauses.append("player_name = ? COLLATE NOCASE")
                params.append(name)
            clauses.append("action = 'ActorDamage'")
        elif role in ("hurt", "victim", "被谁打"):
            if xuid:
                clauses.append("target_xuid = ?")
                params.append(xuid)
            elif name:
                clauses.append("target_name = ? COLLATE NOCASE")
                params.append(name)
            clauses.append("action IN ('ActorDamage', 'PlayerDeath')")
        elif role in ("both", "combat", "all"):
            person_bits: List[str] = []
            if xuid:
                person_bits.append("player_xuid = ?")
                params.append(xuid)
                person_bits.append("target_xuid = ?")
                params.append(xuid)
            if name:
                person_bits.append("player_name = ? COLLATE NOCASE")
                params.append(name)
                person_bits.append("target_name = ? COLLATE NOCASE")
                params.append(name)
            if person_bits:
                clauses.append("(" + " OR ".join(person_bits) + ")")
            clauses.append("action IN ('ActorDamage', 'PlayerDeath')")
        else:
            # 查玩家时同时匹配「本人操作」与「天星代其执行」（target_name=请求者）
            person_bits: List[str] = []
            if xuid:
                person_bits.append("player_xuid = ?")
                params.append(xuid)
                person_bits.append("target_xuid = ?")
                params.append(xuid)
            if name:
                person_bits.append("player_name = ? COLLATE NOCASE")
                params.append(name)
                person_bits.append("target_name = ? COLLATE NOCASE")
                params.append(name)
            if person_bits:
                clauses.append("(" + " OR ".join(person_bits) + ")")
            if tname:
                clauses.append("target_name = ? COLLATE NOCASE")
                params.append(tname)

        act = _clean_text(action)
        if act:
            clauses.append("action = ?")
            params.append(act)
        dim = _clean_text(dimension)
        if dim:
            clauses.append("dimension = ?")
            params.append(dim)
        if in_land is not None:
            clauses.append("in_land = ?")
            params.append(1 if in_land else 0)
        if (
            x is not None
            and y is not None
            and z is not None
            and radius is not None
            and float(radius) >= 0
        ):
            r2 = float(radius) * float(radius)
            clauses.append(
                "((x - ?) * (x - ?) + (y - ?) * (y - ?) + (z - ?) * (z - ?)) <= ?"
            )
            params.extend(
                [float(x), float(x), float(y), float(y), float(z), float(z), r2]
            )

        cap = max(1, min(int(limit or 40), 80))
        sql = (
            "SELECT * FROM sky_eye_events WHERE "
            + " AND ".join(clauses)
            + " ORDER BY ts_unix DESC, id DESC LIMIT ?"
        )
        params.append(cap)
        with self._lock:
            conn = self._connect()
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]


def format_sky_eye_records(records: Sequence[Dict[str, Any]], heading: str = "") -> str:
    if not records:
        return "天眼没有找到匹配记录。"
    lines = []
    if heading:
        lines.append(heading)
    lines.append(f"共 {len(records)} 条（新→旧）:")
    for item in records:
        action = ACTION_LABELS.get(str(item.get("action") or ""), str(item.get("action") or "?"))
        ts = item.get("ts") or "?"
        name = item.get("player_name") or "?"
        dim = item.get("dimension") or "-"
        try:
            pos = f"{float(item.get('x')):.1f},{float(item.get('y')):.1f},{float(item.get('z')):.1f}"
        except (TypeError, ValueError):
            pos = "?,?,?"
        land_bit = "荒野"
        if int(item.get("in_land") or 0):
            land_name = item.get("land_name") or f"#{item.get('land_id')}"
            owner = item.get("land_owner") or "?"
            land_bit = f"领地内 {land_name}（主人 {owner}）"
        hand = item.get("hand") or "-"
        detail = item.get("detail") or ""
        target = item.get("target_name") or ""
        extra = []
        if target:
            extra.append(f"对象:{target}")
        if detail:
            extra.append(detail)
        if hand and hand not in ("-", "empty"):
            extra.append(f"主手:{hand}")
        extra_text = ("  " + "  ".join(extra)) if extra else ""
        lines.append(f"• {ts}  {name}  {action}  {dim} ({pos})  {land_bit}{extra_text}")
    return "\n".join(lines)
