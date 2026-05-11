# -*- coding: utf-8 -*-
"""公会：建会扣费、职级、邀请、跨库路由下的 SQLite 表。"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ROLE_OWNER = "owner"
ROLE_MANAGER = "manager"
ROLE_MEMBER = "member"

# 公会规模等级（按门槛人数从小到大）
SIZE_TIER_SMALL = "small"
SIZE_TIER_MEDIUM = "medium"
SIZE_TIER_LARGE = "large"
SIZE_TIERS: Tuple[str, ...] = (SIZE_TIER_SMALL, SIZE_TIER_MEDIUM, SIZE_TIER_LARGE)

# 默认公会规模上限（服主可在 core_setting.yml 中通过
# GUILD_SIZE_SMALL_MAX / GUILD_SIZE_MEDIUM_MAX / GUILD_SIZE_LARGE_MAX 修改）
_DEFAULT_TIER_MAX: Dict[str, int] = {
    SIZE_TIER_SMALL: 10,
    SIZE_TIER_MEDIUM: 20,
    SIZE_TIER_LARGE: 40,
}

# 公会名颜色码过滤：MC 基岩版格式码以 § 起，后跟单个字符（颜色或样式 0-9 / a-u / r 等）；
# 玩家可能在公会名中粘贴此类格式码，所有读写公会名前都先剥离，避免污染聊天/头顶名。
_MC_COLOR_RE = re.compile(r"§.", flags=re.DOTALL)

# 公会名：最多字符数；禁止 []"（避免与展示括号冲突、减少注入相关字符误用）
GUILD_NAME_MAX_LEN = 8
_FORBIDDEN_GUILD_NAME_CHARS = re.compile(r'[\[\]"]')

# (ok, error_code) 错误码供语言文件映射
GuildResult = Tuple[bool, Optional[str]]


def strip_mc_color_codes(value: Any) -> str:
    """去除字符串中所有 MC 格式码（§X）以及残留的孤立 §。"""
    if value is None:
        return ""
    s = str(value)
    s = _MC_COLOR_RE.sub("", s)
    s = s.replace("§", "")
    return s


class GuildSystem:
    def __init__(self, database_manager, setting_manager, economy, logger=None):
        self.db = database_manager
        self.setting_manager = setting_manager
        self.economy = economy
        self.logger = logger

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    def get_create_cost(self) -> float:
        raw = self.setting_manager.GetSetting("GUILD_CREATE_COST")
        if raw is None or str(raw).strip() == "":
            return 100000.0
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 100000.0

    def get_rename_cost(self) -> float:
        """会长改名公会需要支付的金钱（默认 0 即免费）。"""
        raw = self.setting_manager.GetSetting("GUILD_RENAME_COST")
        if raw is None or str(raw).strip() == "":
            return 0.0
        try:
            v = float(raw)
            return v if v > 0 else 0.0
        except (TypeError, ValueError):
            return 0.0

    # ─── 公会规模 ───────────────────────────────────────────────────────────
    def _setting_int(self, key: str, default: int) -> int:
        raw = self.setting_manager.GetSetting(key)
        if raw is None or str(raw).strip() == "":
            return int(default)
        try:
            v = int(str(raw).strip())
            if v < 1:
                return int(default)
            return v
        except (TypeError, ValueError):
            return int(default)

    @staticmethod
    def normalize_size_tier(tier: Any) -> str:
        s = str(tier or "").strip().lower()
        if s in SIZE_TIERS:
            return s
        return SIZE_TIER_SMALL

    def get_size_tier_max(self, tier: str) -> int:
        """获取指定规模等级的成员人数上限。"""
        t = self.normalize_size_tier(tier)
        if t == SIZE_TIER_LARGE:
            return self._setting_int(
                "GUILD_SIZE_LARGE_MAX", _DEFAULT_TIER_MAX[SIZE_TIER_LARGE]
            )
        if t == SIZE_TIER_MEDIUM:
            return self._setting_int(
                "GUILD_SIZE_MEDIUM_MAX", _DEFAULT_TIER_MAX[SIZE_TIER_MEDIUM]
            )
        return self._setting_int(
            "GUILD_SIZE_SMALL_MAX", _DEFAULT_TIER_MAX[SIZE_TIER_SMALL]
        )

    def get_guild_size_tier(self, guild_id: int) -> str:
        g = self.get_guild(guild_id)
        if not g:
            return SIZE_TIER_SMALL
        return self.normalize_size_tier(g.get("size_tier"))

    def get_guild_size_max(self, guild_id: int) -> int:
        return self.get_size_tier_max(self.get_guild_size_tier(guild_id))

    def count_members(self, guild_id: int) -> int:
        try:
            row = self.db.query_one(
                "SELECT COUNT(1) AS c FROM guild_members WHERE guild_id = ?",
                (int(guild_id),),
            )
            return int(row.get("c") or 0) if row else 0
        except Exception:
            return 0

    def is_guild_full(self, guild_id: int) -> bool:
        try:
            cap = self.get_guild_size_max(int(guild_id))
            cur = self.count_members(int(guild_id))
            return cur >= cap
        except Exception:
            return False

    def set_size_tier(self, guild_id: int, tier: str) -> GuildResult:
        """直接设置公会规模等级（不做职级校验，供 OP 或上层逻辑调用）。"""
        try:
            gid = int(guild_id)
        except (TypeError, ValueError):
            return False, "GUILD_NOT_FOUND"
        t = self.normalize_size_tier(tier)
        if not self.get_guild(gid):
            return False, "GUILD_NOT_FOUND"
        ok = self.db.update("guilds", {"size_tier": t}, "id = ?", (gid,))
        return (True, None) if ok else (False, "GUILD_DB_ERROR")

    @staticmethod
    def _tier_rank(tier: str) -> int:
        return {SIZE_TIER_SMALL: 0, SIZE_TIER_MEDIUM: 1, SIZE_TIER_LARGE: 2}.get(
            GuildSystem.normalize_size_tier(tier), 0
        )

    def get_upgrade_cost(self, target_tier: str) -> int:
        """读取升级到指定规模需要消耗的公共贡献点（默认中型 10000、大型 100000）。"""
        t = self.normalize_size_tier(target_tier)
        if t == SIZE_TIER_MEDIUM:
            return self._setting_int("GUILD_UPGRADE_TO_MEDIUM_COST", 10000)
        if t == SIZE_TIER_LARGE:
            return self._setting_int("GUILD_UPGRADE_TO_LARGE_COST", 100000)
        return 0

    def upgrade_size_tier_with_contribution(
        self, actor_xuid: str, target_tier: str
    ) -> Tuple[bool, Optional[str], Dict[str, int]]:
        """
        会长 / 管理员消耗公会公共贡献点升级公会规模。
        - 仅允许从低向高升级（small -> medium / large、medium -> large）
        - 不能升级到 small（也不会退还贡献点）
        :return: (ok, error_code, info)
                 info = {
                   'guild_id': int,
                   'old_tier': str, 'new_tier': str,
                   'cost': int,
                   'guild_total_contribution': int,
                 }
        """
        info: Dict[str, int] = {
            "guild_id": 0,
            "old_tier": "",
            "new_tier": "",
            "cost": 0,
            "guild_total_contribution": 0,
        }
        actor = str(actor_xuid or "").strip()
        if not actor:
            return False, "GUILD_INVALID_PLAYER", info
        target = self.normalize_size_tier(target_tier)
        if target not in (SIZE_TIER_MEDIUM, SIZE_TIER_LARGE):
            return False, "GUILD_TIER_NOT_UPGRADABLE", info

        mem = self.get_membership(actor)
        if not mem:
            return False, "GUILD_NOT_IN_GUILD", info
        role = str(mem.get("role") or "")
        if role not in (ROLE_OWNER, ROLE_MANAGER):
            return False, "GUILD_NO_PERMISSION", info

        gid = int(mem.get("guild_id") or 0)
        if gid <= 0:
            return False, "GUILD_NOT_FOUND", info
        g = self.get_guild(gid)
        if not g:
            return False, "GUILD_NOT_FOUND", info

        old_tier = self.normalize_size_tier(g.get("size_tier"))
        info["guild_id"] = gid
        info["old_tier"] = old_tier
        info["new_tier"] = target
        info["guild_total_contribution"] = self.get_guild_total_contribution(gid)

        if self._tier_rank(target) <= self._tier_rank(old_tier):
            return False, "GUILD_TIER_NOT_UPGRADABLE", info

        cost = self.get_upgrade_cost(target)
        info["cost"] = int(cost)
        if cost <= 0:
            return False, "GUILD_TIER_NOT_UPGRADABLE", info

        if info["guild_total_contribution"] < cost:
            return False, "GUILD_CONTRIB_NOT_ENOUGH", info

        # 先扣公共贡献点，再升级；任一步失败回滚
        ok_consume, err_consume, new_total = self.consume_guild_contribution(gid, cost)
        if not ok_consume:
            return False, err_consume or "GUILD_DB_ERROR", info

        ok_set, err_set = self.set_size_tier(gid, target)
        if not ok_set:
            # 回滚扣减
            try:
                self.db.execute(
                    "UPDATE guilds SET total_contribution = COALESCE(total_contribution, 0) + ? "
                    "WHERE id = ?",
                    (int(cost), gid),
                )
            except Exception:
                pass
            info["guild_total_contribution"] = self.get_guild_total_contribution(gid)
            return False, err_set or "GUILD_DB_ERROR", info

        info["guild_total_contribution"] = int(new_total)
        return True, None, info

    # ─── 公会贡献点 ────────────────────────────────────────────────────────
    def get_member_contribution(self, xuid: str) -> int:
        xuid_s = str(xuid or "").strip()
        if not xuid_s:
            return 0
        try:
            row = self.db.query_one(
                "SELECT contribution FROM guild_members WHERE xuid = ?",
                (xuid_s,),
            )
            if not row:
                return 0
            return int(row.get("contribution") or 0)
        except Exception:
            return 0

    def get_guild_total_contribution(self, guild_id: int) -> int:
        try:
            gid = int(guild_id)
        except (TypeError, ValueError):
            return 0
        try:
            row = self.db.query_one(
                "SELECT total_contribution FROM guilds WHERE id = ?", (gid,)
            )
            if not row:
                return 0
            return int(row.get("total_contribution") or 0)
        except Exception:
            return 0

    def add_contribution_by_xuid(
        self, xuid: str, points: int
    ) -> Tuple[bool, Optional[str], Dict[str, int]]:
        """
        给玩家增加公会贡献点。
        - 玩家私人贡献点 += points
        - 玩家所在公会的公共贡献点 += points
        :return: (ok, error_code, info)
                 info = {"personal": int, "guild_total": int, "guild_id": int}
        """
        info: Dict[str, int] = {"personal": 0, "guild_total": 0, "guild_id": 0}
        xuid_s = str(xuid or "").strip()
        if not xuid_s:
            return False, "GUILD_INVALID_PLAYER", info
        try:
            pts = int(points)
        except (TypeError, ValueError):
            return False, "GUILD_CONTRIB_INVALID_POINTS", info
        if pts <= 0:
            return False, "GUILD_CONTRIB_INVALID_POINTS", info

        mem = self.get_membership(xuid_s)
        if not mem:
            return False, "GUILD_NOT_IN_GUILD", info
        gid = int(mem.get("guild_id") or 0)
        if gid <= 0:
            return False, "GUILD_NOT_FOUND", info

        ok1 = self.db.execute(
            "UPDATE guild_members SET contribution = COALESCE(contribution, 0) + ? "
            "WHERE xuid = ? AND guild_id = ?",
            (pts, xuid_s, gid),
        )
        ok2 = self.db.execute(
            "UPDATE guilds SET total_contribution = COALESCE(total_contribution, 0) + ? "
            "WHERE id = ?",
            (pts, gid),
        )
        if not (ok1 and ok2):
            return False, "GUILD_DB_ERROR", info

        info["guild_id"] = gid
        info["personal"] = self.get_member_contribution(xuid_s)
        info["guild_total"] = self.get_guild_total_contribution(gid)
        return True, None, info

    def consume_guild_contribution(
        self, guild_id: int, points: int
    ) -> Tuple[bool, Optional[str], int]:
        """
        消耗公会公共贡献点。仅扣减公共值，不影响成员私人贡献点。
        :return: (ok, error_code, new_total)
        """
        try:
            gid = int(guild_id)
        except (TypeError, ValueError):
            return False, "GUILD_NOT_FOUND", 0
        try:
            pts = int(points)
        except (TypeError, ValueError):
            return False, "GUILD_CONTRIB_INVALID_POINTS", 0
        if pts <= 0:
            return False, "GUILD_CONTRIB_INVALID_POINTS", 0
        if not self.get_guild(gid):
            return False, "GUILD_NOT_FOUND", 0
        cur = self.get_guild_total_contribution(gid)
        if cur < pts:
            return False, "GUILD_CONTRIB_NOT_ENOUGH", cur
        ok = self.db.execute(
            "UPDATE guilds SET total_contribution = COALESCE(total_contribution, 0) - ? "
            "WHERE id = ?",
            (pts, gid),
        )
        if not ok:
            return False, "GUILD_DB_ERROR", cur
        return True, None, self.get_guild_total_contribution(gid)

    def consume_member_contribution(
        self, xuid: str, points: int
    ) -> Tuple[bool, Optional[str], int]:
        """
        扣除成员私人公会贡献点（不影响公会公共池）。
        :return: (ok, error_code, personal_after_or_current_on_fail)
        """
        xuid_s = str(xuid or "").strip()
        if not xuid_s:
            return False, "GUILD_INVALID_PLAYER", 0
        try:
            pts = int(points)
        except (TypeError, ValueError):
            return False, "GUILD_CONTRIB_INVALID_POINTS", 0
        if pts < 0:
            return False, "GUILD_CONTRIB_INVALID_POINTS", 0
        if pts == 0:
            return True, None, self.get_member_contribution(xuid_s)
        if not self.get_membership(xuid_s):
            return False, "GUILD_NOT_IN_GUILD", 0
        cur = self.get_member_contribution(xuid_s)
        if cur < pts:
            return False, "GUILD_CONTRIB_NOT_ENOUGH", cur
        ok = self.db.execute(
            "UPDATE guild_members SET contribution = COALESCE(contribution, 0) - ? "
            "WHERE xuid = ?",
            (pts, xuid_s),
        )
        if not ok:
            return False, "GUILD_DB_ERROR", cur
        return True, None, self.get_member_contribution(xuid_s)

    def refund_guild_contribution_pool(self, guild_id: int, points: int) -> bool:
        """仅回滚公会公共池（不改动成员个人贡献），用于创建领地等失败后的补偿。"""
        try:
            gid = int(guild_id)
            pts = int(points)
        except (TypeError, ValueError):
            return False
        if pts <= 0:
            return True
        if not self.get_guild(gid):
            return False
        return bool(
            self.db.execute(
                "UPDATE guilds SET total_contribution = COALESCE(total_contribution, 0) + ? "
                "WHERE id = ?",
                (pts, gid),
            )
        )

    def ensure_tables(self) -> bool:
        try:
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS guilds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    owner_xuid TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    motto TEXT DEFAULT '',
                    size_tier TEXT NOT NULL DEFAULT 'small',
                    total_contribution INTEGER NOT NULL DEFAULT 0,
                    join_requires_approval INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_members (
                    guild_id INTEGER NOT NULL,
                    xuid TEXT NOT NULL,
                    role TEXT NOT NULL,
                    joined_at TEXT NOT NULL,
                    contribution INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, xuid),
                    UNIQUE (xuid),
                    FOREIGN KEY (guild_id) REFERENCES guilds(id)
                )
                """
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_guild_members_guild ON guild_members(guild_id)"
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_invites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    invitee_xuid TEXT NOT NULL,
                    inviter_xuid TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (guild_id, invitee_xuid),
                    FOREIGN KEY (guild_id) REFERENCES guilds(id)
                )
                """
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_guild_invites_invitee ON guild_invites(invitee_xuid)"
            )
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_join_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    applicant_xuid TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (guild_id, applicant_xuid),
                    FOREIGN KEY (guild_id) REFERENCES guilds(id)
                )
                """
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_guild_join_req_guild ON guild_join_requests(guild_id)"
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_guild_join_req_applicant ON guild_join_requests(applicant_xuid)"
            )
            self._upgrade_columns()
            return True
        except Exception:
            return False

    def _column_exists(self, table: str, column: str) -> bool:
        try:
            cols = self.db.query_all(f"PRAGMA table_info({table})")
            return any(str(c.get("name") or "") == column for c in cols)
        except Exception:
            return False

    def _upgrade_columns(self) -> None:
        """旧库平滑升级：补齐公会规模与贡献点字段。"""
        try:
            if not self._column_exists("guilds", "size_tier"):
                self.db.execute(
                    "ALTER TABLE guilds ADD COLUMN size_tier TEXT NOT NULL DEFAULT 'small'"
                )
            if not self._column_exists("guilds", "total_contribution"):
                self.db.execute(
                    "ALTER TABLE guilds ADD COLUMN total_contribution INTEGER NOT NULL DEFAULT 0"
                )
            if not self._column_exists("guild_members", "contribution"):
                self.db.execute(
                    "ALTER TABLE guild_members ADD COLUMN contribution INTEGER NOT NULL DEFAULT 0"
                )
            if not self._column_exists("guilds", "join_requires_approval"):
                self.db.execute(
                    "ALTER TABLE guilds ADD COLUMN join_requires_approval INTEGER NOT NULL DEFAULT 1"
                )
        except Exception:
            # 升级失败时不阻塞插件加载，运行期相关读取使用 COALESCE 兜底
            pass

    @staticmethod
    def _validate_guild_name(name: Any) -> Tuple[Optional[str], Optional[str]]:
        """
        校验新建/改名用的公会名（不入库前的玩家输入）。
        规则：去首尾空白；长度不超过 GUILD_NAME_MAX_LEN；禁止 §（含 MC 格式码）；
        禁止 [ ] " 字符。
        返回 (可用名字, 错误码)；通过时错误码为 None。
        """
        if name is None:
            return None, "GUILD_INVALID_NAME"
        s = str(name).strip()
        if not s:
            return None, "GUILD_INVALID_NAME"
        if "§" in s:
            return None, "GUILD_NAME_NO_COLOR_CODES"
        if _FORBIDDEN_GUILD_NAME_CHARS.search(s):
            return None, "GUILD_NAME_FORBIDDEN_CHARS"
        if len(s) > GUILD_NAME_MAX_LEN:
            return None, "GUILD_NAME_TOO_LONG"
        return s, None

    @staticmethod
    def _normalize_guild_name(name: str) -> Optional[str]:
        """与 _validate_guild_name 一致；无效时返回 None（仅名字，不含错误原因）。"""
        n, err = GuildSystem._validate_guild_name(name)
        return n if err is None else None

    @staticmethod
    def sanitize_guild_name(name: Any) -> str:
        """对外公开的公会名清洗工具（不做长度校验，仅剥离 MC 格式码并去首尾空白）。"""
        if name is None:
            return ""
        return strip_mc_color_codes(name).strip()

    def get_membership(self, xuid: str) -> Optional[Dict[str, Any]]:
        xuid = str(xuid).strip()
        if not xuid:
            return None
        row = self.db.query_one(
            "SELECT guild_id, xuid, role, joined_at FROM guild_members WHERE xuid = ?",
            (xuid,),
        )
        return dict(row) if row else None

    def get_guild(self, guild_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.query_one("SELECT * FROM guilds WHERE id = ?", (int(guild_id),))
        if not row:
            return None
        d = dict(row)
        # 读取兜底：旧数据若曾被注入过格式码，统一在出口处剥离
        if d.get("name") is not None:
            d["name"] = strip_mc_color_codes(d.get("name")).strip()
        return d

    def get_guild_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        n = self._normalize_guild_name(name)
        if not n:
            return None
        row = self.db.query_one("SELECT * FROM guilds WHERE name = ?", (n,))
        if not row:
            return None
        d = dict(row)
        if d.get("name") is not None:
            d["name"] = strip_mc_color_codes(d.get("name")).strip()
        return d

    def list_members(self, guild_id: int) -> List[Dict[str, Any]]:
        return self.db.query_all(
            """
            SELECT guild_id, xuid, role, joined_at, contribution
            FROM guild_members
            WHERE guild_id = ?
            ORDER BY
                CASE role
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    ELSE 2
                END,
                xuid
            """,
            (int(guild_id), ROLE_OWNER, ROLE_MANAGER),
        )

    def guild_join_requires_approval(self, guild_id: int) -> bool:
        g = self.get_guild(int(guild_id))
        if not g:
            return True
        raw = g.get("join_requires_approval")
        if raw is None:
            return True
        try:
            return int(raw) != 0
        except (TypeError, ValueError):
            return True

    def list_guilds_directory(self, name_substring: str = "") -> List[Dict[str, Any]]:
        """
        服务器公会列表（用于公开浏览）。
        排序：规模等级降序（大→中→小），同规模按公共贡献点降序，再按 id 降序。
        可选按名称子串过滤（大小写不敏感）。
        """
        rows = self.db.query_all(
            """
            SELECT
                g.id,
                g.name,
                g.motto,
                g.size_tier,
                g.total_contribution,
                g.join_requires_approval,
                (SELECT COUNT(1) FROM guild_members m WHERE m.guild_id = g.id) AS member_count
            FROM guilds g
            """
        )
        out: List[Dict[str, Any]] = []
        needle = str(name_substring or "").strip().lower()
        for row in rows or []:
            d = dict(row)
            if d.get("name") is not None:
                d["name"] = strip_mc_color_codes(d.get("name")).strip()
            if needle and needle not in str(d.get("name") or "").lower():
                continue
            out.append(d)

        def _sort_key(r: Dict[str, Any]) -> Tuple[int, int, int]:
            tid = int(r.get("id") or 0)
            tr = self._tier_rank(str(r.get("size_tier") or ""))
            tc = int(r.get("total_contribution") or 0)
            return (-tr, -tc, -tid)

        out.sort(key=_sort_key)
        return out

    def set_guild_join_requires_approval(
        self, actor_xuid: str, requires_approval: bool
    ) -> GuildResult:
        actor = str(actor_xuid or "").strip()
        if not actor:
            return False, "GUILD_INVALID_PLAYER"
        mem = self.get_membership(actor)
        if not mem or str(mem.get("role") or "") not in (ROLE_OWNER, ROLE_MANAGER):
            return False, "GUILD_NO_PERMISSION"
        gid = int(mem.get("guild_id") or 0)
        if gid <= 0 or not self.get_guild(gid):
            return False, "GUILD_NOT_FOUND"
        flag = 1 if requires_approval else 0
        ok = self.db.update(
            "guilds",
            {"join_requires_approval": flag},
            "id = ?",
            (gid,),
        )
        return (True, None) if ok else (False, "GUILD_DB_ERROR")

    def add_guild_member(
        self, guild_id: int, xuid: str, role: str = ROLE_MEMBER
    ) -> GuildResult:
        """插入公会成员（普通入会、邀请、审批通过等共用）。"""
        xuid_s = str(xuid or "").strip()
        if not xuid_s:
            return False, "GUILD_INVALID_PLAYER"
        r = str(role or "").strip().lower()
        if r not in (ROLE_MEMBER, ROLE_MANAGER, ROLE_OWNER):
            return False, "GUILD_INVALID_ROLE"
        if self.get_membership(xuid_s):
            return False, "GUILD_ALREADY_IN_GUILD"
        if not self.get_guild(int(guild_id)):
            return False, "GUILD_NOT_FOUND"
        if self.is_guild_full(int(guild_id)):
            return False, "GUILD_FULL"
        ts = self._now_iso()
        ok = self.db.insert(
            "guild_members",
            {
                "guild_id": int(guild_id),
                "xuid": xuid_s,
                "role": r,
                "joined_at": ts,
                "contribution": 0,
            },
        )
        if not ok:
            return False, "GUILD_DB_ERROR"
        try:
            self.db.delete("guild_join_requests", "applicant_xuid = ?", (xuid_s,))
            self.db.delete("guild_invites", "invitee_xuid = ?", (xuid_s,))
        except Exception:
            pass
        return True, None

    def try_public_join_guild(
        self, applicant_xuid: str, guild_id: int
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        公开申请/加入：若公会配置为无需审核则直接入会；否则写入待审批申请。
        :return: (ok, error_code, outcome) outcome 为 ``joined`` | ``pending`` | None
        """
        xuid_s = str(applicant_xuid or "").strip()
        if not xuid_s:
            return False, "GUILD_INVALID_PLAYER", None
        gid = int(guild_id)
        if not self.get_guild(gid):
            return False, "GUILD_NOT_FOUND", None
        if self.get_membership(xuid_s):
            return False, "GUILD_ALREADY_IN_GUILD", None
        if self.is_guild_full(gid):
            return False, "GUILD_FULL", None
        if self.guild_join_requires_approval(gid):
            ok, err = self.submit_join_request(xuid_s, gid)
            return ok, err, "pending" if ok else None
        ok, err = self.add_guild_member(gid, xuid_s, ROLE_MEMBER)
        return ok, err, "joined" if ok else None

    def submit_join_request(self, applicant_xuid: str, guild_id: int) -> GuildResult:
        xuid_s = str(applicant_xuid or "").strip()
        if not xuid_s:
            return False, "GUILD_INVALID_PLAYER"
        gid = int(guild_id)
        if not self.get_guild(gid):
            return False, "GUILD_NOT_FOUND"
        if self.get_membership(xuid_s):
            return False, "GUILD_ALREADY_IN_GUILD"
        if self.is_guild_full(gid):
            return False, "GUILD_FULL"
        existing = self.db.query_one(
            "SELECT id FROM guild_join_requests WHERE guild_id = ? AND applicant_xuid = ?",
            (gid, xuid_s),
        )
        if existing:
            return False, "GUILD_JOIN_REQUEST_DUPLICATE"
        ts = self._now_iso()
        ok = self.db.insert(
            "guild_join_requests",
            {"guild_id": gid, "applicant_xuid": xuid_s, "created_at": ts},
        )
        return (True, None) if ok else (False, "GUILD_DB_ERROR")

    def count_join_requests(self, guild_id: int) -> int:
        try:
            row = self.db.query_one(
                "SELECT COUNT(1) AS c FROM guild_join_requests WHERE guild_id = ?",
                (int(guild_id),),
            )
            return int(row.get("c") or 0) if row else 0
        except Exception:
            return 0

    def list_join_requests(self, guild_id: int) -> List[Dict[str, Any]]:
        return self.db.query_all(
            """
            SELECT id, guild_id, applicant_xuid, created_at
            FROM guild_join_requests
            WHERE guild_id = ?
            ORDER BY created_at ASC
            """,
            (int(guild_id),),
        )

    def get_join_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.query_one(
            "SELECT * FROM guild_join_requests WHERE id = ?", (int(request_id),)
        )
        return dict(row) if row else None

    def approve_join_request(self, actor_xuid: str, request_id: int) -> GuildResult:
        actor = str(actor_xuid or "").strip()
        if not actor:
            return False, "GUILD_INVALID_PLAYER"
        mem = self.get_membership(actor)
        if not mem or str(mem.get("role") or "") not in (ROLE_OWNER, ROLE_MANAGER):
            return False, "GUILD_NO_PERMISSION"
        req = self.get_join_request(int(request_id))
        if not req:
            return False, "GUILD_JOIN_REQUEST_NOT_FOUND"
        gid = int(req.get("guild_id") or 0)
        if gid != int(mem.get("guild_id") or 0):
            return False, "GUILD_NO_PERMISSION"
        applicant = str(req.get("applicant_xuid") or "").strip()
        if not applicant:
            return False, "GUILD_JOIN_REQUEST_NOT_FOUND"
        if self.get_membership(applicant):
            self.db.delete("guild_join_requests", "id = ?", (int(request_id),))
            return False, "GUILD_ALREADY_IN_GUILD"
        if self.is_guild_full(gid):
            return False, "GUILD_FULL"
        ok, err = self.add_guild_member(gid, applicant, ROLE_MEMBER)
        if not ok:
            return False, err or "GUILD_DB_ERROR"
        return True, None

    def reject_join_request(self, actor_xuid: str, request_id: int) -> GuildResult:
        actor = str(actor_xuid or "").strip()
        if not actor:
            return False, "GUILD_INVALID_PLAYER"
        mem = self.get_membership(actor)
        if not mem or str(mem.get("role") or "") not in (ROLE_OWNER, ROLE_MANAGER):
            return False, "GUILD_NO_PERMISSION"
        req = self.get_join_request(int(request_id))
        if not req:
            return False, "GUILD_JOIN_REQUEST_NOT_FOUND"
        if int(req.get("guild_id") or 0) != int(mem.get("guild_id") or 0):
            return False, "GUILD_NO_PERMISSION"
        if self.db.delete("guild_join_requests", "id = ?", (int(request_id),)):
            return True, None
        return False, "GUILD_DB_ERROR"

    def list_invites_for_player(self, invitee_xuid: str) -> List[Dict[str, Any]]:
        invitee_xuid = str(invitee_xuid).strip()
        if not invitee_xuid:
            return []
        rows = self.db.query_all(
            """
            SELECT i.id AS invite_id, i.guild_id, i.inviter_xuid, i.created_at, g.name AS guild_name
            FROM guild_invites i
            JOIN guilds g ON g.id = i.guild_id
            WHERE i.invitee_xuid = ?
            ORDER BY i.created_at DESC
            """,
            (invitee_xuid,),
        )
        for row in rows:
            if row.get("guild_name") is not None:
                row["guild_name"] = strip_mc_color_codes(row.get("guild_name")).strip()
        return rows

    def get_invite(self, invite_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.query_one(
            "SELECT * FROM guild_invites WHERE id = ?", (int(invite_id),)
        )
        return dict(row) if row else None

    def _refund_create_cost(self, owner_xuid: str, cost: float) -> None:
        try:
            self.economy.increase_player_money_by_xuid(owner_xuid, cost)
        except Exception:
            pass

    def create_guild(
        self, name: str, owner_xuid: str, motto: str = ""
    ) -> GuildResult:
        owner_xuid = str(owner_xuid).strip()
        n, name_err = self._validate_guild_name(name)
        if not n:
            return False, name_err or "GUILD_INVALID_NAME"
        if not owner_xuid:
            return False, "GUILD_INVALID_PLAYER"
        if self.get_membership(owner_xuid):
            return False, "GUILD_ALREADY_IN_GUILD"
        if self.get_guild_by_name(n):
            return False, "GUILD_NAME_TAKEN"

        cost = self.economy.round_money(self.get_create_cost())
        if cost > 0:
            if not self.economy.judge_if_player_has_enough_money_by_xuid(owner_xuid, cost):
                return False, "GUILD_NOT_ENOUGH_MONEY"
            if not self.economy.decrease_player_money_by_xuid(owner_xuid, cost):
                return False, "GUILD_NOT_ENOUGH_MONEY"

        ts = self._now_iso()
        motto_s = (str(motto).strip() if motto else "")[:128]
        data_g = {
            "name": n,
            "owner_xuid": owner_xuid,
            "created_at": ts,
            "motto": motto_s,
            "size_tier": SIZE_TIER_SMALL,
            "total_contribution": 0,
            "join_requires_approval": 1,
        }
        fields = ",".join(data_g.keys())
        placeholders = ",".join(["?" for _ in data_g])
        sql_ins = f"INSERT INTO guilds ({fields}) VALUES ({placeholders})"
        try:
            conn = self.db._resolve_connection(sql_ins)
            cur = conn.cursor()
            cur.execute(sql_ins, tuple(data_g.values()))
            gid = int(cur.lastrowid)
            conn.commit()
        except Exception:
            if cost > 0:
                self._refund_create_cost(owner_xuid, cost)
            return False, "GUILD_DB_ERROR"
        if gid <= 0:
            if cost > 0:
                self._refund_create_cost(owner_xuid, cost)
            return False, "GUILD_DB_ERROR"

        ok_m = self.db.insert(
            "guild_members",
            {
                "guild_id": gid,
                "xuid": owner_xuid,
                "role": ROLE_OWNER,
                "joined_at": ts,
                "contribution": 0,
            },
        )
        if not ok_m:
            self.db.delete("guilds", "id = ?", (gid,))
            if cost > 0:
                self._refund_create_cost(owner_xuid, cost)
            return False, "GUILD_DB_ERROR"

        return True, None

    def _actor_role(self, actor_xuid: str, guild_id: int) -> Optional[str]:
        row = self.db.query_one(
            "SELECT role FROM guild_members WHERE guild_id = ? AND xuid = ?",
            (int(guild_id), str(actor_xuid).strip()),
        )
        if not row:
            return None
        return str(row.get("role") or "")

    def join_via_live_invite(
        self, invitee_xuid: str, guild_id: int, inviter_xuid: str
    ) -> GuildResult:
        """在线邀请：被邀请者点接受后直接入会，不写入 guild_invites。"""
        invitee_xuid = str(invitee_xuid).strip()
        inviter_xuid = str(inviter_xuid).strip()
        if not invitee_xuid or not inviter_xuid:
            return False, "GUILD_INVALID_PLAYER"
        if invitee_xuid == inviter_xuid:
            return False, "GUILD_CANNOT_INVITE_SELF"
        if not self.get_guild(guild_id):
            return False, "GUILD_NOT_FOUND"
        role = self._actor_role(inviter_xuid, int(guild_id))
        if role not in (ROLE_OWNER, ROLE_MANAGER):
            return False, "GUILD_NO_PERMISSION"
        if self.get_membership(invitee_xuid):
            return False, "GUILD_ALREADY_IN_GUILD"
        if self.is_guild_full(int(guild_id)):
            return False, "GUILD_FULL"
        return self.add_guild_member(int(guild_id), invitee_xuid, ROLE_MEMBER)

    def accept_invite(self, invitee_xuid: str, invite_id: int) -> GuildResult:
        invitee_xuid = str(invitee_xuid).strip()
        inv = self.get_invite(invite_id)
        if not inv:
            return False, "GUILD_NO_INVITE"
        if str(inv.get("invitee_xuid") or "").strip() != invitee_xuid:
            return False, "GUILD_NO_INVITE"

        if self.get_membership(invitee_xuid):
            self.db.delete("guild_invites", "id = ?", (int(invite_id),))
            return False, "GUILD_ALREADY_IN_GUILD"

        gid = int(inv["guild_id"])
        if self.is_guild_full(gid):
            return False, "GUILD_FULL"
        ok, err = self.add_guild_member(gid, invitee_xuid, ROLE_MEMBER)
        if not ok:
            return False, err
        return True, None

    def decline_invite(self, invitee_xuid: str, invite_id: int) -> GuildResult:
        invitee_xuid = str(invitee_xuid).strip()
        inv = self.get_invite(invite_id)
        if not inv:
            return False, "GUILD_NO_INVITE"
        if str(inv.get("invitee_xuid") or "").strip() != invitee_xuid:
            return False, "GUILD_NO_INVITE"
        self.db.delete("guild_invites", "id = ?", (int(invite_id),))
        return True, None

    def kick(self, actor_xuid: str, target_xuid: str) -> GuildResult:
        actor_xuid = str(actor_xuid).strip()
        target_xuid = str(target_xuid).strip()
        if not actor_xuid or not target_xuid:
            return False, "GUILD_INVALID_PLAYER"
        if actor_xuid == target_xuid:
            return False, "GUILD_CANNOT_KICK_SELF"

        a_mem = self.get_membership(actor_xuid)
        t_mem = self.get_membership(target_xuid)
        if not a_mem or not t_mem:
            return False, "GUILD_NOT_IN_GUILD"
        if int(a_mem["guild_id"]) != int(t_mem["guild_id"]):
            return False, "GUILD_NOT_SAME_GUILD"

        gid = int(a_mem["guild_id"])
        a_role = a_mem.get("role")
        t_role = t_mem.get("role")

        if t_role == ROLE_OWNER:
            return False, "GUILD_CANNOT_KICK_OWNER"

        if a_role == ROLE_OWNER:
            pass
        elif a_role == ROLE_MANAGER:
            if t_role != ROLE_MEMBER:
                return False, "GUILD_NO_PERMISSION"
        else:
            return False, "GUILD_NO_PERMISSION"

        if self.db.delete(
            "guild_members",
            "guild_id = ? AND xuid = ?",
            (gid, target_xuid),
        ):
            self.db.delete("guild_invites", "invitee_xuid = ?", (target_xuid,))
            return True, None
        return False, "GUILD_DB_ERROR"

    def set_role(self, actor_xuid: str, target_xuid: str, new_role: str) -> GuildResult:
        actor_xuid = str(actor_xuid).strip()
        target_xuid = str(target_xuid).strip()
        new_role = str(new_role).strip().lower()
        if new_role not in (ROLE_MANAGER, ROLE_MEMBER):
            return False, "GUILD_INVALID_ROLE"

        a_mem = self.get_membership(actor_xuid)
        t_mem = self.get_membership(target_xuid)
        if not a_mem or not t_mem:
            return False, "GUILD_NOT_IN_GUILD"
        if int(a_mem["guild_id"]) != int(t_mem["guild_id"]):
            return False, "GUILD_NOT_SAME_GUILD"

        if a_mem.get("role") != ROLE_OWNER:
            return False, "GUILD_NO_PERMISSION"

        if t_mem.get("role") == ROLE_OWNER:
            return False, "GUILD_CANNOT_CHANGE_OWNER_ROLE"

        ok = self.db.update(
            "guild_members",
            {"role": new_role},
            "guild_id = ? AND xuid = ?",
            (int(a_mem["guild_id"]), target_xuid),
        )
        return (True, None) if ok else (False, "GUILD_DB_ERROR")

    def leave(self, xuid: str) -> GuildResult:
        xuid = str(xuid).strip()
        mem = self.get_membership(xuid)
        if not mem:
            return False, "GUILD_NOT_IN_GUILD"
        if mem.get("role") == ROLE_OWNER:
            return False, "GUILD_OWNER_MUST_DISBAND"
        gid = int(mem["guild_id"])
        if self.db.delete("guild_members", "guild_id = ? AND xuid = ?", (gid, xuid)):
            self.db.delete("guild_invites", "invitee_xuid = ?", (xuid,))
            return True, None
        return False, "GUILD_DB_ERROR"

    def disband(self, owner_xuid: str) -> GuildResult:
        owner_xuid = str(owner_xuid).strip()
        mem = self.get_membership(owner_xuid)
        if not mem or mem.get("role") != ROLE_OWNER:
            return False, "GUILD_NOT_OWNER"
        gid = int(mem["guild_id"])
        g = self.get_guild(gid)
        if not g:
            return False, "GUILD_NOT_FOUND"
        if str(g.get("owner_xuid") or "").strip() != owner_xuid:
            return False, "GUILD_NOT_OWNER"

        self.db.delete("guild_invites", "guild_id = ?", (gid,))
        self.db.delete("guild_join_requests", "guild_id = ?", (gid,))
        self.db.delete("guild_members", "guild_id = ?", (gid,))
        if self.db.delete("guilds", "id = ?", (gid,)):
            return True, None
        return False, "GUILD_DB_ERROR"

    def rename_guild(
        self, actor_xuid: str, new_name: str
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        会长改名公会。
        - 仅会长可执行
        - 新名先经过 _validate_guild_name（限长、禁止 §、禁止 [ ] "）
        - 新名不能与现名相同；不能与其它公会重名
        - 若 GUILD_RENAME_COST > 0，会从会长账户扣款；扣款失败回滚
        :return: (ok, error_code, info)
                 info = {'guild_id': int, 'old_name': str, 'new_name': str, 'cost': float}
        """
        info: Dict[str, Any] = {
            "guild_id": 0,
            "old_name": "",
            "new_name": "",
            "cost": 0.0,
        }
        actor = str(actor_xuid or "").strip()
        if not actor:
            return False, "GUILD_INVALID_PLAYER", info

        n, name_err = self._validate_guild_name(new_name)
        if not n:
            return False, name_err or "GUILD_INVALID_NAME", info

        mem = self.get_membership(actor)
        if not mem:
            return False, "GUILD_NOT_IN_GUILD", info
        if str(mem.get("role") or "") != ROLE_OWNER:
            return False, "GUILD_NOT_OWNER", info

        gid = int(mem.get("guild_id") or 0)
        if gid <= 0:
            return False, "GUILD_NOT_FOUND", info
        g = self.get_guild(gid)
        if not g:
            return False, "GUILD_NOT_FOUND", info

        old_name = strip_mc_color_codes(g.get("name") or "").strip()
        info["guild_id"] = gid
        info["old_name"] = old_name
        info["new_name"] = n

        # 改回相同名字（去色后一致）拒绝，避免无意义扣款
        if n == old_name:
            return False, "GUILD_RENAME_SAME_NAME", info

        # 重名检测（用净化后的名字精确匹配）
        existing = self.get_guild_by_name(n)
        if existing and int(existing.get("id") or 0) != gid:
            return False, "GUILD_NAME_TAKEN", info

        cost = self.economy.round_money(self.get_rename_cost())
        info["cost"] = float(cost)
        if cost > 0:
            if not self.economy.judge_if_player_has_enough_money_by_xuid(actor, cost):
                return False, "GUILD_NOT_ENOUGH_MONEY", info
            if not self.economy.decrease_player_money_by_xuid(actor, cost):
                return False, "GUILD_NOT_ENOUGH_MONEY", info

        ok = self.db.update("guilds", {"name": n}, "id = ?", (gid,))
        if not ok:
            if cost > 0:
                # 回滚扣款
                try:
                    self.economy.increase_player_money_by_xuid(actor, cost)
                except Exception:
                    pass
            return False, "GUILD_DB_ERROR", info
        return True, None, info
