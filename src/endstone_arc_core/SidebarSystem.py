# -*- coding: utf-8 -*-
"""弧光核心侧边栏总控：多页面注册、键值对模板、定时翻页、每玩家独立计分板。"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
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
    "§7§m----------------",
    "§f{date} §b{time}",
    "§e金钱 §f{money}",
    "§c生命 §f{hp}§7/§f{max_hp}",
    "§6饱食 §f{food}",
    "§aTPS §f{tps} §7MSPT §f{mspt}",
    "§7在线 §f{online}§7/§f{max_players}",
    "§7延迟 §f{ping}ms",
    "§7§m----------------",
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


def _unique_entry_name(text: str, used: Set[str]) -> str:
    """同一 objective 内 entry 名必须唯一；重复行追加不可见 §r。"""
    base = text if text else " "
    name = base
    n = 0
    while name in used:
        n += 1
        name = base + ("§r" * n)
        if len(name) > 40:
            # Bedrock 行名过长会截断；截断后再追加
            name = (base[: 40 - n] if 40 > n else base[:1]) + ("§r" * n)
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
    obj_seq: int = 0
    last_render_sig: str = ""


class SidebarSystem:
    def __init__(self, plugin):
        self.plugin = plugin
        self._pages: Dict[str, SidebarPage] = {}
        # xuid -> page_id -> key -> value
        self._values: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # page_id -> key -> value
        self._global_values: Dict[str, Dict[str, Any]] = {}
        self._player_state: Dict[str, PlayerSidebarState] = {}
        self.enabled = True
        self.default_on = True
        self.sidebar_title = "§l§b弧 光 服 务 器"
        self.switch_interval = 10.0
        self.refresh_ticks = 20
        self.max_lines = 15
        self.main_line_templates: List[str] = list(DEFAULT_MAIN_LINES)
        self.reload_config()
        self._ensure_main_page()

    # ------------------------------------------------------------------ config
    def reload_config(self) -> None:
        sm = self.plugin.setting_manager
        self.enabled = _setting_bool(sm.GetSetting("SIDEBAR_ENABLE"), True)
        self.default_on = _setting_bool(sm.GetSetting("SIDEBAR_DEFAULT_ON"), True)
        title = sm.GetSetting("SIDEBAR_TITLE")
        self.sidebar_title = (
            str(title).replace("\\n", "\n") if title else "§l§b弧 光 服 务 器"
        )
        self.switch_interval = float(
            max(1, _setting_int(sm.GetSetting("SIDEBAR_SWITCH_INTERVAL"), 10))
        )
        self.refresh_ticks = max(
            1, _setting_int(sm.GetSetting("SIDEBAR_REFRESH_TICKS"), 20)
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
            ok = True
            for k, v in values.items():
                if not self.set_value(page_id, str(k), v, xuid=xuid):
                    ok = False
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
            )
            self._player_state[xuid] = st
            if st.enabled:
                self._ensure_player_scoreboard(player, st)
                self.refresh_player(player)
        except Exception as e:
            self._log_error(f"on_player_join: {e}")

    def on_player_quit(self, player: Player) -> None:
        try:
            xuid = str(getattr(player, "xuid", "") or "").strip()
            if not xuid:
                return
            st = self._player_state.pop(xuid, None)
            self._values.pop(xuid, None)
            if st is not None:
                self._clear_sidebar_display(player, st)
        except Exception as e:
            self._log_error(f"on_player_quit: {e}")

    def shutdown(self) -> None:
        try:
            for player in list(getattr(self.plugin.server, "online_players", []) or []):
                xuid = str(getattr(player, "xuid", "") or "").strip()
                st = self._player_state.get(xuid)
                if st is not None:
                    self._clear_sidebar_display(player, st)
            self._player_state.clear()
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
                self._clear_sidebar_display(player, st)
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
        if not self.enabled:
            return
        try:
            now = time.time()
            for player in list(getattr(self.plugin.server, "online_players", []) or []):
                try:
                    self._tick_player(player, now)
                except Exception as e:
                    self._log_error(f"tick player: {e}")
        except Exception as e:
            self._log_error(f"tick: {e}")

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
        if not st.enabled:
            self._clear_sidebar_display(player, st)
            return
        pages = self._visible_pages_for(xuid)
        if not pages:
            self._clear_sidebar_display(player, st)
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
        if not st.enabled:
            return
        pages = self._visible_pages_for(xuid)
        if not pages:
            return
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
            )
            self._player_state[xuid] = st
        return st

    def _ensure_player_scoreboard(self, player: Player, st: PlayerSidebarState) -> Any:
        if st.scoreboard is not None:
            try:
                player.scoreboard = st.scoreboard
            except Exception:
                pass
            return st.scoreboard
        try:
            sb = self.plugin.server.create_scoreboard()
            st.scoreboard = sb
            player.scoreboard = sb
            return sb
        except Exception as e:
            self._log_error(f"create_scoreboard: {e}")
            # 回退：使用服务器主计分板（多玩家可能互相覆盖标题，但至少能显示）
            try:
                sb = self.plugin.server.scoreboard
                st.scoreboard = sb
                return sb
            except Exception:
                return None

    def _clear_sidebar_display(self, player: Player, st: PlayerSidebarState) -> None:
        try:
            sb = st.scoreboard
            if sb is not None:
                try:
                    sb.clear_slot(DisplaySlot.SIDE_BAR)
                except Exception:
                    pass
                if st.current_objective_name:
                    try:
                        obj = sb.get_objective(st.current_objective_name)
                        if obj is not None:
                            obj.unregister()
                    except Exception:
                        pass
            st.current_objective_name = ""
            st.last_render_sig = ""
            # 恢复默认计分板
            try:
                primary = self.plugin.server.scoreboard
                if primary is not None:
                    player.scoreboard = primary
            except Exception:
                pass
            st.scoreboard = None
        except Exception as e:
            self._log_error(f"clear_sidebar: {e}")

    def _render_to_player(
        self,
        player: Player,
        st: PlayerSidebarState,
        page: SidebarPage,
        pages: List[SidebarPage],
        force: bool = False,
    ) -> None:
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

        st.obj_seq = (st.obj_seq + 1) % 10000
        new_name = f"arc_sb_{st.obj_seq}"
        old_name = st.current_objective_name

        try:
            # 清理同名残留
            try:
                existing = sb.get_objective(new_name)
                if existing is not None:
                    existing.unregister()
            except Exception:
                pass

            criteria = getattr(Criteria, "DUMMY", None)
            if criteria is None:
                criteria = Criteria.Type.DUMMY  # type: ignore[attr-defined]
            obj = sb.add_objective(new_name, criteria, display_title)

            used: Set[str] = set()
            # DESCENDING：分值大的在上，第 1 行给最大分
            score_base = max(len(rendered), 1)
            for i, line in enumerate(rendered[: self.max_lines]):
                entry = _unique_entry_name(line, used)
                sc = obj.get_score(entry)
                sc.value = score_base - i

            obj.set_display(DisplaySlot.SIDE_BAR, ObjectiveSortOrder.DESCENDING)
            st.current_objective_name = new_name
            st.last_render_sig = sig

            if old_name and old_name != new_name:
                try:
                    old = sb.get_objective(old_name)
                    if old is not None:
                        old.unregister()
                except Exception:
                    pass
        except Exception as e:
            self._log_error(f"render_to_player: {e}")

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

    def _builtin_vars(
        self,
        player: Player,
        xuid: str,
        pages: List[SidebarPage],
        st: PlayerSidebarState,
    ) -> Dict[str, Any]:
        now = datetime.now()
        money = 0.0
        try:
            money = self.plugin.economy.get_player_money_by_xuid(xuid)
        except Exception:
            pass

        hp = None
        max_hp = None
        try:
            hp = int(getattr(player, "health", None))
            max_hp = int(getattr(player, "max_health", None))
        except Exception:
            hp = None
            max_hp = None

        food = self._get_food(player)

        online = 0
        max_players = None
        try:
            online = len(list(self.plugin.server.online_players or []))
        except Exception:
            online = 0
        try:
            mp = getattr(self.plugin.server, "max_players", None)
            if mp is not None:
                max_players = int(mp)
        except Exception:
            max_players = None

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

        ping = None
        try:
            ping = int(getattr(player, "ping", None))
        except Exception:
            ping = None

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
                    # 0-23999 → HH:MM 游戏日
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

        money_str = (
            f"{money:.2f}".rstrip("0").rstrip(".")
            if isinstance(money, float)
            else str(money)
        )

        return {
            "time": now.strftime("%H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "player": str(getattr(player, "name", "") or ""),
            "money": money_str,
            "hp": hp,
            "max_hp": max_hp,
            "food": food,
            "online": online,
            "max_players": max_players,
            "tps": tps,
            "mspt": mspt,
            "ping": ping,
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

    def _log_error(self, msg: str) -> None:
        try:
            logger = getattr(self.plugin, "logger", None)
            if logger:
                logger.error(f"[ARC Core][Sidebar] {msg}")
        except Exception:
            pass
