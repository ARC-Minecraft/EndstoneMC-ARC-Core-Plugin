# -*- coding: utf-8 -*-
"""头衔系统：稀有度、介绍；玩家解锁/佩戴，聊天展示。

头衔完整标识为 (title, rarity)，支持同名不同稀有度并存。
"""
import json
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

from endstone import Player


# 稀有度 -> MC 颜色码（§0-§f）
RARITY_COLORS = {
    "普通": "§h",
    "稀有": "§9",
    "史诗": "§u",
    "传奇": "§6",
    "神话": "§c",
}
DEFAULT_RARITY = "普通"

# 稀有度比较顺序（数值越大越高）
RARITY_ORDER = {
    "普通": 0,
    "稀有": 1,
    "史诗": 2,
    "传奇": 3,
    "神话": 4,
}


def normalize_rarity(rarity: Any) -> str:
    r = str(rarity or "").strip()
    if r == "传说":
        return "传奇"
    if r in RARITY_ORDER:
        return r
    return DEFAULT_RARITY


class TitleSystem:
    """头衔系统：头衔定义（名称+稀有度）、解锁时间、佩戴与聊天展示。"""

    def __init__(self, database_manager, setting_manager):
        self.database_manager = database_manager
        self.setting_manager = setting_manager
        self._table_def = "title_definitions"
        self._table_unlock_time = "player_title_unlock_time"
        self._table_equipped = "player_title_equipped"

    def _create_title_tables(self) -> None:
        """CREATE IF NOT EXISTS 三张头衔表（走表路由，落在正确库文件）。"""
        self.database_manager.execute(
            "CREATE TABLE IF NOT EXISTS title_definitions ("
            "title TEXT NOT NULL, "
            "rarity TEXT NOT NULL DEFAULT '普通', "
            "description TEXT, "
            "reward_money REAL DEFAULT 0, "
            "reward_items TEXT DEFAULT '[]', "
            "PRIMARY KEY (title, rarity)"
            ")"
        )
        self.database_manager.execute(
            "CREATE TABLE IF NOT EXISTS player_title_unlock_time ("
            "xuid TEXT NOT NULL, "
            "title TEXT NOT NULL, "
            "rarity TEXT NOT NULL DEFAULT '普通', "
            "unlocked_at TEXT, "
            "UNIQUE(xuid, title, rarity)"
            ")"
        )
        self.database_manager.execute(
            "CREATE TABLE IF NOT EXISTS player_title_equipped ("
            "xuid TEXT PRIMARY KEY, "
            "title TEXT, "
            "rarity TEXT DEFAULT '普通'"
            ")"
        )

    def ensure_tables(self) -> bool:
        """创建头衔相关表，并迁移到 (title, rarity) 复合标识。"""
        try:
            self._create_title_tables()
            if not self.database_manager.table_exists(self._table_def):
                print(
                    "[ARC Core]ERROR title_definitions missing before migrate; recreating"
                )
                self._create_title_tables()
            self._migrate_title_identity_schema()
            if not self.database_manager.table_exists(self._table_def):
                print(
                    "[ARC Core]ERROR title_definitions missing after migrate; recreating"
                )
                self._create_title_tables()
            self._seed_default_title_definitions()
            # v0.7.1 起解锁时间只走 player_title_unlock_time；空壳兼容表直接删掉
            try:
                self.database_manager.execute("DROP TABLE IF EXISTS player_title_extra")
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _table_columns(self, table: str) -> List[str]:
        try:
            rows = self.database_manager.query_all(f"PRAGMA table_info({table})", ()) or []
            return [str(r.get("name") or "") for r in rows if r.get("name")]
        except Exception:
            return []

    def _table_create_sql(self, table: str) -> str:
        """读 CREATE SQL；表名写进字面量以便 DatabaseManager 按路由命中正确库。"""
        try:
            # 仅允许标识符，防止注入
            if not table or not all(c.isalnum() or c == "_" for c in table):
                return ""
            row = self.database_manager.query_one(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='"
                + table
                + "'",
                (),
            )
            return str((row or {}).get("sql") or "")
        except Exception:
            return ""

    @staticmethod
    def _sql_has_title_rarity_pk(create_sql: str) -> bool:
        compact = str(create_sql or "").replace(" ", "").replace("\n", "").lower()
        return "primarykey(title,rarity)" in compact

    def _migrate_title_identity_schema(self) -> None:
        """将旧版「仅 title」主键迁移为 (title, rarity)。

        一律走 DatabaseManager.rebuild_table_copy（同连接事务 + VACUUM 备份），
        避免临时表落默认库、DROP 却打到路由共享库的跨库误删。
        """
        def_cols = self._table_columns(self._table_def)
        unlock_cols = self._table_columns(self._table_unlock_time)
        equipped_cols = self._table_columns(self._table_equipped)
        def_sql = self._table_create_sql(self._table_def)
        already_nr = self._sql_has_title_rarity_pk(def_sql)

        # --- title_definitions ---
        if def_cols and "rarity" in def_cols and not already_nr:
            ok = self.database_manager.rebuild_table_copy(
                logical_table=self._table_def,
                temp_table="title_definitions__nr",
                create_sql=(
                    "CREATE TABLE title_definitions__nr ("
                    "title TEXT NOT NULL, "
                    "rarity TEXT NOT NULL DEFAULT '普通', "
                    "description TEXT, "
                    "reward_money REAL DEFAULT 0, "
                    "reward_items TEXT DEFAULT '[]', "
                    "PRIMARY KEY (title, rarity)"
                    ")"
                ),
                copy_columns=[
                    "title",
                    "rarity",
                    "description",
                    "reward_money",
                    "reward_items",
                ],
                select_sql=(
                    "SELECT title, "
                    "CASE "
                    "WHEN rarity IS NULL OR rarity = '' THEN '普通' "
                    "WHEN rarity = '传说' THEN '传奇' "
                    "ELSE rarity END, "
                    "description, reward_money, "
                    "COALESCE(reward_items, '[]') "
                    "FROM title_definitions"
                ),
            )
            if not ok:
                print("[ARC Core]title_definitions PK rebuild skipped/failed")
        elif def_cols and "rarity" not in def_cols:
            # 极旧：无 rarity 列
            has_desc = "description" in def_cols
            has_money = "reward_money" in def_cols
            has_items = "reward_items" in def_cols
            desc_expr = "description" if has_desc else "''"
            money_expr = "COALESCE(reward_money, 0)" if has_money else "0"
            items_expr = "COALESCE(reward_items, '[]')" if has_items else "'[]'"
            ok = self.database_manager.rebuild_table_copy(
                logical_table=self._table_def,
                temp_table="title_definitions__nr",
                create_sql=(
                    "CREATE TABLE title_definitions__nr ("
                    "title TEXT NOT NULL, "
                    "rarity TEXT NOT NULL DEFAULT '普通', "
                    "description TEXT, "
                    "reward_money REAL DEFAULT 0, "
                    "reward_items TEXT DEFAULT '[]', "
                    "PRIMARY KEY (title, rarity)"
                    ")"
                ),
                copy_columns=[
                    "title",
                    "rarity",
                    "description",
                    "reward_money",
                    "reward_items",
                ],
                select_sql=(
                    f"SELECT title, '{DEFAULT_RARITY}', {desc_expr}, "
                    f"{money_expr}, {items_expr} FROM title_definitions"
                ),
            )
            if not ok:
                print("[ARC Core]title_definitions legacy rebuild skipped/failed")

        # --- player_title_unlock_time ---
        if unlock_cols and "rarity" not in unlock_cols:
            # 从同库 title_definitions 取稀有度；无定义则默认普通
            ok = self.database_manager.rebuild_table_copy(
                logical_table=self._table_unlock_time,
                temp_table="player_title_unlock_time__nr",
                create_sql=(
                    "CREATE TABLE player_title_unlock_time__nr ("
                    "xuid TEXT NOT NULL, "
                    "title TEXT NOT NULL, "
                    "rarity TEXT NOT NULL DEFAULT '普通', "
                    "unlocked_at TEXT, "
                    "UNIQUE(xuid, title, rarity)"
                    ")"
                ),
                copy_columns=["xuid", "title", "rarity", "unlocked_at"],
                select_sql=(
                    "SELECT u.xuid, u.title, "
                    "COALESCE("
                    "(SELECT d.rarity FROM title_definitions d "
                    "WHERE d.title = u.title LIMIT 1), "
                    f"'{DEFAULT_RARITY}'), "
                    "u.unlocked_at "
                    "FROM player_title_unlock_time u"
                ),
            )
            if not ok:
                print("[ARC Core]player_title_unlock_time rarity rebuild skipped/failed")
        elif unlock_cols and "rarity" in unlock_cols:
            try:
                self.database_manager.execute(
                    "UPDATE player_title_unlock_time SET rarity = ? "
                    "WHERE rarity IS NULL OR rarity = ''",
                    (DEFAULT_RARITY,),
                )
                self.database_manager.execute(
                    "UPDATE player_title_unlock_time SET rarity = '传奇' "
                    "WHERE rarity = '传说'"
                )
            except Exception:
                pass

        # --- player_title_equipped ---
        if equipped_cols and "rarity" not in equipped_cols:
            ok = self.database_manager.rebuild_table_copy(
                logical_table=self._table_equipped,
                temp_table="player_title_equipped__nr",
                create_sql=(
                    "CREATE TABLE player_title_equipped__nr ("
                    "xuid TEXT PRIMARY KEY, "
                    "title TEXT, "
                    "rarity TEXT DEFAULT '普通'"
                    ")"
                ),
                copy_columns=["xuid", "title", "rarity"],
                select_sql=(
                    "SELECT e.xuid, e.title, "
                    "CASE WHEN e.title IS NULL OR TRIM(e.title) = '' THEN NULL "
                    "ELSE COALESCE("
                    "(SELECT d.rarity FROM title_definitions d "
                    "WHERE d.title = e.title LIMIT 1), "
                    f"'{DEFAULT_RARITY}') END "
                    "FROM player_title_equipped e"
                ),
            )
            if not ok:
                print("[ARC Core]player_title_equipped rarity rebuild skipped/failed")
        elif equipped_cols and "rarity" in equipped_cols:
            try:
                self.database_manager.execute(
                    "UPDATE player_title_equipped SET rarity = ? "
                    "WHERE title IS NOT NULL AND title != '' "
                    "AND (rarity IS NULL OR rarity = '')",
                    (DEFAULT_RARITY,),
                )
            except Exception:
                pass

    def _seed_default_title_definitions(self) -> None:
        """确保配置中的默认头衔和 OP 头衔在 title_definitions 中存在。"""
        for t in self.get_default_titles():
            self.ensure_title_definition(t, DEFAULT_RARITY, "", 0.0, [])
        op_t = self.get_op_title()
        if op_t:
            self.ensure_title_definition(op_t, DEFAULT_RARITY, "", 0.0, [])

    def ensure_title_definition(
        self,
        title: str,
        rarity: str = DEFAULT_RARITY,
        description: str = "",
        reward_money: float = 0.0,
        reward_items: Optional[List] = None,
    ) -> bool:
        """若 (title, rarity) 未注册则插入；已存在同名同稀有度则不覆盖。"""
        if not title or not title.strip():
            return False
        title = title.strip()
        rarity = normalize_rarity(rarity)
        if reward_items is None:
            reward_items = []
        try:
            self.database_manager.execute(
                "INSERT OR IGNORE INTO title_definitions "
                "(title, rarity, description, reward_money, reward_items) VALUES (?, ?, ?, ?, ?)",
                (title, rarity, description, reward_money, json.dumps(reward_items, ensure_ascii=False)),
            )
            return True
        except Exception:
            return False

    def has_title_definition(self, title: str, rarity: str = DEFAULT_RARITY) -> bool:
        """是否已注册指定名称+稀有度的头衔。"""
        return self.get_title_definition(title, rarity) is not None

    def get_title_definition(
        self, title: str, rarity: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """获取头衔定义。

        - rarity 给定：按 (title, rarity) 精确匹配
        - rarity 为 None：若该名称仅一条则返回；多条时优先返回「普通」，否则返回第一条
        """
        title_s = str(title or "").strip()
        if not title_s:
            return None
        if rarity is not None and str(rarity).strip() != "":
            rarity_s = normalize_rarity(rarity)
            row = self.database_manager.query_one(
                "SELECT title, rarity, description, reward_money, reward_items "
                "FROM title_definitions WHERE title = ? AND rarity = ?",
                (title_s, rarity_s),
            )
            return self._row_to_definition(row)

        rows = self.database_manager.query_all(
            "SELECT title, rarity, description, reward_money, reward_items "
            "FROM title_definitions WHERE title = ?",
            (title_s,),
        ) or []
        if not rows:
            return None
        if len(rows) == 1:
            return self._row_to_definition(rows[0])
        for row in rows:
            if normalize_rarity(row.get("rarity")) == DEFAULT_RARITY:
                return self._row_to_definition(row)
        return self._row_to_definition(rows[0])

    def list_title_definitions_by_name(self, title: str) -> List[Dict[str, Any]]:
        title_s = str(title or "").strip()
        if not title_s:
            return []
        rows = self.database_manager.query_all(
            "SELECT title, rarity, description, reward_money, reward_items "
            "FROM title_definitions WHERE title = ? ORDER BY rarity",
            (title_s,),
        ) or []
        out = []
        for row in rows:
            defn = self._row_to_definition(row)
            if defn:
                out.append(defn)
        return out

    @staticmethod
    def _row_to_definition(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        reward_items = []
        if row.get("reward_items"):
            try:
                reward_items = json.loads(row["reward_items"])
            except (TypeError, ValueError, json.JSONDecodeError):
                reward_items = []
        return {
            "title": row["title"],
            "rarity": normalize_rarity(row.get("rarity")),
            "description": row.get("description") or "",
            "reward_money": float(row.get("reward_money") or 0),
            "reward_items": reward_items,
        }

    def set_title_definition(
        self,
        title: str,
        rarity: str,
        description: str,
        reward_money: float,
        reward_items: List,
    ) -> bool:
        """创建或覆盖指定 (title, rarity) 的头衔定义。"""
        if not title or not title.strip():
            return False
        title = title.strip()
        rarity = normalize_rarity(rarity)
        try:
            self.database_manager.execute(
                "INSERT OR REPLACE INTO title_definitions "
                "(title, rarity, description, reward_money, reward_items) VALUES (?, ?, ?, ?, ?)",
                (title, rarity, description, reward_money, json.dumps(reward_items, ensure_ascii=False)),
            )
            return True
        except Exception:
            return False

    def rename_title(
        self, old_title: str, new_title: str, rarity: Optional[str] = None
    ) -> bool:
        """重命名头衔：同时更新定义/解锁记录/佩戴记录。

        rarity 给定时只改该稀有度变体；否则改该名称下全部变体（要求新名均不冲突）。
        """
        try:
            old_title = (old_title or "").strip()
            new_title = (new_title or "").strip()
            if not old_title or not new_title:
                return False
            if old_title == new_title:
                return True

            if rarity is not None and str(rarity).strip() != "":
                old_defs = []
                d = self.get_title_definition(old_title, rarity)
                if d:
                    old_defs.append(d)
            else:
                old_defs = self.list_title_definitions_by_name(old_title)
            if not old_defs:
                return False

            for d in old_defs:
                r = normalize_rarity(d.get("rarity"))
                if self.get_title_definition(new_title, r):
                    return False

            for d in old_defs:
                r = normalize_rarity(d.get("rarity"))
                ok = self.set_title_definition(
                    new_title,
                    r,
                    d.get("description") or "",
                    float(d.get("reward_money") or 0.0),
                    d.get("reward_items") or [],
                )
                if not ok:
                    return False
                self.database_manager.execute(
                    "UPDATE player_title_unlock_time SET title = ? WHERE title = ? AND rarity = ?",
                    (new_title, old_title, r),
                )
                self.database_manager.execute(
                    "UPDATE player_title_equipped SET title = ? WHERE title = ? AND rarity = ?",
                    (new_title, old_title, r),
                )
                self.database_manager.execute(
                    "DELETE FROM title_definitions WHERE title = ? AND rarity = ?",
                    (old_title, r),
                )
            return True
        except Exception:
            return False

    def get_all_title_names(self) -> List[str]:
        """所有头衔名（去重，不含稀有度）。"""
        default = self.get_default_titles()
        op_t = self.get_op_title()
        rows = self.database_manager.query_all("SELECT DISTINCT title FROM title_definitions", ()) or []
        db_titles = [r["title"] for r in rows if r.get("title")]
        seen = set()
        result = []
        for t in default + ([op_t] if op_t else []) + db_titles:
            if t and t not in seen:
                result.append(t)
                seen.add(t)
        return result

    def get_all_title_entries(self) -> List[Dict[str, Any]]:
        """全部头衔定义条目（含同名不同稀有度）。"""
        rows = self.database_manager.query_all(
            "SELECT title, rarity, description, reward_money, reward_items "
            "FROM title_definitions ORDER BY title, rarity",
            (),
        ) or []
        out = []
        for row in rows:
            defn = self._row_to_definition(row)
            if defn:
                out.append(defn)
        # 确保默认/OP 也在列表中
        for t in self.get_default_titles() + ([self.get_op_title()] if self.get_op_title() else []):
            if not t:
                continue
            if not any(x.get("title") == t for x in out):
                self.ensure_title_definition(t, DEFAULT_RARITY, "", 0.0, [])
                d = self.get_title_definition(t, DEFAULT_RARITY)
                if d:
                    out.append(d)
        return out

    def rarity_rank(self, rarity: str) -> int:
        """稀有度排序用权重，未知稀有度视为最低档。"""
        return RARITY_ORDER.get(normalize_rarity(rarity), RARITY_ORDER[DEFAULT_RARITY])

    def preferred_grant_rarity(self, title: str, fallback: str = DEFAULT_RARITY) -> str:
        """自动授予头衔时使用的稀有度：已定义时取最高档，否则 fallback。"""
        title_s = str(title or "").strip()
        if not title_s:
            return normalize_rarity(fallback)
        defs = self.list_title_definitions_by_name(title_s)
        if not defs:
            return normalize_rarity(fallback)
        best = max(defs, key=lambda d: self.rarity_rank(d.get("rarity")))
        return normalize_rarity(best.get("rarity") or fallback)

    def pick_highest_rarity_title(self, title_names: List[str]) -> Optional[str]:
        """从已解锁头衔名列表中选出稀有度最高的一条（按名称检索定义；同名多稀有度取最高）。"""
        if not title_names:
            return None
        best_name: Optional[str] = None
        best_rank = -1
        for title_name in title_names:
            if not title_name:
                continue
            name = title_name.strip()
            defs = self.list_title_definitions_by_name(name)
            if not defs:
                rank = self.rarity_rank(DEFAULT_RARITY)
            else:
                rank = max(self.rarity_rank(d.get("rarity")) for d in defs)
            if rank > best_rank:
                best_rank = rank
                best_name = name
        return best_name

    def pick_highest_rarity_entry(
        self, entries: List[Dict[str, Any]]
    ) -> Optional[Dict[str, str]]:
        """从 [{title, rarity}, ...] 中选稀有度最高的一条。"""
        best: Optional[Dict[str, str]] = None
        best_rank = -1
        for entry in entries or []:
            title = str(entry.get("title") or "").strip()
            rarity = normalize_rarity(entry.get("rarity"))
            if not title:
                continue
            rank = self.rarity_rank(rarity)
            if rank > best_rank:
                best_rank = rank
                best = {"title": title, "rarity": rarity}
        return best

    def get_title_rarity_color(self, title: str, rarity: Optional[str] = None) -> str:
        """根据头衔稀有度返回 MC 颜色码。"""
        if rarity is not None and str(rarity).strip() != "":
            return RARITY_COLORS.get(normalize_rarity(rarity), "§f")
        defn = self.get_title_definition(title)
        r = (defn.get("rarity") or DEFAULT_RARITY) if defn else DEFAULT_RARITY
        return RARITY_COLORS.get(normalize_rarity(r), "§f")

    def get_normal_rarity_color(self) -> str:
        """「普通」稀有度对应颜色（用于公会名等与默认头衔一致的着色）。"""
        return RARITY_COLORS.get(DEFAULT_RARITY, "§f")

    def _get_default_titles_raw(self) -> str:
        raw = self.setting_manager.GetSetting("DEFAULT_TITLE")
        return (raw or "").strip()

    def get_default_titles(self) -> List[str]:
        """配置中的默认头衔列表（逗号分隔）。"""
        raw = self._get_default_titles_raw()
        if not raw:
            return []
        return [t.strip() for t in raw.split(",") if t.strip()]

    def get_op_title(self) -> Optional[str]:
        """配置中的 OP 专属头衔（仅一个）。"""
        raw = self.setting_manager.GetSetting("OP_TITLE")
        if not raw or not str(raw).strip():
            return None
        return str(raw).strip()

    def _xuid(self, player: Player) -> str:
        return str(player.xuid)

    def get_unlocked_titles(self, player: Player) -> List[str]:
        """玩家已解锁头衔名称列表（去重）。"""
        return sorted({e["title"] for e in self.get_unlocked_title_entries(player)})

    def get_unlocked_titles_by_xuid(self, xuid: str) -> List[str]:
        return sorted({e["title"] for e in self.get_unlocked_title_entries_by_xuid(xuid)})

    def get_unlocked_title_entries(self, player: Player) -> List[Dict[str, str]]:
        return self.get_unlocked_title_entries_by_xuid(self._xuid(player))

    def get_unlocked_title_entries_by_xuid(self, xuid: str) -> List[Dict[str, str]]:
        xs = str(xuid or "").strip()
        if not xs:
            return []
        rows = self.database_manager.query_all(
            "SELECT title, rarity FROM player_title_unlock_time WHERE xuid = ? "
            "ORDER BY title, rarity",
            (xs,),
        ) or []
        out = []
        for r in rows:
            title = str(r.get("title") or "").strip()
            if not title:
                continue
            out.append({"title": title, "rarity": normalize_rarity(r.get("rarity"))})
        return out

    def get_title_unlock_time(
        self, player: Player, title: str, rarity: Optional[str] = None
    ) -> Optional[str]:
        """玩家某头衔的解锁时间；rarity 省略时取该名称任一变体。"""
        title_s = title.strip()
        if rarity is not None and str(rarity).strip() != "":
            row = self.database_manager.query_one(
                "SELECT unlocked_at FROM player_title_unlock_time "
                "WHERE xuid = ? AND title = ? AND rarity = ?",
                (self._xuid(player), title_s, normalize_rarity(rarity)),
            )
        else:
            row = self.database_manager.query_one(
                "SELECT unlocked_at FROM player_title_unlock_time "
                "WHERE xuid = ? AND title = ? ORDER BY unlocked_at LIMIT 1",
                (self._xuid(player), title_s),
            )
        return row.get("unlocked_at") if row else None

    def get_equipped_title(self, player: Player) -> Optional[str]:
        """当前佩戴的头衔名称，未佩戴返回 None。"""
        info = self.get_equipped_title_entry(player)
        return info["title"] if info else None

    def get_equipped_title_by_xuid(self, xuid: str) -> Optional[str]:
        info = self.get_equipped_title_entry_by_xuid(xuid)
        return info["title"] if info else None

    def get_equipped_title_entry(self, player: Player) -> Optional[Dict[str, str]]:
        return self.get_equipped_title_entry_by_xuid(self._xuid(player))

    def get_equipped_title_entry_by_xuid(self, xuid: str) -> Optional[Dict[str, str]]:
        xs = (xuid or "").strip()
        if not xs:
            return None
        row = self.database_manager.query_one(
            "SELECT title, rarity FROM player_title_equipped WHERE xuid = ?",
            (xs,),
        )
        if not row or row.get("title") is None:
            return None
        title = str(row.get("title") or "").strip()
        if not title:
            return None
        return {"title": title, "rarity": normalize_rarity(row.get("rarity"))}

    def format_player_display_label(
        self, raw_player_name: str, equipped_title: Optional[str], rarity: Optional[str] = None
    ) -> str:
        """展示用：有佩戴头衔时为 [稀有色][头衔]§r名字，否则为裸名。"""
        name = (raw_player_name or "").strip() or "?"
        et = (equipped_title or "").strip() if equipped_title else ""
        if not et:
            return name
        color = self.get_title_rarity_color(et, rarity)
        return color + "[" + et + "]" + "§r" + name

    def set_equipped_title_by_xuid(
        self, xuid: str, title: Optional[str], rarity: Optional[str] = None
    ) -> bool:
        """按 xuid 设置佩戴头衔。title 为 None 则取消佩戴。"""
        xs = (xuid or "").strip()
        if not xs:
            return False
        if title is None or title == "":
            return self.database_manager.execute(
                "DELETE FROM player_title_equipped WHERE xuid = ?", (xs,)
            )
        title_s = str(title).strip()
        if not title_s:
            return False
        entries = self.get_unlocked_title_entries_by_xuid(xs)
        if rarity is not None and str(rarity).strip() != "":
            rarity_s = normalize_rarity(rarity)
            if not any(e["title"] == title_s and e["rarity"] == rarity_s for e in entries):
                return False
        else:
            matches = [e for e in entries if e["title"] == title_s]
            if not matches:
                return False
            if len(matches) == 1:
                rarity_s = matches[0]["rarity"]
            else:
                # 未指定稀有度且同名多条：取最高稀有度
                best = self.pick_highest_rarity_entry(matches)
                rarity_s = best["rarity"] if best else DEFAULT_RARITY
        self.database_manager.execute("DELETE FROM player_title_equipped WHERE xuid = ?", (xs,))
        return self.database_manager.execute(
            "INSERT INTO player_title_equipped (xuid, title, rarity) VALUES (?, ?, ?)",
            (xs, title_s, rarity_s),
        )

    def set_equipped_title(
        self, player: Player, title: Optional[str], rarity: Optional[str] = None
    ) -> bool:
        """设置佩戴头衔。"""
        return self.set_equipped_title_by_xuid(self._xuid(player), title, rarity)

    def unlock_title(
        self, player: Player, title: str, rarity: str = DEFAULT_RARITY
    ) -> Tuple[bool, bool]:
        """为玩家解锁头衔（名称+稀有度）。返回 (是否成功, 是否本次新解锁)。"""
        if not title or not title.strip():
            return False, False
        return self.unlock_title_by_xuid(
            self._xuid(player), title.strip(), rarity=rarity
        )

    def unlock_title_by_xuid(
        self,
        xuid: str,
        title: str,
        unlocked_at: Optional[str] = None,
        rarity: str = DEFAULT_RARITY,
    ) -> Tuple[bool, bool]:
        """按 xuid 解锁指定 (title, rarity)。返回 (是否成功, 是否本次新解锁)。"""
        if not xuid or not title or not title.strip():
            return False, False
        title = title.strip()
        rarity = normalize_rarity(rarity)
        if unlocked_at is None:
            unlocked_at = datetime.now().isoformat()
        try:
            if self.has_unlocked_title_by_xuid(xuid, title, rarity):
                return True, False
            # 确保定义存在（基本属性）
            self.ensure_title_definition(title, rarity, "", 0.0, [])
            ok = bool(
                self.database_manager.execute(
                    "INSERT INTO player_title_unlock_time (xuid, title, rarity, unlocked_at) "
                    "VALUES (?, ?, ?, ?)",
                    (xuid, title, rarity, unlocked_at),
                )
            )
            if ok:
                return True, True
            if self.has_unlocked_title_by_xuid(xuid, title, rarity):
                return True, False
            return False, False
        except Exception:
            return False, False

    def has_unlocked_title_by_xuid(
        self, xuid: str, title: str, rarity: Optional[str] = None
    ) -> bool:
        """查询玩家是否已解锁该头衔。

        rarity 给定：精确匹配；省略：该名称任一稀有度即可。
        """
        xs = str(xuid or "").strip()
        tt = str(title or "").strip()
        if not xs or not tt:
            return False
        if rarity is not None and str(rarity).strip() != "":
            row = self.database_manager.query_one(
                "SELECT 1 FROM player_title_unlock_time "
                "WHERE xuid = ? AND title = ? AND rarity = ?",
                (xs, tt, normalize_rarity(rarity)),
            )
        else:
            row = self.database_manager.query_one(
                "SELECT 1 FROM player_title_unlock_time WHERE xuid = ? AND title = ?",
                (xs, tt),
            )
        return row is not None

    def revoke_title_by_xuid(
        self, xuid: str, title: str, rarity: Optional[str] = None
    ) -> Tuple[bool, bool]:
        """按 xuid 撤销玩家头衔。rarity 省略则撤销该名称全部稀有度变体。"""
        try:
            xuid = (xuid or "").strip()
            title = (title or "").strip()
            if not xuid or not title:
                return False, False

            was_equipped = False
            equipped = self.get_equipped_title_entry_by_xuid(xuid)
            if equipped and equipped.get("title") == title:
                if rarity is None or normalize_rarity(rarity) == equipped.get("rarity"):
                    was_equipped = True
                    self.database_manager.execute(
                        "DELETE FROM player_title_equipped WHERE xuid = ?",
                        (xuid,),
                    )

            if rarity is not None and str(rarity).strip() != "":
                self.database_manager.execute(
                    "DELETE FROM player_title_unlock_time "
                    "WHERE xuid = ? AND title = ? AND rarity = ?",
                    (xuid, title, normalize_rarity(rarity)),
                )
            else:
                self.database_manager.execute(
                    "DELETE FROM player_title_unlock_time WHERE xuid = ? AND title = ?",
                    (xuid, title),
                )
            return True, was_equipped
        except Exception:
            return False, False

    def revoke_title(
        self, player: Player, title: str, rarity: Optional[str] = None
    ) -> Tuple[bool, bool]:
        """撤销玩家头衔（在线玩家版）。"""
        if not player:
            return False, False
        return self.revoke_title_by_xuid(str(player.xuid), title, rarity)

    def on_player_join(self, player: Player) -> None:
        """进服时：确保默认/OP 头衔解锁；非 OP 卸下 OP 头衔。"""
        xuid = self._xuid(player)
        default_titles = self.get_default_titles()
        op_title = self.get_op_title()
        to_ensure = list(default_titles)
        if op_title and getattr(player, "is_op", False):
            to_ensure.append(op_title)
        now_iso = datetime.now().isoformat()
        for t in to_ensure:
            if not t:
                continue
            rarity = self.preferred_grant_rarity(t)
            self.ensure_title_definition(t, rarity, "", 0.0, [])
            self.database_manager.execute(
                "INSERT OR IGNORE INTO player_title_unlock_time "
                "(xuid, title, rarity, unlocked_at) VALUES (?, ?, ?, ?)",
                (xuid, t, rarity, now_iso),
            )
            equipped = self.get_equipped_title_entry(player)
            if equipped and equipped.get("title") == t and equipped.get("rarity") != rarity:
                self.set_equipped_title(player, t, rarity)
        if op_title and not getattr(player, "is_op", False):
            equipped = self.get_equipped_title_entry(player)
            if equipped and equipped.get("title") == op_title:
                self.set_equipped_title(player, None)

    def format_chat_message(self, player: Player, original_message: str) -> str:
        """根据佩戴头衔格式化聊天（含稀有度颜色）。"""
        equipped = self.get_equipped_title_entry(player)
        name = player.name
        if equipped:
            color = self.get_title_rarity_color(equipped["title"], equipped["rarity"])
            return color + "[" + equipped["title"] + "]" + "§r" + name + ": " + original_message
        return name + ": " + original_message
