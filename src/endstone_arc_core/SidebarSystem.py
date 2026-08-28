# -*- coding: utf-8 -*-
"""弧光核心侧边栏总控：多页面注册、键值对模板、定时翻页、每玩家独立计分板。"""
from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from endstone import Player
from endstone.scoreboard import Criteria, DisplaySlot, ObjectiveSortOrder

try:
    from endstone.attribute import Attribute
except ImportError:
    try:
        from endstone import Attribute  # type: ignore
    except ImportError:
        Attribute = None  # type: ignore

MAIN_PAGE_ID = "arc_core_main"
PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

DEFAULT_MAIN_LINES = [
    "§8----------",
    "§7当前时间：§f{time}",
    "§7性能：§6TPS §f{tps}",
    "§7在线：§f{online}§8/§f{max_players}",
    "§7延迟：§f{ping}§8ms",
    "§7金钱：§f{money}",
    "§8----------",
]


def _setting_bool(raw: Any, default: bool = True) -> bool:
    if raw is None:
        return default
    return str(raw).strip().lower() in ("true", "1", "yes", "on")


def _setting_int(raw: Any, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


# 个人计分板上的稳定 objective 名（短于 Bedrock 16 字符上限）
_STABLE_OBJECTIVE = "arc_sb"
# 单人刷新周期默认：60 tick ≈ 3 秒
_DEFAULT_REFRESH_TICKS = 60
_DEFAULT_JOIN_DELAY_TICKS = 40  # 进服后延迟再写显示槽，避开未 spawn
_RENDER_RING_MAX = 32
_RENDER_STATE_FILE = Path("plugins/ARCCore/sidebar_render_state.txt")

# 侧边栏假名过长会踢客户端（历史包长上限约 40）
_MAX_ENTRY_LEN = 40


def _sanitize_entry_name(text: str) -> str:
    """去掉换行并截断，避免超长假名导致基岩端解码崩溃/踢线。"""
    s = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    if not s:
        s = " "
    if len(s) > _MAX_ENTRY_LEN:
        s = s[:_MAX_ENTRY_LEN]
    return s


def _unique_entry_name(text: str, used: Set[str]) -> str:
    """同一 objective 内 entry 名必须唯一；重复行追加不可见 §r。"""
    base = _sanitize_entry_name(text)
    name = base
    n = 0
    while name in used:
        n += 1
        suffix = "§r" * n
        keep = _MAX_ENTRY_LEN - len(suffix)
        if keep < 1:
            name = suffix[-_MAX_ENTRY_LEN :]
        else:
            name = base[:keep] + suffix
        name = _sanitize_entry_name(name)
    used.add(name)
    return name


@dataclass
class SidebarPage:
    page_id: str
    title: str
    lines: List[str]
    owner: str = ""
    priority: int = 0
    hide_line_if_missing: bool = True


@dataclass
class PlayerSidebarState:
    enabled: bool = True
    page_index: int = 0
    locked_page: str = ""
    last_switch_ts: float = 0.0
    # page_id -> False 表示对该玩家隐藏
    page_visible: Dict[str, bool] = field(default_factory=dict)
    scoreboard: Any = None
    current_objective_name: str = ""
    display_title: str = ""
    last_entries: Set[str] = field(default_factory=set)
    last_render_sig: str = ""
    display_set: bool = False
    join_at_mono: float = 0.0
    join_tick: int = 0


class SidebarSystem:
    def __init__(self, plugin):
        self.plugin = plugin
        self._pages: Dict[str, SidebarPage] = {}
        # xuid -> page_id -> key -> value
        self._values: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # page_id -> key -> value
        self._global_values: Dict[str, Dict[str, Any]] = {}
        self._player_state: Dict[str, PlayerSidebarState] = {}
        # xuid -> Scoreboard 强引用，避免 player_boards_ 被抹掉后 Python GC 析构原生对象
        self._boards: Dict[str, Any] = {}
        self._render_ring: deque = deque(maxlen=_RENDER_RING_MAX)
        self._render_open_xuid: str = ""
        # 低频缓存：定时器更新 time/tps/ping；事件更新 money/online
        self._cached_time: str = ""
        self._cached_date: str = ""
        self._cached_tps: Optional[float] = None
        self._cached_mspt: Optional[float] = None
        self._cached_online: int = 0
        self._cached_max_players: Optional[int] = None
        self._ping_cache: Dict[str, Optional[int]] = {}
        self._money_cache: Dict[str, str] = {}
        self._game_tick: int = 0
        self.enabled = True
        self.default_on = True
        self.sidebar_title = "§6弧光服务器"
        self.switch_interval = 10.0
        self.refresh_ticks = _DEFAULT_REFRESH_TICKS
        self.join_delay_ticks = _DEFAULT_JOIN_DELAY_TICKS
        self.max_lines = 15
        self.main_line_templates: List[str] = list(DEFAULT_MAIN_LINES)
        self.reload_config()
        self._ensure_main_page()
        self._check_stale_render_state()

    # ------------------------------------------------------------------ config
    def reload_config(self) -> None:
        sm = self.plugin.setting_manager
        self.enabled = _setting_bool(sm.GetSetting("SIDEBAR_ENABLE"), True)
        self.default_on = _setting_bool(sm.GetSetting("SIDEBAR_DEFAULT_ON"), True)
        title = sm.GetSetting("SIDEBAR_TITLE")
        # 旧默认标题迁移到灰橙配色
        if title is not None and str(title).strip() in (
            "§l§b弧 光 服 务 器",
            "§l§b弧光服务器",
            "§b弧 光 服 务 器",
            "§b弧光服务器",
            "§6弧 光 服 务 器",
        ):
            title = "§6弧光服务器"
            try:
                sm.SetSetting("SIDEBAR_TITLE", title)
            except Exception:
                pass
        self.sidebar_title = (
            str(title).replace("\\n", "\n") if title else "§6弧光服务器"
        )
        self.switch_interval = float(
            max(1, _setting_int(sm.GetSetting("SIDEBAR_SWITCH_INTERVAL"), 10))
        )
        refresh = max(1, _setting_int(sm.GetSetting("SIDEBAR_REFRESH_TICKS"), _DEFAULT_REFRESH_TICKS))
        self.refresh_ticks = refresh
        self.join_delay_ticks = max(
            0,
            _setting_int(
                sm.GetSetting("SIDEBAR_JOIN_DELAY_TICKS"), _DEFAULT_JOIN_DELAY_TICKS
            ),
        )
        self.max_lines = max(1, min(15, _setting_int(sm.GetSetting("SIDEBAR_MAX_LINES"), 15)))
        raw_lines = sm.GetSetting("SIDEBAR_MAIN_LINES")
        if raw_lines and str(raw_lines).strip():
            text = str(raw_lines).replace("\\n", "\n")
            parsed = [ln for ln in text.split("\n") if ln is not None]
            self.main_line_templates = parsed if parsed else list(DEFAULT_MAIN_LINES)
        else:
            self.main_line_templates = list(DEFAULT_MAIN_LINES)
        self._ensure_main_page()

    def _ensure_main_page(self) -> None:
        self._pages[MAIN_PAGE_ID] = SidebarPage(
            page_id=MAIN_PAGE_ID,
            title=self.sidebar_title,
            lines=list(self.main_line_templates),
            owner="arc_core",
            priority=-1000,
            hide_line_if_missing=True,
        )

    # ------------------------------------------------------------------ DB pref
    def init_pref_table(self) -> None:
        try:
            self.plugin.database_manager.execute(
                """
                CREATE TABLE IF NOT EXISTS player_sidebar_pref (
                    xuid TEXT PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    locked_page TEXT DEFAULT '',
                    updated_at TEXT
                )
                """
            )
        except Exception as e:
            self._log_error(f"init_pref_table: {e}")

    def _load_pref(self, xuid: str) -> Dict[str, Any]:
        try:
            row = self.plugin.database_manager.query_one(
                "SELECT enabled, locked_page FROM player_sidebar_pref WHERE xuid = ?",
                (xuid,),
            )
            if not row:
                return {
                    "enabled": self.default_on,
                    "locked_page": "",
                }
            return {
                "enabled": bool(int(row.get("enabled") if row.get("enabled") is not None else 1)),
                "locked_page": str(row.get("locked_page") or ""),
            }
        except Exception:
            return {"enabled": self.default_on, "locked_page": ""}

    def _save_pref(self, xuid: str, state: PlayerSidebarState) -> None:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            existing = self.plugin.database_manager.query_one(
                "SELECT xuid FROM player_sidebar_pref WHERE xuid = ?",
                (xuid,),
            )
            data = {
                "enabled": 1 if state.enabled else 0,
                "locked_page": state.locked_page or "",
                "updated_at": now,
            }
            if existing:
                self.plugin.database_manager.update(
                    "player_sidebar_pref", data, "xuid = ?", (xuid,)
                )
            else:
                data["xuid"] = xuid
                self.plugin.database_manager.insert("player_sidebar_pref", data)
        except Exception as e:
            self._log_error(f"save_pref {xuid}: {e}")

    # ------------------------------------------------------------------ pages API
    def register_page(
        self,
        page_id: str,
        title: str,
        lines: List[str],
        owner: str = "",
        priority: int = 0,
        hide_line_if_missing: bool = True,
    ) -> bool:
        try:
            pid = str(page_id or "").strip()
            if not pid:
                return False
            if pid == MAIN_PAGE_ID:
                # 主页面只允许改标题/行模板，不允许被覆盖所有者
                page = self._pages.get(MAIN_PAGE_ID)
                if page is None:
                    self._ensure_main_page()
                    page = self._pages[MAIN_PAGE_ID]
                if title:
                    page.title = str(title)
                if lines is not None:
                    page.lines = [str(x) for x in lines]
                page.hide_line_if_missing = bool(hide_line_if_missing)
                return True
            self._pages[pid] = SidebarPage(
                page_id=pid,
                title=str(title or pid),
                lines=[str(x) for x in (lines or [])],
                owner=str(owner or ""),
                priority=int(priority),
                hide_line_if_missing=bool(hide_line_if_missing),
            )
            return True
        except Exception as e:
            self._log_error(f"register_page: {e}")
            return False

    def unregister_page(self, page_id: str) -> bool:
        try:
            pid = str(page_id or "").strip()
            if not pid or pid == MAIN_PAGE_ID:
                return False
            if pid not in self._pages:
                return False
            del self._pages[pid]
            self._global_values.pop(pid, None)
            for xv in self._values.values():
                xv.pop(pid, None)
            for st in self._player_state.values():
                st.page_visible.pop(pid, None)
                if st.locked_page == pid:
                    st.locked_page = ""
            return True
        except Exception as e:
            self._log_error(f"unregister_page: {e}")
            return False

    def set_page_lines(self, page_id: str, lines: List[str]) -> bool:
        try:
            page = self._pages.get(str(page_id or "").strip())
            if page is None:
                return False
            page.lines = [str(x) for x in (lines or [])]
            if page.page_id == MAIN_PAGE_ID:
                self.main_line_templates = list(page.lines)
            return True
        except Exception as e:
            self._log_error(f"set_page_lines: {e}")
            return False

    def set_page_title(self, page_id: str, title: str) -> bool:
        try:
            page = self._pages.get(str(page_id or "").strip())
            if page is None:
                return False
            page.title = str(title or page.page_id)
            if page.page_id == MAIN_PAGE_ID:
                self.sidebar_title = page.title
            return True
        except Exception as e:
            self._log_error(f"set_page_title: {e}")
            return False

    def list_pages(self) -> List[Dict[str, Any]]:
        pages = sorted(
            self._pages.values(),
            key=lambda p: (p.priority, p.page_id),
        )
        return [
            {
                "page_id": p.page_id,
                "title": p.title,
                "owner": p.owner,
                "priority": p.priority,
                "line_count": len(p.lines),
                "hide_line_if_missing": p.hide_line_if_missing,
            }
            for p in pages
        ]

    # ------------------------------------------------------------------ values
    def set_value(
        self, page_id: str, key: str, value: Any, xuid: str = ""
    ) -> bool:
        try:
            pid = str(page_id or "").strip()
            k = str(key or "").strip()
            if not pid or not k:
                return False
            xs = str(xuid or "").strip()
            if xs:
                self._values.setdefault(xs, {}).setdefault(pid, {})[k] = value
            else:
                self._global_values.setdefault(pid, {})[k] = value
            return True
        except Exception as e:
            self._log_error(f"set_value: {e}")
            return False

    def set_values(
        self, page_id: str, values: Dict[str, Any], xuid: str = ""
    ) -> bool:
        try:
            if not isinstance(values, dict):
                return False
            pid = str(page_id or "").strip()
            xs = str(xuid or "").strip()
            ok = True
            for k, v in values.items():
                kk = str(k or "").strip()
                if not pid or not kk:
                    ok = False
                    continue
                if xs:
                    self._values.setdefault(xs, {}).setdefault(pid, {})[kk] = v
                else:
                    self._global_values.setdefault(pid, {})[kk] = v
            return ok
        except Exception as e:
            self._log_error(f"set_values: {e}")
            return False

    def get_value(
        self,
        page_id: str,
        key: str,
        xuid: str = "",
        default: Any = None,
    ) -> Any:
        try:
            pid = str(page_id or "").strip()
            k = str(key or "").strip()
            xs = str(xuid or "").strip()
            if xs:
                v = self._values.get(xs, {}).get(pid, {}).get(k)
                if v is not None:
                    return v
            v = self._global_values.get(pid, {}).get(k)
            return default if v is None else v
        except Exception:
            return default

    def clear_values(self, page_id: str, xuid: str = "") -> bool:
        try:
            pid = str(page_id or "").strip()
            xs = str(xuid or "").strip()
            if xs:
                if pid:
                    self._values.get(xs, {}).pop(pid, None)
                else:
                    self._values.pop(xs, None)
            else:
                if pid:
                    self._global_values.pop(pid, None)
            return True
        except Exception as e:
            self._log_error(f"clear_values: {e}")
            return False

    def set_global_value(self, page_id: str, key: str, value: Any) -> bool:
        return self.set_value(page_id, key, value, xuid="")

    def set_page_visible(self, page_id: str, visible: bool, xuid: str) -> bool:
        try:
            pid = str(page_id or "").strip()
            xs = str(xuid or "").strip()
            if not pid or not xs or pid == MAIN_PAGE_ID:
                return False
            st = self._player_state.get(xs)
            if st is None:
                st = PlayerSidebarState(enabled=self.default_on)
                self._player_state[xs] = st
            st.page_visible[pid] = bool(visible)
            return True
        except Exception as e:
            self._log_error(f"set_page_visible: {e}")
            return False

    # ------------------------------------------------------------------ player lifecycle
    def on_player_join(self, player: Player) -> None:
        if not self.enabled or player is None:
            return
        try:
            xuid = str(getattr(player, "xuid", "") or "").strip()
            if not xuid:
                return
            pref = self._load_pref(xuid)
            st = PlayerSidebarState(
                enabled=bool(pref.get("enabled", self.default_on)),
                locked_page=str(pref.get("locked_page") or ""),
                last_switch_ts=time.time(),
                join_at_mono=time.monotonic(),
                join_tick=int(self._game_tick),
            )
            self._player_state[xuid] = st
            self._seed_money_cache(xuid)
            self._update_online_cache()
            if st.enabled:
                # 不在 join 同帧写显示槽；等 SIDEBAR_JOIN_DELAY_TICKS 后再绑看板
                delay = max(1, int(self.join_delay_ticks))

                def _later() -> None:
                    try:
                        p = self._find_online(xuid)
                        if p is None:
                            return
                        st2 = self._player_state.get(xuid)
                        if st2 is None or not st2.enabled:
                            return
                        if not self._is_render_ready(p):
                            return
                        self._ensure_player_scoreboard(p, st2)
                        self.refresh_player(p, force=True)
                    except Exception as e:
                        self._log_error(f"join_delayed_render: {e}")

                try:
                    self.plugin.server.scheduler.run_task(
                        self.plugin, _later, delay=delay
                    )
                except Exception:
                    self._run_on_main(_later)
        except Exception as e:
            self._log_error(f"on_player_join: {e}")

    def on_player_quit(self, player: Player) -> None:
        try:
            xuid = str(getattr(player, "xuid", "") or "").strip()
            if not xuid:
                return
            st = self._player_state.get(xuid)
            if st is not None:
                self._release_player_board(player, st, xuid)
            self._player_state.pop(xuid, None)
            self._values.pop(xuid, None)
            self._ping_cache.pop(xuid, None)
            self._money_cache.pop(xuid, None)
            self._update_online_cache()
        except Exception as e:
            self._log_error(f"on_player_quit: {e}")

    def shutdown(self) -> None:
        try:
            if self._render_open_xuid:
                self._log_warn(
                    f"shutdown with unclosed render xuid={self._render_open_xuid}"
                )
            for player in list(getattr(self.plugin.server, "online_players", []) or []):
                xuid = str(getattr(player, "xuid", "") or "").strip()
                st = self._player_state.get(xuid)
                if st is not None:
                    self._release_player_board(player, st, xuid)
            self._player_state.clear()
            self._boards.clear()
            self._mark_render_exit(self._render_open_xuid)
        except Exception as e:
            self._log_error(f"shutdown: {e}")

    # ------------------------------------------------------------------ commands helpers
    def set_enabled(self, player: Player, enabled: bool) -> bool:
        try:
            xuid = str(getattr(player, "xuid", "") or "").strip()
            if not xuid:
                return False
            st = self._ensure_state(xuid)
            st.enabled = bool(enabled)
            self._save_pref(xuid, st)
            if st.enabled:
                self._ensure_player_scoreboard(player, st)
                self.refresh_player(player, force=True)
            else:
                self._hide_sidebar_display(st)
            return True
        except Exception as e:
            self._log_error(f"set_enabled: {e}")
            return False

    def toggle_enabled(self, player: Player) -> bool:
        xuid = str(getattr(player, "xuid", "") or "").strip()
        st = self._ensure_state(xuid) if xuid else None
        cur = bool(st.enabled) if st else self.default_on
        return self.set_enabled(player, not cur)

    def is_enabled_for(self, player: Player) -> bool:
        xuid = str(getattr(player, "xuid", "") or "").strip()
        st = self._player_state.get(xuid)
        if st is None:
            return self.default_on
        return bool(st.enabled)

    def flip_page(self, player: Player, delta: int) -> Optional[SidebarPage]:
        try:
            xuid = str(getattr(player, "xuid", "") or "").strip()
            if not xuid:
                return None
            st = self._ensure_state(xuid)
            pages = self._visible_pages_for(xuid)
            if not pages:
                return None
            if st.locked_page:
                st.locked_page = ""
                self._save_pref(xuid, st)
            st.page_index = (st.page_index + int(delta)) % len(pages)
            st.last_switch_ts = time.time()
            self.refresh_player(player, force=True)
            return pages[st.page_index]
        except Exception as e:
            self._log_error(f"flip_page: {e}")
            return None

    def lock_page(self, player: Player, page_ref: str = "") -> Optional[SidebarPage]:
        try:
            xuid = str(getattr(player, "xuid", "") or "").strip()
            if not xuid:
                return None
            st = self._ensure_state(xuid)
            pages = self._visible_pages_for(xuid)
            if not pages:
                return None
            target: Optional[SidebarPage] = None
            ref = str(page_ref or "").strip()
            if ref:
                if ref.isdigit():
                    idx = int(ref) - 1
                    if 0 <= idx < len(pages):
                        target = pages[idx]
                else:
                    for p in pages:
                        if p.page_id == ref:
                            target = p
                            break
            if target is None:
                idx = st.page_index % len(pages)
                target = pages[idx]
            st.locked_page = target.page_id
            # 同步 page_index
            for i, p in enumerate(pages):
                if p.page_id == target.page_id:
                    st.page_index = i
                    break
            self._save_pref(xuid, st)
            self.refresh_player(player, force=True)
            return target
        except Exception as e:
            self._log_error(f"lock_page: {e}")
            return None

    def unlock_page(self, player: Player) -> bool:
        try:
            xuid = str(getattr(player, "xuid", "") or "").strip()
            if not xuid:
                return False
            st = self._ensure_state(xuid)
            st.locked_page = ""
            st.last_switch_ts = time.time()
            self._save_pref(xuid, st)
            return True
        except Exception as e:
            self._log_error(f"unlock_page: {e}")
            return False

    def get_visible_pages_for_player(self, player: Player) -> List[SidebarPage]:
        xuid = str(getattr(player, "xuid", "") or "").strip()
        return self._visible_pages_for(xuid)

    def get_current_page(self, player: Player) -> Optional[SidebarPage]:
        xuid = str(getattr(player, "xuid", "") or "").strip()
        pages = self._visible_pages_for(xuid)
        if not pages:
            return None
        st = self._player_state.get(xuid)
        if st and st.locked_page:
            for p in pages:
                if p.page_id == st.locked_page:
                    return p
        idx = (st.page_index if st else 0) % len(pages)
        return pages[idx]

    # ------------------------------------------------------------------ tick / render
    def tick(self) -> None:
        """每游戏 tick 调用；按进服 tick 错峰，仅刷新到期玩家。"""
        if not self.enabled:
            return
        try:
            self._game_tick += 1
            rt = max(1, int(self.refresh_ticks))
            delay = max(0, int(self.join_delay_ticks))
            if self._game_tick % rt == 0:
                self._refresh_timed_cache()
            now = time.time()
            for player in list(getattr(self.plugin.server, "online_players", []) or []):
                try:
                    xuid = str(getattr(player, "xuid", "") or "").strip()
                    if not xuid:
                        continue
                    st = self._player_state.get(xuid)
                    if st is None or not st.enabled:
                        continue
                    if not self._is_render_ready(player):
                        continue
                    elapsed = self._game_tick - int(st.join_tick)
                    if elapsed < delay:
                        continue
                    if elapsed % rt != 0:
                        continue
                    self._tick_player(player, now)
                except Exception as e:
                    self._log_error(f"tick player: {e}")
        except Exception as e:
            self._log_error(f"tick: {e}")

    def notify_money_changed(self, xuid: str) -> None:
        """金钱变动：只更新缓存，等定时 tick 渲染。"""
        xs = str(xuid or "").strip()
        if not xs or not self.enabled:
            return
        try:
            self._seed_money_cache(xs)
        except Exception as e:
            self._log_error(f"notify_money_changed: {e}")

    def notify_online_changed(self) -> None:
        """在线人数变动：只更新缓存，等定时 tick 渲染。"""
        if not self.enabled:
            return
        try:
            self._update_online_cache()
        except Exception as e:
            self._log_error(f"notify_online_changed: {e}")

    def refresh(self, xuid: str = "") -> None:
        try:
            xs = str(xuid or "").strip()
            if xs:
                player = self._find_online(xs)
                if player is not None:
                    self.refresh_player(player, force=True)
                return
            for player in list(getattr(self.plugin.server, "online_players", []) or []):
                self.refresh_player(player, force=True)
        except Exception as e:
            self._log_error(f"refresh: {e}")

    def refresh_player(self, player: Player, force: bool = False) -> None:
        if not self.enabled or player is None:
            return
        xuid = str(getattr(player, "xuid", "") or "").strip()
        if not xuid:
            return
        st = self._ensure_state(xuid)
        if not self._is_render_ready(player):
            return
        if not st.enabled:
            self._hide_sidebar_display(st)
            return
        pages = self._visible_pages_for(xuid)
        if not pages:
            self._hide_sidebar_display(st)
            return
        page = self._resolve_current_page(st, pages)
        self._render_to_player(player, st, page, pages, force=force)

    def _tick_player(self, player: Player, now: float) -> None:
        xuid = str(getattr(player, "xuid", "") or "").strip()
        if not xuid:
            return
        st = self._player_state.get(xuid)
        if st is None:
            self.on_player_join(player)
            st = self._player_state.get(xuid)
            if st is None:
                return
        if not self._is_render_ready(player):
            return
        if not st.enabled:
            return
        pages = self._visible_pages_for(xuid)
        if not pages:
            self._hide_sidebar_display(st)
            return
        # 每人延迟随定时器取样；金钱顺带从库重读（跨服共享库无本地事件时兜底）
        self._sample_player_ping(player, xuid)
        self._seed_money_cache(xuid)
        if not st.locked_page and len(pages) >= 2:
            if now - st.last_switch_ts >= self.switch_interval:
                st.page_index = (st.page_index + 1) % len(pages)
                st.last_switch_ts = now
        self.refresh_player(player, force=False)

    def _resolve_current_page(
        self, st: PlayerSidebarState, pages: List[SidebarPage]
    ) -> SidebarPage:
        if st.locked_page:
            for p in pages:
                if p.page_id == st.locked_page:
                    return p
            # 锁定页已不可见，解除锁定
            st.locked_page = ""
        if st.page_index < 0 or st.page_index >= len(pages):
            st.page_index = 0
        return pages[st.page_index]

    def _visible_pages_for(self, xuid: str) -> List[SidebarPage]:
        st = self._player_state.get(xuid)
        pages = list(self._pages.values())
        pages.sort(key=lambda p: (p.priority, p.page_id))
        result: List[SidebarPage] = []
        for p in pages:
            if st is not None and p.page_id in st.page_visible:
                if not st.page_visible[p.page_id]:
                    continue
            result.append(p)
        return result

    def _ensure_state(self, xuid: str) -> PlayerSidebarState:
        st = self._player_state.get(xuid)
        if st is None:
            pref = self._load_pref(xuid)
            st = PlayerSidebarState(
                enabled=bool(pref.get("enabled", self.default_on)),
                locked_page=str(pref.get("locked_page") or ""),
                last_switch_ts=time.time(),
                join_tick=int(self._game_tick),
            )
            self._player_state[xuid] = st
        return st

    def _ensure_player_scoreboard(self, player: Player, st: PlayerSidebarState) -> Any:
        xuid = str(getattr(player, "xuid", "") or "").strip()
        sb = st.scoreboard
        if sb is None and xuid:
            sb = self._boards.get(xuid)
            if sb is not None:
                st.scoreboard = sb
        if sb is not None:
            if xuid:
                self._boards[xuid] = sb
            try:
                player.scoreboard = sb
            except Exception:
                pass
            return sb
        try:
            sb = self.plugin.server.create_scoreboard()
            st.scoreboard = sb
            if xuid:
                self._boards[xuid] = sb
            player.scoreboard = sb
            return sb
        except Exception as e:
            self._log_error(f"create_scoreboard: {e}")
            return None

    def _hide_sidebar_display(self, st: PlayerSidebarState) -> None:
        """关掉显示槽但不销毁看板/objective（/sidebar off、无可见页）。"""
        sb = st.scoreboard
        if sb is not None:
            try:
                sb.clear_slot(DisplaySlot.SIDE_BAR)
            except Exception:
                pass
        st.display_set = False
        st.last_render_sig = ""

    def _release_player_board(
        self, player: Optional[Player], st: PlayerSidebarState, xuid: str
    ) -> None:
        """仅下线/shutdown：先交还主计分板，再丢掉 Python 强引用。"""
        try:
            primary = self.plugin.server.scoreboard
            if primary is not None and player is not None:
                player.scoreboard = primary
        except Exception:
            pass
        sb = st.scoreboard or (self._boards.get(xuid) if xuid else None)
        if sb is not None:
            try:
                sb.clear_slot(DisplaySlot.SIDE_BAR)
            except Exception:
                pass
        st.scoreboard = None
        st.current_objective_name = ""
        st.display_title = ""
        st.last_entries = set()
        st.last_render_sig = ""
        st.display_set = False
        if xuid:
            self._boards.pop(xuid, None)

    def _dummy_criteria(self):
        criteria = getattr(Criteria, "DUMMY", None)
        if criteria is None:
            criteria = Criteria.Type.DUMMY  # type: ignore[attr-defined]
        return criteria

    def _reset_score_entry(self, sb: Any, obj: Any, entry: str) -> bool:
        """尽量从 objective 上移除一行；失败返回 False。"""
        try:
            sc = obj.get_score(entry)
            reset = getattr(sc, "reset", None)
            if callable(reset):
                reset()
                return True
        except Exception:
            pass
        try:
            rs = getattr(sb, "reset_scores", None)
            if callable(rs):
                rs(entry)
                return True
        except Exception:
            pass
        return False

    def _get_or_create_objective(
        self, sb: Any, st: PlayerSidebarState, display_title: str
    ) -> Any:
        """复用稳定 objective；标题变化只改 display_name，不 unregister。"""
        title = _sanitize_entry_name(display_title)[:32] or " "
        obj_name = _STABLE_OBJECTIVE
        obj = None
        try:
            obj = sb.get_objective(obj_name)
        except Exception:
            obj = None

        if obj is not None:
            if st.display_title != title:
                try:
                    obj.display_name = title
                except Exception as e:
                    self._log_error(f"set display_name: {e}")
                st.display_title = title
            st.current_objective_name = obj_name
            return obj

        if st.current_objective_name and st.current_objective_name != obj_name:
            try:
                old2 = sb.get_objective(st.current_objective_name)
                if old2 is not None:
                    old2.unregister()
            except Exception:
                pass
            st.display_set = False

        try:
            obj = sb.add_objective(obj_name, self._dummy_criteria(), title)
        except Exception as e:
            try:
                obj = sb.get_objective(obj_name)
            except Exception:
                obj = None
            if obj is None:
                self._log_error(f"add_objective: {e}")
                return None
        st.current_objective_name = obj_name
        st.display_title = title
        st.last_entries = set()
        st.display_set = False
        return obj

    def _rebuild_objective(
        self, sb: Any, st: PlayerSidebarState, display_title: str
    ) -> Any:
        """无法逐条删行时：先 clear_slot，再重建 objective。"""
        try:
            sb.clear_slot(DisplaySlot.SIDE_BAR)
        except Exception:
            pass
        st.display_set = False
        obj_name = st.current_objective_name or _STABLE_OBJECTIVE
        try:
            old = sb.get_objective(obj_name)
            if old is not None:
                old.unregister()
        except Exception:
            pass
        st.current_objective_name = ""
        st.display_title = ""
        st.last_entries = set()
        return self._get_or_create_objective(sb, st, display_title)

    def _ensure_display_slot(self, obj: Any, st: PlayerSidebarState) -> None:
        """每个 objective 生命周期只调一次 set_display；用 is_displayed 兜底校正。"""
        need = not st.display_set
        if not need:
            try:
                displayed = getattr(obj, "is_displayed", None)
                if callable(displayed):
                    displayed = displayed()
                if displayed is False:
                    need = True
            except Exception:
                pass
            if not need:
                try:
                    slot = getattr(obj, "display_slot", None)
                    if slot is not None and slot != DisplaySlot.SIDE_BAR:
                        need = True
                except Exception:
                    pass
        if not need:
            return
        try:
            obj.set_display(DisplaySlot.SIDE_BAR, ObjectiveSortOrder.DESCENDING)
            st.display_set = True
        except Exception as e:
            self._log_error(f"set_display: {e}")
            st.display_set = False

    def _render_to_player(
        self,
        player: Player,
        st: PlayerSidebarState,
        page: SidebarPage,
        pages: List[SidebarPage],
        force: bool = False,
    ) -> None:
        if not self._is_render_ready(player):
            return
        xuid = str(getattr(player, "xuid", "") or "").strip()
        rendered = self._render_lines(page, player, xuid, pages, st)
        display_title = self._render_text(
            page.title or self.sidebar_title, page, player, xuid, pages, st
        )
        sig = display_title + "\n" + "\n".join(rendered)
        if not force and sig == st.last_render_sig:
            return

        sb = self._ensure_player_scoreboard(player, st)
        if sb is None:
            return

        used: Set[str] = set()
        entries: List[str] = []
        for line in rendered[: self.max_lines]:
            entries.append(_unique_entry_name(line, used))
        if not entries:
            entries = [" "]

        self._mark_render_enter(xuid)
        try:
            obj = self._get_or_create_objective(sb, st, display_title)
            if obj is None:
                return

            new_set = set(entries)
            for old_entry in list(st.last_entries - new_set):
                if not self._reset_score_entry(sb, obj, old_entry):
                    obj = self._rebuild_objective(sb, st, display_title)
                    if obj is None:
                        return
                    st.last_entries = set()
                    break

            score_base = max(len(entries), 1)
            for i, entry in enumerate(entries):
                sc = obj.get_score(entry)
                sc.value = score_base - i

            self._ensure_display_slot(obj, st)

            st.last_entries = new_set
            st.last_render_sig = sig
        except Exception as e:
            self._log_error(f"render_to_player: {e}")
        finally:
            self._mark_render_exit(xuid)

    def _render_lines(
        self,
        page: SidebarPage,
        player: Player,
        xuid: str,
        pages: List[SidebarPage],
        st: PlayerSidebarState,
    ) -> List[str]:
        out: List[str] = []
        for tmpl in page.lines:
            text, missing = self._render_text_with_missing(
                str(tmpl), page, player, xuid, pages, st
            )
            if missing and page.hide_line_if_missing:
                continue
            out.append(text if text else " ")
            if len(out) >= self.max_lines:
                break
        if not out:
            out = [" "]
        return out

    def _render_text(
        self,
        template: str,
        page: SidebarPage,
        player: Player,
        xuid: str,
        pages: List[SidebarPage],
        st: PlayerSidebarState,
    ) -> str:
        text, _ = self._render_text_with_missing(
            template, page, player, xuid, pages, st
        )
        return text

    def _render_text_with_missing(
        self,
        template: str,
        page: SidebarPage,
        player: Player,
        xuid: str,
        pages: List[SidebarPage],
        st: PlayerSidebarState,
    ) -> tuple:
        missing = False
        builtins = self._builtin_vars(player, xuid, pages, st)

        def repl(m: re.Match) -> str:
            nonlocal missing
            key = m.group(1)
            # per-player → global → builtin
            if xuid and key in self._values.get(xuid, {}).get(page.page_id, {}):
                return str(self._values[xuid][page.page_id][key])
            if key in self._global_values.get(page.page_id, {}):
                return str(self._global_values[page.page_id][key])
            if key in builtins:
                val = builtins[key]
                if val is None:
                    missing = True
                    return ""
                return str(val)
            missing = True
            return ""

        return PLACEHOLDER_RE.sub(repl, template), missing

    def _run_on_main(self, fn) -> None:
        try:
            self.plugin.server.scheduler.run_task(self.plugin, fn)
        except Exception:
            try:
                fn()
            except Exception as e:
                self._log_error(f"run_on_main: {e}")

    def _schedule_refresh_xuid(self, xuid: str) -> None:
        xs = str(xuid or "").strip()
        if not xs:
            return

        def _run() -> None:
            player = self._find_online(xs)
            if player is None:
                return
            st = self._player_state.get(xs)
            if st is None or not st.enabled:
                return
            self.refresh_player(player, force=False)

        self._run_on_main(_run)

    def _schedule_refresh_all_enabled(self) -> None:
        self._run_on_main(lambda: self._refresh_all_enabled())

    def _refresh_all_enabled(self, exclude_xuid: str = "") -> None:
        ex = str(exclude_xuid or "").strip()
        for player in list(getattr(self.plugin.server, "online_players", []) or []):
            xuid = str(getattr(player, "xuid", "") or "").strip()
            if not xuid or xuid == ex:
                continue
            st = self._player_state.get(xuid)
            if st is None or not st.enabled:
                continue
            try:
                self.refresh_player(player, force=False)
            except Exception as e:
                self._log_error(f"refresh_all_enabled: {e}")

    def _update_online_cache(self) -> None:
        try:
            self._cached_online = len(
                list(getattr(self.plugin.server, "online_players", []) or [])
            )
        except Exception:
            self._cached_online = 0
        try:
            mp = getattr(self.plugin.server, "max_players", None)
            self._cached_max_players = int(mp) if mp is not None else None
        except Exception:
            self._cached_max_players = None

    def _refresh_timed_cache(self) -> None:
        """定时器专用：现实时间 + TPS/MSPT。"""
        now = datetime.now()
        self._cached_time = now.strftime("%H:%M")
        self._cached_date = now.strftime("%Y-%m-%d")
        tps = None
        mspt = None
        try:
            server = self.plugin.server
            if hasattr(server, "current_tps"):
                tps = round(float(server.current_tps), 1)
            elif hasattr(server, "average_tps"):
                tps = round(float(server.average_tps), 1)
        except Exception:
            tps = None
        try:
            server = self.plugin.server
            if hasattr(server, "current_mspt"):
                mspt = round(float(server.current_mspt), 1)
            elif hasattr(server, "average_mspt"):
                mspt = round(float(server.average_mspt), 1)
        except Exception:
            mspt = None
        self._cached_tps = tps
        self._cached_mspt = mspt

    def _seed_money_cache(self, xuid: str) -> None:
        xs = str(xuid or "").strip()
        if not xs:
            return
        try:
            money = self.plugin.economy.get_player_money_by_xuid(xs)
        except Exception:
            money = 0.0
        if isinstance(money, float):
            self._money_cache[xs] = (
                f"{money:.2f}".rstrip("0").rstrip(".")
            )
        else:
            self._money_cache[xs] = str(money)

    def _sample_player_ping(self, player: Player, xuid: str) -> Optional[int]:
        ping = None
        try:
            ping = max(0, int(getattr(player, "ping", None)))
        except Exception:
            ping = None
        self._ping_cache[xuid] = ping
        return ping

    def _builtin_vars(
        self,
        player: Player,
        xuid: str,
        pages: List[SidebarPage],
        st: PlayerSidebarState,
    ) -> Dict[str, Any]:
        # 金钱：缓存未命中时补一次（进服/事件应已写入）
        if xuid and xuid not in self._money_cache:
            self._seed_money_cache(xuid)
        money_str = self._money_cache.get(xuid, "0")

        # 生命/饱食仅在自定义模板仍引用时现场读取（默认模板已去掉）
        hp = None
        max_hp = None
        try:
            hp = int(getattr(player, "health", None))
            max_hp = int(getattr(player, "max_health", None))
        except Exception:
            hp = None
            max_hp = None
        food = self._get_food(player)

        title = ""
        try:
            title = self.plugin.title_system.get_equipped_title(player) or ""
        except Exception:
            title = ""

        guild = ""
        try:
            mem = self.plugin.guild_system.get_membership(xuid)
            if mem:
                g = self.plugin.guild_system.get_guild(int(mem.get("guild_id") or 0))
                if g:
                    guild = str(g.get("name") or "")
        except Exception:
            guild = ""

        mc_time = None
        try:
            level = getattr(player, "level", None) or getattr(
                self.plugin.server, "level", None
            )
            if level is not None:
                t = getattr(level, "time", None)
                if t is not None:
                    ticks = int(t) % 24000
                    hours = (ticks // 1000 + 6) % 24
                    mins = int((ticks % 1000) * 60 / 1000)
                    mc_time = f"{hours:02d}:{mins:02d}"
        except Exception:
            mc_time = None

        page_total = max(len(pages), 1)
        page_num = 1
        if pages:
            cur = self._resolve_current_page(st, pages)
            for i, p in enumerate(pages):
                if p.page_id == cur.page_id:
                    page_num = i + 1
                    break

        return {
            "time": self._cached_time or datetime.now().strftime("%H:%M"),
            "date": self._cached_date or datetime.now().strftime("%Y-%m-%d"),
            "player": str(getattr(player, "name", "") or ""),
            "money": money_str,
            "hp": hp,
            "max_hp": max_hp,
            "food": food,
            "online": self._cached_online,
            "max_players": self._cached_max_players,
            "tps": self._cached_tps,
            "mspt": self._cached_mspt,
            "ping": self._ping_cache.get(xuid),
            "mc_time": mc_time,
            "title": title,
            "guild": guild,
            "page": page_num,
            "page_total": page_total,
        }

    def _get_food(self, player: Player) -> Optional[Any]:
        # 优先 Attribute.PLAYER_HUNGER
        if Attribute is not None:
            try:
                attr_id = getattr(Attribute, "PLAYER_HUNGER", None)
                if attr_id is not None:
                    inst = player.get_attribute(attr_id)
                    if inst is not None:
                        return int(getattr(inst, "value", inst))
            except Exception:
                pass
            try:
                inst = player.get_attribute("minecraft:player.hunger")
                if inst is not None:
                    return int(getattr(inst, "value", inst))
            except Exception:
                pass
        for attr_name in ("food_level", "hunger", "food"):
            try:
                v = getattr(player, attr_name, None)
                if v is not None:
                    return int(v)
            except Exception:
                continue
        return None

    def _find_online(self, xuid: str) -> Optional[Player]:
        try:
            fn = getattr(self.plugin, "_find_online_player_by_xuid", None)
            if callable(fn):
                return fn(xuid)
        except Exception:
            pass
        try:
            for p in list(self.plugin.server.online_players or []):
                if str(getattr(p, "xuid", "") or "") == xuid:
                    return p
        except Exception:
            pass
        return None

    def _is_render_ready(self, player: Player) -> bool:
        if player is None:
            return False
        xuid = str(getattr(player, "xuid", "") or "").strip()
        if not xuid:
            return False
        if self._find_online(xuid) is None:
            return False
        try:
            iv = getattr(player, "is_valid", None)
            if callable(iv):
                if not iv():
                    return False
            elif isinstance(iv, bool) and not iv:
                return False
        except Exception:
            return False
        st = self._player_state.get(xuid)
        if st is not None and st.join_at_mono > 0:
            need = max(0, int(self.join_delay_ticks)) / 20.0
            if time.monotonic() - st.join_at_mono < need:
                return False
        return True

    def _ring_note(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._render_ring.append(f"{ts} {msg}")

    def _write_render_state(self, line: str) -> None:
        try:
            _RENDER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _RENDER_STATE_FILE.write_text(line, encoding="utf-8")
        except Exception:
            pass

    def _check_stale_render_state(self) -> None:
        try:
            if not _RENDER_STATE_FILE.exists():
                return
            raw = _RENDER_STATE_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            return
        if raw.startswith("open"):
            self._log_warn(f"previous crash during sidebar render: {raw}")
            self._write_render_state("")

    def _mark_render_enter(self, xuid: str) -> None:
        xs = str(xuid or "").strip() or "?"
        self._render_open_xuid = xs
        self._ring_note(f"ENTER {xs}")
        self._write_render_state(f"open {xs} {time.time():.3f}")

    def _mark_render_exit(self, xuid: str) -> None:
        xs = str(xuid or "").strip()
        self._ring_note(f"EXIT {xs or self._render_open_xuid}")
        if not xs or self._render_open_xuid == xs:
            self._render_open_xuid = ""
            self._write_render_state("")

    def _log_warn(self, msg: str) -> None:
        try:
            logger = getattr(self.plugin, "logger", None)
            if logger:
                logger.warning(f"[ARC Core][Sidebar] {msg}")
        except Exception:
            pass

    def _log_error(self, msg: str) -> None:
        try:
            logger = getattr(self.plugin, "logger", None)
            if logger:
                logger.error(f"[ARC Core][Sidebar] {msg}")
        except Exception:
            pass
