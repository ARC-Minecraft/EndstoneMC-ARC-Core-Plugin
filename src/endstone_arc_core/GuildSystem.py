# -*- coding: utf-8 -*-
"""公会：建会扣费、职级、邀请、跨库路由下的 SQLite 表。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ROLE_OWNER = "owner"
ROLE_MANAGER = "manager"
ROLE_MEMBER = "member"

# (ok, error_code) 错误码供语言文件映射
GuildResult = Tuple[bool, Optional[str]]


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

    def ensure_tables(self) -> bool:
        try:
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS guilds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    owner_xuid TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    motto TEXT DEFAULT ''
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
            return True
        except Exception:
            return False

    @staticmethod
    def _normalize_guild_name(name: str) -> Optional[str]:
        if name is None:
            return None
        s = str(name).strip()
        if not s:
            return None
        if len(s) > 32:
            return None
        return s

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
        return dict(row) if row else None

    def get_guild_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        n = self._normalize_guild_name(name)
        if not n:
            return None
        row = self.db.query_one("SELECT * FROM guilds WHERE name = ?", (n,))
        return dict(row) if row else None

    def list_members(self, guild_id: int) -> List[Dict[str, Any]]:
        return self.db.query_all(
            "SELECT guild_id, xuid, role, joined_at FROM guild_members WHERE guild_id = ? ORDER BY role, xuid",
            (int(guild_id),),
        )

    def list_invites_for_player(self, invitee_xuid: str) -> List[Dict[str, Any]]:
        invitee_xuid = str(invitee_xuid).strip()
        if not invitee_xuid:
            return []
        return self.db.query_all(
            """
            SELECT i.id AS invite_id, i.guild_id, i.inviter_xuid, i.created_at, g.name AS guild_name
            FROM guild_invites i
            JOIN guilds g ON g.id = i.guild_id
            WHERE i.invitee_xuid = ?
            ORDER BY i.created_at DESC
            """,
            (invitee_xuid,),
        )

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
        n = self._normalize_guild_name(name)
        if not n:
            return False, "GUILD_INVALID_NAME"
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
        ts = self._now_iso()
        if self.db.insert(
            "guild_members",
            {
                "guild_id": int(guild_id),
                "xuid": invitee_xuid,
                "role": ROLE_MEMBER,
                "joined_at": ts,
            },
        ):
            return True, None
        return False, "GUILD_DB_ERROR"

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
        ts = self._now_iso()
        if not self.db.insert(
            "guild_members",
            {"guild_id": gid, "xuid": invitee_xuid, "role": ROLE_MEMBER, "joined_at": ts},
        ):
            return False, "GUILD_DB_ERROR"
        self.db.delete("guild_invites", "invitee_xuid = ?", (invitee_xuid,))
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
        self.db.delete("guild_members", "guild_id = ?", (gid,))
        if self.db.delete("guilds", "id = ?", (gid,)):
            return True, None
        return False, "GUILD_DB_ERROR"
