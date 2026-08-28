# -*- coding: utf-8 -*-
"""生物名称翻译：当生物名称中包含 ':' 时视为 MC 未提供对应翻译，从 entity_display_name.txt 读取用户配置的显示名。"""
from pathlib import Path
from typing import Optional


class EntityDisplayNameManager:
    """从 entity_display_name.txt 读取/补写生物显示名。仅对名称中含 ':' 的键进行查询。"""

    def __init__(self, base_path: Path, logger=None):
        self.base_path = Path(base_path)
        self.logger = logger
        self._file_path = self.base_path / "entity_display_name.txt"
        self._cache: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载 key=value，key 为生物原始名（如 entity.ns_ab:vfx_dragon_fire.name），value 为显示名。"""
        self._cache.clear()
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._file_path.exists():
            self._file_path.touch()
            with self._file_path.open("w", encoding="utf-8") as f:
                f.write("# 生物显示名翻译：每行 原始名称=显示名\n")
                f.write("# 支持：entity.minecraft.zombie.name=僵尸  或  minecraft:zombie=僵尸\n")
                f.write("# 当死亡播报等处的生物名称含有 ':' 时会在此查找；未找到的键会自动追加到文件末尾，请补写显示名。\n")
            return
        with self._file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                self._cache[key.strip()] = value.strip()

    @staticmethod
    def _alternate_keys(raw_name: str) -> list[str]:
        """为同一生物生成可互换的查找键。

        常见原始值：
        - minecraft:skeleton
        - entity.minecraft.skeleton.name
        - entity.ns_ab:vfx_dragon_fire.name（MC 未翻译键，冒号在命名空间与 ID 之间）
        """
        keys: list[str] = []
        # minecraft:skeleton → entity.minecraft.skeleton.name
        if raw_name.count(":") == 1 and not raw_name.startswith("entity."):
            ns, short = raw_name.split(":", 1)
            if ns and short:
                keys.append(f"entity.{ns}.{short}.name")
        # entity.ns:id.name → entity.ns.id.name 以及 ns:id
        if raw_name.startswith("entity.") and ":" in raw_name:
            mid = raw_name[len("entity.") :]
            ns, rest = mid.split(":", 1)
            if ns and rest:
                dotted = f"entity.{ns}.{rest}"
                keys.append(dotted)
                short = rest[:-5] if rest.endswith(".name") else rest
                if short:
                    keys.append(f"{ns}:{short}")
        # entity.minecraft.skeleton.name → minecraft:skeleton
        if (
            raw_name.startswith("entity.")
            and raw_name.endswith(".name")
            and ":" not in raw_name
        ):
            body = raw_name[len("entity.") : -len(".name")]
            if "." in body:
                ns, short = body.split(".", 1)
                if ns and short:
                    keys.append(f"{ns}:{short}")
        return keys

    def _lookup(self, key: str) -> Optional[str]:
        """按键及其等价形式查找非空翻译。"""
        if not key:
            return None
        seen: set[str] = set()
        for candidate in [key, *self._alternate_keys(key)]:
            if candidate in seen:
                continue
            seen.add(candidate)
            translated = self._cache.get(candidate)
            if translated:
                return translated
        return None

    def get_display_name(self, raw_name: str) -> str:
        """
        获取生物显示名。若 raw_name 中含 ':'，或为 entity.*.*.name 键，则从文件查找；
        支持类型 ID（minecraft:skeleton）与 entity.ns:id.name / entity.ns.id.name 互通；
        若文件中有非空翻译则返回翻译，否则将含 ':' 的未配置键追加到文件并返回 raw_name。
        """
        if not raw_name:
            return ""
        raw_name = str(raw_name).strip()
        needs_lookup = (":" in raw_name) or (
            raw_name.startswith("entity.") and raw_name.endswith(".name")
        )
        if not needs_lookup:
            return raw_name
        found = self._lookup(raw_name)
        if found:
            return found
        if ":" in raw_name and raw_name not in self._cache:
            self._append_key(raw_name)
        return raw_name

    def _append_key(self, key: str) -> None:
        """将未存在的键追加到文件末尾，便于用户补写翻译。"""
        self._cache[key] = ""
        try:
            with self._file_path.open("a", encoding="utf-8") as f:
                f.write(f"\n{key}=")
            if self.logger:
                self.logger.info(f"[ARC Core] 生物显示名未配置，已追加到 entity_display_name.txt: {key}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"[ARC Core] 追加 entity_display_name 失败: {str(e)}")

    def reload(self) -> None:
        """重新从文件加载。"""
        self._load()

    def get_display_name_for_entity_type(self, entity_type_id: str) -> str:
        """
        根据类型 ID（如 minecraft:creeper）解析显示名。
        优先查 entity.minecraft.creeper.name 与文件中其它键；无则返回简短 ID（如 creeper）。
        """
        if not entity_type_id:
            return ""
        et = str(entity_type_id).strip()
        found = self._lookup(et)
        if found:
            return found
        if ":" in et:
            return et.split(":", 1)[1]
        return et

    def get_display_name_or_identifier(self, entity_type_id: str) -> str:
        """
        有配置翻译时返回显示名；未配置时返回完整类型 ID（如 minecraft:creeper），不截断命名空间。
        """
        if not entity_type_id:
            return ""
        et = str(entity_type_id).strip()
        if et == "*":
            return "*"
        found = self._lookup(et)
        if found:
            return found
        return et
