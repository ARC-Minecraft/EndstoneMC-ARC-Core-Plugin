# -*- coding: utf-8 -*-
"""天眼系统：独立 SQLite（plugins/ARCCore/sky_eye/skyeye.db）滚动存储，并清理旧的按日 txt。"""
import re
import sqlite3
import threading
from contextlib import suppress
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_file_lock = threading.Lock()
_last_txt_prune_date: Optional[date] = None
_date_filename_re = re.compile(r"^(\d{8})\.txt$")

_INSERT_SQL = """
INSERT INTO sky_eye_events (
    ts, ts_unix, action, player_name, player_xuid, dimension,
    x, y, z, hand, detail, in_land, land_id, land_name, land_owner,
    target_name, target_xuid, target_type
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

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

# 事件类型别名 → (canonical actions, 额外 SQL 条件)
# 额外条件用于细分 PvP / PvE 等（依赖写入时的 target_type）
_EVENT_KIND_FILTERS: Dict[str, Tuple[List[str], str]] = {
    "death": (["PlayerDeath"], ""),
    "pvp": (
        ["ActorDamage", "PlayerDeath"],
        "lower(ifnull(target_type,'')) = 'player'",
    ),
    "pvp_death": (
        ["PlayerDeath"],
        "lower(ifnull(target_type,'')) = 'player'",
    ),
    "pvp_hit": (
        ["ActorDamage"],
        "lower(ifnull(target_type,'')) = 'player'",
    ),
    "pve": (
        ["ActorDamage"],
        "ifnull(target_type,'') != '' AND lower(target_type) != 'player'",
    ),
    "pve_death": (
        ["PlayerDeath"],
        "ifnull(target_type,'') = '' OR lower(target_type) != 'player'",
    ),
    "kill": (["ActorDamage"], ""),
    "combat": (["ActorDamage", "PlayerDeath"], ""),
    "join": (["PlayerJoin"], ""),
    "quit": (["PlayerQuit"], ""),
    "break": (["BlockBreak"], ""),
    "place": (["BlockPlace"], ""),
    "chat": (["PlayerChat"], ""),
    "command": (["PlayerCommand", "ConsoleCommand", "AgentCommand"], ""),
    "teleport": (["TeleportUse", "PlayerTeleport"], ""),
    "economy": (["EconomyChange"], ""),
    "land": (["LandCreate", "LandDelete", "LandUpdate"], ""),
    "shop": (["ShopTrade"], ""),
    "item": (["ItemDrop", "ItemPickup", "ItemHeldChange", "ItemConsume"], ""),
}

_EVENT_KIND_ALIASES: Dict[str, str] = {
    "death": "death",
    "die": "death",
    "died": "death",
    "死亡": "death",
    "死了": "death",
    "谁死了": "death",
    "playerdeath": "death",
    "pvp": "pvp",
    "pk": "pvp",
    "打架": "pvp",
    "互砍": "pvp",
    "玩家击杀": "pvp",
    "击杀玩家": "pvp",
    "pvp_death": "pvp_death",
    "pvpdeath": "pvp_death",
    "pvp死亡": "pvp_death",
    "被玩家杀死": "pvp_death",
    "pvp_hit": "pvp_hit",
    "pvphit": "pvp_hit",
    "pvp伤害": "pvp_hit",
    "pve": "pve",
    "打怪": "pve",
    "击杀生物": "pve",
    "杀怪": "pve",
    "mob": "pve",
    "mob_kill": "pve",
    "pve_death": "pve_death",
    "pvedeath": "pve_death",
    "被怪杀死": "pve_death",
    "环境死亡": "pve_death",
    "kill": "kill",
    "攻击": "kill",
    "伤害": "kill",
    "actordamage": "kill",
    "combat": "combat",
    "战斗": "combat",
    "打架记录": "combat",
    "join": "join",
    "进服": "join",
    "上线": "join",
    "playerjoin": "join",
    "quit": "quit",
    "离服": "quit",
    "下线": "quit",
    "playerquit": "quit",
    "break": "break",
    "破坏": "break",
    "挖方块": "break",
    "blockbreak": "break",
    "place": "place",
    "放置": "place",
    "放方块": "place",
    "blockplace": "place",
    "chat": "chat",
    "聊天": "chat",
    "说话": "chat",
    "playerchat": "chat",
    "command": "command",
    "指令": "command",
    "命令": "command",
    "teleport": "teleport",
    "传送": "teleport",
    "tp": "teleport",
    "economy": "economy",
    "银行": "economy",
    "经济": "economy",
    "land": "land",
    "领地": "land",
    "shop": "shop",
    "商店": "shop",
    "item": "item",
    "物品": "item",
}

# 精确 action 名（大小写不敏感）→ 自身
_CANONICAL_ACTIONS = {k.lower(): k for k in ACTION_LABELS.keys()}


def _escape_like(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def resolve_event_kind(action: str) -> Tuple[Optional[List[str]], str, str]:
    """把用户/模型传入的 action 解析为 (actions, extra_sql, kind_label)。

    支持：精确动作名（PlayerDeath）、类别别名（death/pvp/死亡）、逗号分隔多值。
    返回 actions=None 表示不过滤动作；extra_sql 非空时需 AND 上该条件。
    """
    raw = _clean_text(action)
    if not raw:
        return None, "", ""
    parts = [p.strip() for p in re.split(r"[,;/|，、\s]+", raw) if p.strip()]
    if not parts:
        return None, "", ""
    actions: List[str] = []
    extras: List[str] = []
    labels: List[str] = []
    for part in parts:
        key = part.lower().replace(" ", "").replace("-", "_")
        # 精确 canonical
        if key in _CANONICAL_ACTIONS:
            act = _CANONICAL_ACTIONS[key]
            if act not in actions:
                actions.append(act)
            labels.append(ACTION_LABELS.get(act, act))
            continue
        kind = _EVENT_KIND_ALIASES.get(key) or _EVENT_KIND_ALIASES.get(part)
        if kind and kind in _EVENT_KIND_FILTERS:
            kind_actions, extra = _EVENT_KIND_FILTERS[kind]
            for act in kind_actions:
                if act not in actions:
                    actions.append(act)
            if extra and extra not in extras:
                extras.append(extra)
            labels.append(kind)
            continue
        # 未识别：当作精确 action 字符串（兼容旧调用）
        if part not in actions:
            actions.append(part)
        labels.append(part)
    extra_sql = " AND ".join(f"({e})" for e in extras) if extras else ""
    return actions or None, extra_sql, "+".join(labels)


def _person_name_clause(
    column: str,
    name: str,
    *,
    fuzzy: bool,
    params: List[Any],
) -> str:
    if fuzzy:
        params.append(f"%{_escape_like(name)}%")
        return f"{column} LIKE ? ESCAPE '\\' COLLATE NOCASE"
    params.append(name)
    return f"{column} = ? COLLATE NOCASE"


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

    _FLUSH_BATCH = 64
    _FLUSH_INTERVAL = 0.5

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._last_prune_date: Optional[date] = None
        self._pending: List[Tuple[Any, ...]] = []
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._ensure_schema()
        self._writer = threading.Thread(
            target=self._writer_loop, name="ARCCore-SkyEyeWriter", daemon=True
        )
        self._writer.start()

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

    def _writer_loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self._FLUSH_INTERVAL)
            self._wake.clear()
            try:
                self.flush()
            except Exception:
                pass
        try:
            self.flush()
        except Exception:
            pass

    def flush(self) -> None:
        """将内存队列中的事件批量写入 SQLite。可在后台线程调用。"""
        with self._lock:
            if not self._pending:
                return
            rows = self._pending
            self._pending = []
            conn = self._connect()
            conn.executemany(_INSERT_SQL, rows)
            conn.commit()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        writer = getattr(self, "_writer", None)
        if writer is not None and writer.is_alive() and threading.current_thread() is not writer:
            writer.join(timeout=3)
        with self._lock:
            try:
                if self._pending:
                    conn = self._connect()
                    conn.executemany(_INSERT_SQL, self._pending)
                    conn.commit()
                    self._pending = []
            except Exception:
                pass
            if self._conn is not None:
                with suppress(sqlite3.Error):
                    self._conn.close()
                self._conn = None

    def maybe_prune(self, retention_days: int) -> None:
        """若尚未在今天执行过清理，则滚动删除旧事件。"""
        today = date.today()
        with self._lock:
            if self._last_prune_date == today:
                return
        self.flush()
        self.prune(retention_days)

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
        _ = retention_days  # 保留参数以兼容调用方；滚动清理改由定时任务触发
        now = datetime.now()
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
        should_flush = False
        with self._lock:
            self._pending.append(row)
            if len(self._pending) >= self._FLUSH_BATCH:
                should_flush = True
        if should_flush:
            self._wake.set()

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
        name_fuzzy: bool = True,
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        self.flush()
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
        fuzzy = bool(name_fuzzy)
        role = _clean_text(combat_role).lower()
        resolved_actions, action_extra, _ = resolve_event_kind(action)

        if role in ("hit", "attacker", "打了谁"):
            if xuid:
                clauses.append("player_xuid = ?")
                params.append(xuid)
            elif name:
                clauses.append(
                    _person_name_clause("player_name", name, fuzzy=fuzzy, params=params)
                )
            if resolved_actions:
                placeholders = ",".join("?" for _ in resolved_actions)
                clauses.append(f"action IN ({placeholders})")
                params.extend(resolved_actions)
            else:
                clauses.append("action = 'ActorDamage'")
            if action_extra:
                clauses.append(action_extra)
        elif role in ("hurt", "victim", "被谁打"):
            if xuid:
                clauses.append("target_xuid = ?")
                params.append(xuid)
            elif name:
                clauses.append(
                    _person_name_clause("target_name", name, fuzzy=fuzzy, params=params)
                )
            if resolved_actions:
                placeholders = ",".join("?" for _ in resolved_actions)
                clauses.append(f"action IN ({placeholders})")
                params.extend(resolved_actions)
            else:
                clauses.append("action IN ('ActorDamage', 'PlayerDeath')")
            if action_extra:
                clauses.append(action_extra)
        elif role in ("both", "combat", "all"):
            person_bits: List[str] = []
            if xuid:
                person_bits.append("player_xuid = ?")
                params.append(xuid)
                person_bits.append("target_xuid = ?")
                params.append(xuid)
            if name:
                person_bits.append(
                    _person_name_clause("player_name", name, fuzzy=fuzzy, params=params)
                )
                person_bits.append(
                    _person_name_clause("target_name", name, fuzzy=fuzzy, params=params)
                )
            if person_bits:
                clauses.append("(" + " OR ".join(person_bits) + ")")
            if resolved_actions:
                placeholders = ",".join("?" for _ in resolved_actions)
                clauses.append(f"action IN ({placeholders})")
                params.extend(resolved_actions)
            else:
                clauses.append("action IN ('ActorDamage', 'PlayerDeath')")
            if action_extra:
                clauses.append(action_extra)
        else:
            # 查玩家时同时匹配「本人操作」与「天星代其执行」（target_name=请求者）
            person_bits: List[str] = []
            if xuid:
                person_bits.append("player_xuid = ?")
                params.append(xuid)
                person_bits.append("target_xuid = ?")
                params.append(xuid)
            if name:
                person_bits.append(
                    _person_name_clause("player_name", name, fuzzy=fuzzy, params=params)
                )
                person_bits.append(
                    _person_name_clause("target_name", name, fuzzy=fuzzy, params=params)
                )
            if person_bits:
                clauses.append("(" + " OR ".join(person_bits) + ")")
            if tname:
                clauses.append(
                    _person_name_clause(
                        "target_name", tname, fuzzy=fuzzy, params=params
                    )
                )
            if resolved_actions:
                placeholders = ",".join("?" for _ in resolved_actions)
                clauses.append(f"action IN ({placeholders})")
                params.extend(resolved_actions)
            if action_extra:
                clauses.append(action_extra)

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

    def distinct_player_names(
        self,
        *,
        hint: str,
        minutes: Optional[int] = 24 * 60,
        limit: int = 20,
    ) -> List[str]:
        """按模糊名从近期天眼里列出匹配过的玩家名（去重）。"""
        name = _clean_text(hint)
        if not name:
            return []
        self.flush()
        window = 24 * 60 if minutes is None else max(1, int(minutes))
        now_unix = int(datetime.now().timestamp())
        start_unix = now_unix - window * 60
        pattern = f"%{_escape_like(name)}%"
        cap = max(1, min(int(limit or 20), 40))
        sql = """
            SELECT name, MAX(ts_unix) AS last_ts FROM (
                SELECT player_name AS name, ts_unix FROM sky_eye_events
                WHERE ts_unix >= ? AND player_name LIKE ? ESCAPE '\\' COLLATE NOCASE
                UNION ALL
                SELECT target_name AS name, ts_unix FROM sky_eye_events
                WHERE ts_unix >= ? AND target_name LIKE ? ESCAPE '\\' COLLATE NOCASE
                  AND ifnull(target_name,'') != ''
            )
            GROUP BY name
            ORDER BY last_ts DESC
            LIMIT ?
        """
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                sql, (start_unix, pattern, start_unix, pattern, cap)
            ).fetchall()
        return [str(r[0]) for r in rows if r and r[0]]


def format_sky_eye_records(
    records: Sequence[Dict[str, Any]],
    heading: str = "",
    *,
    name_hint: str = "",
) -> str:
    if not records:
        hint = _clean_text(name_hint)
        if hint:
            return f"天眼没有找到与「{hint}」匹配的记录。"
        return "天眼没有找到匹配记录。"
    lines = []
    if heading:
        lines.append(heading)
    if name_hint:
        matched: List[str] = []
        seen = set()
        for item in records:
            for key in ("player_name", "target_name"):
                n = str(item.get(key) or "").strip()
                if not n or n in seen:
                    continue
                if name_hint.lower() in n.lower() or n.lower() in name_hint.lower():
                    seen.add(n)
                    matched.append(n)
        if matched:
            lines.append("模糊匹配到玩家: " + "、".join(matched[:12]))
    # 全服按类型查询时，附带涉及玩家摘要（便于「谁死了」）
    if not name_hint:
        actors: List[str] = []
        seen_a = set()
        for item in records:
            act = str(item.get("action") or "")
            n = str(item.get("player_name") or "").strip()
            if act == "PlayerDeath" and n and n not in seen_a:
                seen_a.add(n)
                actors.append(n)
        if actors:
            lines.append("涉及玩家: " + "、".join(actors[:20]))
    lines.append(f"共 {len(records)} 条（新→旧）:")
    for item in records:
        action = ACTION_LABELS.get(str(item.get("action") or ""), str(item.get("action") or "?"))
        # PvP 细分展示
        ttype = str(item.get("target_type") or "").strip().lower()
        if str(item.get("action") or "") == "ActorDamage" and ttype == "player":
            action = "PvP攻击"
        elif str(item.get("action") or "") == "PlayerDeath" and ttype == "player":
            action = "PvP死亡"
        elif str(item.get("action") or "") == "ActorDamage" and ttype and ttype != "player":
            action = "攻击生物"
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
            if ttype == "player":
                extra.append(f"对象玩家:{target}")
            elif ttype:
                extra.append(f"对象:{target}({ttype})")
            else:
                extra.append(f"对象:{target}")
        if detail:
            extra.append(detail)
        if hand and hand not in ("-", "empty"):
            extra.append(f"主手:{hand}")
        extra_text = ("  " + "  ".join(extra)) if extra else ""
        lines.append(f"• {ts}  {name}  {action}  {dim} ({pos})  {land_bit}{extra_text}")
    return "\n".join(lines)
