# -*- coding: utf-8 -*-
"""条件类头衔：资格由外部查询决定，易主时 revoke/grant；持有者不变则不碰佩戴。"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Protocol


class ConditionalTitleProvider(Protocol):
    """条件头衔提供者协议。"""

    @property
    def id(self) -> str:
        ...

    def get_title_name(self) -> str:
        ...

    def ensure_definition(self) -> None:
        ...

    def query_holder_xuid(self) -> Optional[str]:
        ...

    def get_title_rarity(self) -> str:
        ...


class ConditionalTitleManager:
    """条件头衔迁移管理：同持有者零 revoke；跨服计算权由 can_compute 门闩控制。"""

    def __init__(
        self,
        database_manager,
        title_system,
        *,
        can_compute: Callable[[], bool],
        find_online_by_xuid: Callable[[str], Any],
        update_name_tag: Callable[[Any], None],
        grant_unlock_reward: Optional[Callable[[Any, str], None]] = None,
    ):
        self.db = database_manager
        self.title_system = title_system
        self._can_compute = can_compute
        self._find_online = find_online_by_xuid
        self._update_name_tag = update_name_tag
        self._grant_unlock_reward = grant_unlock_reward
        self._providers: Dict[str, ConditionalTitleProvider] = {}
        self._holders: Dict[str, Optional[str]] = {}

    def ensure_tables(self) -> None:
        try:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS conditional_title_state ("
                "id TEXT PRIMARY KEY, holder_xuid TEXT NOT NULL DEFAULT '')"
            )
            self._migrate_richest_state_if_needed()
        except Exception:
            pass

    def _migrate_richest_state_if_needed(self) -> None:
        """将旧 richest_title_state 迁入 conditional_title_state，随后删除旧表。"""
        try:
            exists = self.db.query_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='richest_title_state'"
            )
            if not exists:
                return
            row = self.db.query_one(
                "SELECT v FROM richest_title_state WHERE k = 'current_xuid'"
            )
            v = (str(row.get("v")).strip() if row and row.get("v") is not None else "")
            self.db.execute(
                "INSERT OR IGNORE INTO conditional_title_state (id, holder_xuid) VALUES ('richest', ?)",
                (v,),
            )
            self.db.execute("DROP TABLE IF EXISTS richest_title_state")
        except Exception:
            pass

    def get_provider(self, provider_id: str) -> Optional[ConditionalTitleProvider]:
        pid = str(provider_id or "").strip()
        return self._providers.get(pid)

    def register(self, provider: ConditionalTitleProvider) -> None:
        pid = str(getattr(provider, "id", "") or "").strip()
        if not pid:
            return
        self._providers[pid] = provider
        if pid not in self._holders:
            self._holders[pid] = self._load_holder(pid)

    def get_holder_xuid(self, provider_id: str) -> Optional[str]:
        pid = str(provider_id or "").strip()
        if not pid:
            return None
        if pid in self._holders:
            return self._holders[pid]
        return self._load_holder(pid)

    def _load_holder(self, provider_id: str) -> Optional[str]:
        try:
            row = self.db.query_one(
                "SELECT holder_xuid FROM conditional_title_state WHERE id = ?",
                (provider_id,),
            )
            if not row:
                return None
            v = str(row.get("holder_xuid") or "").strip()
            return v if v else None
        except Exception:
            return None

    def _save_holder(self, provider_id: str, xuid: Optional[str]) -> None:
        v = (str(xuid).strip() if xuid else "")
        try:
            self.db.execute(
                "INSERT INTO conditional_title_state (id, holder_xuid) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET holder_xuid = excluded.holder_xuid",
                (provider_id, v),
            )
        except Exception:
            try:
                self.db.execute(
                    "INSERT OR REPLACE INTO conditional_title_state (id, holder_xuid) VALUES (?, ?)",
                    (provider_id, v),
                )
            except Exception:
                pass
        self._holders[provider_id] = v if v else None

    def refresh(self, provider_id: str) -> None:
        if not self._can_compute():
            return
        pid = str(provider_id or "").strip()
        provider = self._providers.get(pid)
        if provider is None:
            return
        self._migrate(provider)

    def refresh_all(self) -> None:
        if not self._can_compute():
            return
        for provider in list(self._providers.values()):
            try:
                self._migrate(provider)
            except Exception:
                pass

    def _provider_rarity(self, provider: ConditionalTitleProvider, title: str) -> str:
        fn = getattr(provider, "get_title_rarity", None)
        if callable(fn):
            try:
                raw = fn()
                if raw is not None and str(raw).strip():
                    return str(raw).strip()
            except Exception:
                pass
        try:
            return self.title_system.preferred_grant_rarity(title)
        except Exception:
            return "普通"

    def _ensure_holder_has_rarity(self, xuid: str, title: str, rarity: str) -> None:
        """确保持有者解锁正确稀有度；若正佩戴同名错误稀有度则升级。"""
        self.title_system.unlock_title_by_xuid(xuid, title, rarity=rarity)
        equipped = None
        try:
            equipped = self.title_system.get_equipped_title_by_xuid(xuid)
        except Exception:
            equipped = None
        if equipped and equipped.get("title") == title and equipped.get("rarity") != rarity:
            self.title_system.set_equipped_title_by_xuid(xuid, title, rarity)
        try:
            canonical_rank = self.title_system.rarity_rank(rarity)
            for defn in self.title_system.list_title_definitions_by_name(title):
                alt = str(defn.get("rarity") or "").strip()
                if not alt or alt == rarity:
                    continue
                if self.title_system.rarity_rank(alt) < canonical_rank:
                    self.title_system.revoke_title_by_xuid(xuid, title, alt)
        except Exception:
            pass

    def _migrate(self, provider: ConditionalTitleProvider) -> None:
        title = (provider.get_title_name() or "").strip()
        if not title:
            return
        try:
            provider.ensure_definition()
        except Exception:
            pass

        pid = str(provider.id).strip()
        new_xuid = None
        try:
            raw = provider.query_holder_xuid()
            new_xuid = str(raw).strip() if raw else None
            if new_xuid == "":
                new_xuid = None
        except Exception:
            new_xuid = None

        old_xuid = self._holders.get(pid)
        if old_xuid is None and pid not in self._holders:
            old_xuid = self._load_holder(pid)
            self._holders[pid] = old_xuid

        rarity = self._provider_rarity(provider, title)

        if new_xuid == old_xuid:
            if new_xuid:
                try:
                    self._ensure_holder_has_rarity(new_xuid, title, rarity)
                except Exception:
                    pass
            return

        if old_xuid:
            self._revoke_from_holder(old_xuid, title)

        if new_xuid:
            self._grant_to_holder(new_xuid, title, rarity)

        self._save_holder(pid, new_xuid)

    def _revoke_from_holder(self, xuid: str, title: str) -> None:
        was_equipped = False
        try:
            _, was_equipped = self.title_system.revoke_title_by_xuid(xuid, title)
        except Exception:
            was_equipped = False

        if was_equipped:
            try:
                unlocked = [
                    t
                    for t in self.title_system.get_unlocked_titles_by_xuid(xuid)
                    if t and t != title
                ]
                fallback = self.title_system.pick_highest_rarity_title(unlocked)
                if fallback:
                    self.title_system.set_equipped_title_by_xuid(xuid, fallback)
            except Exception:
                pass

        online = None
        try:
            online = self._find_online(xuid)
        except Exception:
            online = None
        if online is not None:
            try:
                self._update_name_tag(online)
            except Exception:
                pass

    def _grant_to_holder(self, xuid: str, title: str, rarity: str) -> None:
        equipped_before = None
        try:
            equipped_before = self.title_system.get_equipped_title_by_xuid(xuid)
        except Exception:
            equipped_before = None

        was_new = False
        try:
            _, was_new = self.title_system.unlock_title_by_xuid(xuid, title, rarity=rarity)
        except Exception:
            return

        online = None
        try:
            online = self._find_online(xuid)
        except Exception:
            online = None

        if was_new and online is not None and self._grant_unlock_reward is not None:
            try:
                self._grant_unlock_reward(online, title)
            except Exception:
                pass

        # 新持有者当前无佩戴 → 自动佩戴；已戴其它头衔则不覆盖
        if not equipped_before:
            try:
                self.title_system.set_equipped_title_by_xuid(xuid, title, rarity)
            except Exception:
                pass

        if online is not None:
            try:
                self._update_name_tag(online)
            except Exception:
                pass


class RichestTitleProvider:
    """财富榜第一 → 首富条件头衔。"""

    id = "richest"

    def __init__(
        self,
        database_manager,
        title_system,
        *,
        get_title_name: Callable[[], str],
        hide_op_in_ranking: Callable[[], bool],
    ):
        self.db = database_manager
        self.title_system = title_system
        self._get_title_name = get_title_name
        self._hide_op = hide_op_in_ranking

    def get_title_name(self) -> str:
        name = (self._get_title_name() or "").strip()
        return name if name else "首富"

    def ensure_definition(self) -> None:
        self.title_system.set_title_definition(
            self.get_title_name(),
            "传奇",
            "服务器里最富有玩家",
            0.0,
            [],
        )

    def get_title_rarity(self) -> str:
        return "传奇"

    def query_holder_xuid(self) -> Optional[str]:
        """按金钱降序、xuid 升序取唯一榜一（同分稳定）。

        隐藏 OP 时 JOIN 跨服表 player_basic_info.once_op（曾以 OP 登录过即排除），
        不依赖本服独有的 player_local_info。
        """
        try:
            if self._hide_op():
                row = self.db.query_one(
                    "SELECT e.xuid, e.money "
                    "FROM player_economy e "
                    "LEFT JOIN player_basic_info b ON e.xuid = b.xuid "
                    "WHERE (b.once_op IS NULL OR b.once_op = 0) "
                    "ORDER BY e.money DESC, e.xuid ASC LIMIT 1"
                )
            else:
                row = self.db.query_one(
                    "SELECT xuid, money FROM player_economy "
                    "ORDER BY money DESC, xuid ASC LIMIT 1"
                )
            if not row or not row.get("xuid"):
                return None
            return str(row["xuid"]).strip() or None
        except Exception:
            return None
