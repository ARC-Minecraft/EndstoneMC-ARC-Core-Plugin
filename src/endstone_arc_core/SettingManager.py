from pathlib import Path
from typing import Callable, Dict, List

MAIN_PATH = 'plugins/ARCCore'

class SettingManager:
    setting_dict = {}  # Class variable to store all settings

    def __init__(self):
        self.setting_file_path = Path(MAIN_PATH) / "core_setting.yml"
        self._change_listeners: List[Callable[[str, str], None]] = []
        self._suppress_notify = False
        self._load_setting_file()

    def _load_setting_file(self):
        # Create config directory if not exists
        self.setting_file_path.parent.mkdir(exist_ok=True)

        # Create settings file if not exists
        if not self.setting_file_path.exists():
            self.setting_file_path.touch()

        # Load settings file content
        with self.setting_file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line:
                    key, value = line.split("=", 1)
                    SettingManager.setting_dict[key.strip()] = value.strip()

    def GetSetting(self, key):
        # If key doesn't exist in settings, add it
        if key not in SettingManager.setting_dict:
            with self.setting_file_path.open("a", encoding="utf-8") as f:
                f.write(f"\n{key}=")
            SettingManager.setting_dict[key] = ""

        return None if not SettingManager.setting_dict[key] else SettingManager.setting_dict[key]

    def get_existing(self, key: str):
        """读取已有键；不存在返回 None（含空字符串也会返回 ""），不自动写文件。"""
        if key not in SettingManager.setting_dict:
            return None
        return SettingManager.setting_dict[key]

    def add_change_listener(self, callback: Callable[[str, str], None]) -> None:
        self._change_listeners.append(callback)

    def _rewrite_file(self) -> None:
        with self.setting_file_path.open("w", encoding="utf-8") as f:
            for k, v in SettingManager.setting_dict.items():
                f.write(f"{k}={v}\n")

    def _notify_change(self, key: str, value: str) -> None:
        if self._suppress_notify:
            return
        for callback in self._change_listeners:
            try:
                callback(key, value)
            except Exception:
                pass

    def SetSetting(self, key, value):
        # Update setting in memory
        SettingManager.setting_dict[key] = str(value)
        self._rewrite_file()
        self._notify_change(key, str(value))

    def ApplySettings(self, updates: Dict[str, str]) -> int:
        """批量覆盖配置并只写一次文件；不触发变更回调（避免从服回推）。"""
        if not updates:
            return 0
        changed = 0
        self._suppress_notify = True
        try:
            for key, value in updates.items():
                new_value = "" if value is None else str(value)
                if SettingManager.setting_dict.get(key) != new_value:
                    SettingManager.setting_dict[key] = new_value
                    changed += 1
            if changed:
                self._rewrite_file()
        finally:
            self._suppress_notify = False
        return changed

    def Reload(self):
        """重新从文件加载配置（清空内存后重新读取 core_setting.yml）"""
        SettingManager.setting_dict.clear()
        self._load_setting_file()