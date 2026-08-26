# -*- coding: utf-8 -*-
"""OP 面板：浏览并修改 core_setting.yml。"""
import json
from typing import Any, List

from endstone import Player
from endstone.form import ActionForm, Dropdown, ModalForm, TextInput

from endstone_arc_core.setting_catalog import (
    BOOL_FALSE,
    BOOL_TRUE,
    SETTING_GROUPS,
    get_group,
    get_spec,
)


class OpSettingsUi:
    PAGE_SIZE = 12

    def __init__(self, plugin):
        self.plugin = plugin

    def _text(self, key: str) -> str:
        return self.plugin.language_manager.GetText(key)

    def _raw(self, key: str) -> str:
        value = self.plugin.setting_manager.get_existing(key)
        if value is None:
            return ""
        return str(value)

    def _preview(self, raw: str, maxlen: int = 22) -> str:
        text = (raw or "").strip() or self._text("OP_CORE_SETTINGS_EMPTY")
        if len(text) > maxlen:
            return text[:maxlen] + "…"
        return text

    def _save(self, player: Player, key: str, value: str, restart: bool = False) -> None:
        self.plugin.setting_manager.SetSetting(key, value)
        try:
            self.plugin._reapply_cached_settings()
        except Exception:
            pass
        player.send_message(self._text("OP_CORE_SETTINGS_SAVED").format(key))
        if restart:
            player.send_message(self._text("OP_CORE_SETTINGS_RESTART_HINT"))

    def show_groups(self, player: Player) -> None:
        panel = ActionForm(
            title=self._text("OP_CORE_SETTINGS_TITLE"),
            content=self._text("OP_CORE_SETTINGS_HUB_CONTENT"),
            on_close=None,
        )
        for group in SETTING_GROUPS:
            gid = str(group["id"])
            title = str(group["title"])
            panel.add_button(
                title,
                on_click=lambda p, g=gid: self.show_group(p, g),
            )
        panel.add_button(
            self._text("RETURN_BUTTON_TEXT"),
            on_click=self.plugin.show_op_main_panel,
        )
        player.send_form(panel)

    def show_group(self, player: Player, group_id: str, page: int = 0) -> None:
        group = get_group(group_id)
        if not group:
            self.show_groups(player)
            return
        items: List[dict] = list(group["items"])
        total_pages = max(1, (len(items) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        start = page * self.PAGE_SIZE
        chunk = items[start : start + self.PAGE_SIZE]
        panel = ActionForm(
            title=self._text("OP_CORE_SETTINGS_GROUP_TITLE").format(group["title"]),
            content=self._text("OP_CORE_SETTINGS_GROUP_CONTENT").format(
                group["title"], page + 1, total_pages
            ),
            on_close=None,
        )
        if group_id == "sync" and page == 0:
            panel.add_button(
                self._text("OP_SYNC_STATUS_BUTTON"),
                on_click=self.show_sync_status,
            )
            panel.add_button(
                self._text("OP_SYNC_RECONCILE_BUTTON"),
                on_click=self.confirm_sync_reconcile,
            )
        for spec in chunk:
            key = str(spec["key"])
            title = str(spec["title"])
            raw = self._raw(key)
            stype = str(spec["stype"])
            if stype in ("csv_list", "json_triples"):
                count = len(self._parse_list(spec, raw))
                label = f"{title} ({count})"
            else:
                label = f"{title}: {self._preview(raw)}"
            panel.add_button(
                label,
                on_click=lambda p, g=group_id, k=key, pg=page: self.open_setting(
                    p, g, k, pg
                ),
            )
        if page > 0:
            panel.add_button(
                self._text("OP_CORE_SETTINGS_PREV"),
                on_click=lambda p, g=group_id, pg=page: self.show_group(p, g, pg - 1),
            )
        if page < total_pages - 1:
            panel.add_button(
                self._text("OP_CORE_SETTINGS_NEXT"),
                on_click=lambda p, g=group_id, pg=page: self.show_group(p, g, pg + 1),
            )
        panel.add_button(
            self._text("RETURN_BUTTON_TEXT"),
            on_click=self.show_groups,
        )
        player.send_form(panel)

    def show_sync_status(self, player: Player) -> None:
        """展示跨服同步运行状态。"""
        content = self.plugin.get_sync_status_text()
        panel = ActionForm(
            title=self._text("OP_SYNC_STATUS_TITLE"),
            content=content,
            on_close=None,
        )
        panel.add_button(
            self._text("OP_SYNC_RECONCILE_BUTTON"),
            on_click=self.confirm_sync_reconcile,
        )
        panel.add_button(
            self._text("RETURN_BUTTON_TEXT"),
            on_click=lambda p: self.show_group(p, "sync", 0),
        )
        player.send_form(panel)

    def confirm_sync_reconcile(self, player: Player) -> None:
        panel = ActionForm(
            title=self._text("OP_SYNC_RECONCILE_TITLE"),
            content=self._text("OP_SYNC_RECONCILE_CONFIRM"),
            on_close=None,
        )
        panel.add_button(
            self._text("OP_SYNC_RECONCILE_RUN"),
            on_click=self.run_sync_reconcile,
        )
        panel.add_button(
            self._text("RETURN_BUTTON_TEXT"),
            on_click=self.show_sync_status,
        )
        player.send_form(panel)

    def run_sync_reconcile(self, player: Player) -> None:
        try:
            result = self.plugin.run_sync_reconcile()
        except Exception as e:
            player.send_message(
                self._text("OP_SYNC_RECONCILE_FAIL").format(str(e))
            )
            return self.show_sync_status(player)
        player.send_message(
            self._text("OP_SYNC_RECONCILE_OK").format(
                result.get("mode", "?"),
                result.get("detail", ""),
            )
        )
        self.show_sync_status(player)

    def open_setting(self, player: Player, group_id: str, key: str, page: int = 0) -> None:
        spec = get_spec(group_id, key)
        if not spec:
            self.show_group(player, group_id, page)
            return
        stype = str(spec["stype"])
        if stype in ("bool", "choice"):
            self._show_choice(player, group_id, spec, page)
            return
        if stype in ("csv_list", "json_triples"):
            self.show_list(player, group_id, key, 0, page)
            return
        self._show_text_edit(player, group_id, spec, page)

    def _show_choice(self, player: Player, group_id: str, spec: dict, page: int) -> None:
        key = str(spec["key"])
        choices = list(spec.get("choices") or [(BOOL_FALSE, "False"), (BOOL_TRUE, "True")])
        values = [str(v) for v, _ in choices]
        labels = [str(label) for _, label in choices]
        current = self._raw(key).strip()
        default_index = 0
        current_l = current.lower()
        for i, value in enumerate(values):
            if current_l == value.lower():
                default_index = i
                break
            if str(spec["stype"]) == "bool":
                if current_l in ("true", "1", "yes", "on") and value.lower() == "true":
                    default_index = i
                    break
                if current_l in ("false", "0", "no", "off", "") and value.lower() == "false":
                    default_index = i
                    break
        dropdown = Dropdown(
            label=str(spec["title"]),
            options=labels,
            default_index=default_index,
        )

        def on_submit(p: Player, json_str: str):
            try:
                data = json.loads(json_str)
            except Exception:
                p.send_message(self._text("OP_CORE_SETTINGS_INVALID"))
                return self.show_group(p, group_id, page)
            if self.plugin._modal_choice_is_back(data, 0):
                return self.show_group(p, group_id, page)
            try:
                idx = int(data[1])
            except (TypeError, ValueError, IndexError):
                idx = default_index
            if idx < 0 or idx >= len(values):
                idx = default_index
            self._save(p, key, values[idx], bool(spec.get("restart")))
            self.show_group(p, group_id, page)

        form = ModalForm(
            title=str(spec["title"]),
            controls=[self.plugin._modal_nav_dropdown(), dropdown],
            on_close=None,
            on_submit=on_submit,
        )
        player.send_form(form)

    def _show_text_edit(self, player: Player, group_id: str, spec: dict, page: int) -> None:
        key = str(spec["key"])
        stype = str(spec["stype"])
        raw = self._raw(key)
        field = TextInput(
            label=str(spec["title"]),
            placeholder=str(spec.get("placeholder") or ""),
            default_value=raw,
        )

        def on_submit(p: Player, json_str: str):
            try:
                data = json.loads(json_str)
            except Exception:
                p.send_message(self._text("OP_CORE_SETTINGS_INVALID"))
                return self.show_group(p, group_id, page)
            if self.plugin._modal_choice_is_back(data, 0):
                return self.show_group(p, group_id, page)
            typed = "" if len(data) < 2 or data[1] is None else str(data[1]).strip()
            if stype == "int":
                if typed == "":
                    saved = ""
                else:
                    try:
                        saved = str(int(float(typed)))
                    except (TypeError, ValueError):
                        p.send_message(self._text("OP_CORE_SETTINGS_INVALID"))
                        return self._show_text_edit(p, group_id, spec, page)
            elif stype == "float":
                if typed == "":
                    saved = ""
                else:
                    try:
                        saved = str(float(typed))
                    except (TypeError, ValueError):
                        p.send_message(self._text("OP_CORE_SETTINGS_INVALID"))
                        return self._show_text_edit(p, group_id, spec, page)
            else:
                saved = typed
            self._save(p, key, saved, bool(spec.get("restart")))
            self.show_group(p, group_id, page)

        form = ModalForm(
            title=str(spec["title"]),
            controls=[self.plugin._modal_nav_dropdown(), field],
            on_close=None,
            on_submit=on_submit,
        )
        player.send_form(form)

    def _parse_list(self, spec: dict, raw: str) -> List[Any]:
        stype = str(spec["stype"])
        if stype == "csv_list":
            if not raw or not str(raw).strip():
                return []
            return [part.strip() for part in str(raw).split(",") if part.strip()]
        return self.plugin._parse_checkin_reward_list_raw(raw)

    def _write_list(self, player: Player, spec: dict, items: List[Any]) -> None:
        key = str(spec["key"])
        stype = str(spec["stype"])
        if stype == "csv_list":
            value = ",".join(str(x) for x in items)
            self._save(player, key, value, bool(spec.get("restart")))
            return
        self.plugin._save_checkin_reward_list_entries(items)
        try:
            self.plugin._reapply_cached_settings()
        except Exception:
            pass
        player.send_message(self._text("OP_CORE_SETTINGS_SAVED").format(key))

    def show_list(
        self,
        player: Player,
        group_id: str,
        key: str,
        list_page: int = 0,
        group_page: int = 0,
    ) -> None:
        spec = get_spec(group_id, key)
        if not spec:
            self.show_group(player, group_id, group_page)
            return
        items = self._parse_list(spec, self._raw(key))
        total_pages = max(1, (len(items) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        list_page = max(0, min(list_page, total_pages - 1))
        start = list_page * self.PAGE_SIZE
        chunk_idx = list(range(start, min(start + self.PAGE_SIZE, len(items))))
        content = self._text("OP_CORE_SETTINGS_LIST_CONTENT").format(
            spec["title"], len(items), list_page + 1, total_pages
        )
        if not items:
            content += "\n" + self._text("OP_CORE_SETTINGS_ITEM_EMPTY")
        panel = ActionForm(
            title=str(spec["title"]),
            content=content,
            on_close=None,
        )
        panel.add_button(
            self._text("OP_CORE_SETTINGS_ADD"),
            on_click=lambda p, g=group_id, k=key, lp=list_page, gp=group_page: self.show_list_add(
                p, g, k, lp, gp
            ),
        )
        for idx in chunk_idx:
            label = self._list_item_label(spec, items[idx], idx)
            panel.add_button(
                label,
                on_click=lambda p, g=group_id, k=key, i=idx, lp=list_page, gp=group_page: self.show_list_item(
                    p, g, k, i, lp, gp
                ),
            )
        if list_page > 0:
            panel.add_button(
                self._text("OP_CORE_SETTINGS_PREV"),
                on_click=lambda p, g=group_id, k=key, lp=list_page, gp=group_page: self.show_list(
                    p, g, k, lp - 1, gp
                ),
            )
        if list_page < total_pages - 1:
            panel.add_button(
                self._text("OP_CORE_SETTINGS_NEXT"),
                on_click=lambda p, g=group_id, k=key, lp=list_page, gp=group_page: self.show_list(
                    p, g, k, lp + 1, gp
                ),
            )
        panel.add_button(
            self._text("RETURN_BUTTON_TEXT"),
            on_click=lambda p, g=group_id, gp=group_page: self.show_group(p, g, gp),
        )
        player.send_form(panel)

    def _list_item_label(self, spec: dict, item: Any, index: int) -> str:
        if str(spec["stype"]) == "csv_list":
            return f"{index + 1}. {item}"
        return self._text("OP_CORE_SETTINGS_TRIPLE_BUTTON").format(
            index + 1, item.get("item_id"), item.get("item_count"), item.get("weight")
        )

    def show_list_item(
        self,
        player: Player,
        group_id: str,
        key: str,
        index: int,
        list_page: int,
        group_page: int,
    ) -> None:
        spec = get_spec(group_id, key)
        if not spec:
            self.show_group(player, group_id, group_page)
            return
        items = self._parse_list(spec, self._raw(key))
        if index < 0 or index >= len(items):
            self.show_list(player, group_id, key, list_page, group_page)
            return
        label = self._list_item_label(spec, items[index], index)
        panel = ActionForm(
            title=str(spec["title"]),
            content=self._text("OP_CORE_SETTINGS_ITEM_CONTENT").format(label),
            on_close=None,
        )
        panel.add_button(
            self._text("OP_CORE_SETTINGS_DELETE"),
            on_click=lambda p, g=group_id, k=key, i=index, lp=list_page, gp=group_page: self._delete_list_item(
                p, g, k, i, lp, gp
            ),
        )
        panel.add_button(
            self._text("RETURN_BUTTON_TEXT"),
            on_click=lambda p, g=group_id, k=key, lp=list_page, gp=group_page: self.show_list(
                p, g, k, lp, gp
            ),
        )
        player.send_form(panel)

    def _delete_list_item(
        self,
        player: Player,
        group_id: str,
        key: str,
        index: int,
        list_page: int,
        group_page: int,
    ) -> None:
        spec = get_spec(group_id, key)
        if not spec:
            self.show_group(player, group_id, group_page)
            return
        items = self._parse_list(spec, self._raw(key))
        if 0 <= index < len(items):
            del items[index]
            self._write_list(player, spec, items)
        self.show_list(player, group_id, key, list_page, group_page)

    def show_list_add(
        self,
        player: Player,
        group_id: str,
        key: str,
        list_page: int,
        group_page: int,
    ) -> None:
        spec = get_spec(group_id, key)
        if not spec:
            self.show_group(player, group_id, group_page)
            return
        if str(spec["stype"]) == "csv_list":
            field = TextInput(
                label=str(spec["title"]),
                placeholder=str(spec.get("placeholder") or ""),
                default_value="",
            )

            def on_submit_csv(p: Player, json_str: str):
                try:
                    data = json.loads(json_str)
                except Exception:
                    p.send_message(self._text("OP_CORE_SETTINGS_INVALID"))
                    return self.show_list(p, group_id, key, list_page, group_page)
                if self.plugin._modal_choice_is_back(data, 0):
                    return self.show_list(p, group_id, key, list_page, group_page)
                typed = "" if len(data) < 2 or data[1] is None else str(data[1]).strip()
                if not typed:
                    p.send_message(self._text("OP_CORE_SETTINGS_INVALID"))
                    return self.show_list(p, group_id, key, list_page, group_page)
                items = self._parse_list(spec, self._raw(key))
                if any(str(x).lower() == typed.lower() for x in items):
                    p.send_message(self._text("OP_CORE_SETTINGS_DUPLICATE"))
                    return self.show_list(p, group_id, key, list_page, group_page)
                items.append(typed)
                self._write_list(p, spec, items)
                self.show_list(p, group_id, key, list_page, group_page)

            form = ModalForm(
                title=self._text("OP_CORE_SETTINGS_ADD"),
                controls=[self.plugin._modal_nav_dropdown(), field],
                on_close=None,
                on_submit=on_submit_csv,
            )
            player.send_form(form)
            return

        item_input = TextInput(
            label=self._text("OP_CORE_SETTINGS_TRIPLE_ID"),
            placeholder="minecraft:diamond",
            default_value="",
        )
        count_input = TextInput(
            label=self._text("OP_CORE_SETTINGS_TRIPLE_COUNT"),
            placeholder="1",
            default_value="1",
        )
        weight_input = TextInput(
            label=self._text("OP_CORE_SETTINGS_TRIPLE_WEIGHT"),
            placeholder="1",
            default_value="1",
        )

        def on_submit_triple(p: Player, json_str: str):
            try:
                data = json.loads(json_str)
            except Exception:
                p.send_message(self._text("OP_CORE_SETTINGS_INVALID"))
                return self.show_list(p, group_id, key, list_page, group_page)
            if self.plugin._modal_choice_is_back(data, 0):
                return self.show_list(p, group_id, key, list_page, group_page)
            item_id = "" if len(data) < 2 or data[1] is None else str(data[1]).strip()
            try:
                count = int(str(data[2]).strip()) if len(data) >= 3 else 0
            except (TypeError, ValueError):
                count = 0
            try:
                weight = int(str(data[3]).strip()) if len(data) >= 4 else 1
            except (TypeError, ValueError):
                weight = 1
            if not item_id or count <= 0 or weight <= 0:
                p.send_message(self._text("OP_CORE_SETTINGS_INVALID"))
                return self.show_list(p, group_id, key, list_page, group_page)
            items = self._parse_list(spec, self._raw(key))
            items.append({"item_id": item_id, "item_count": count, "weight": weight})
            self._write_list(p, spec, items)
            self.show_list(p, group_id, key, list_page, group_page)

        form = ModalForm(
            title=self._text("OP_CORE_SETTINGS_ADD"),
            controls=[
                self.plugin._modal_nav_dropdown(),
                item_input,
                count_input,
                weight_input,
            ],
            on_close=None,
            on_submit=on_submit_triple,
        )
        player.send_form(form)
