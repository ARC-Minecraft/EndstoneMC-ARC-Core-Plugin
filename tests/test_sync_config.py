# -*- coding: utf-8 -*-
import importlib.util
import unittest
from pathlib import Path

_SYNC_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "endstone_arc_core" / "sync_config.py"
)
_spec = importlib.util.spec_from_file_location("sync_config_under_test", _SYNC_CONFIG_PATH)
sync_config = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(sync_config)

ALL_SHARED_SETTING_KEYS = sync_config.ALL_SHARED_SETTING_KEYS
can_edit_setting_key = sync_config.can_edit_setting_key
filter_incoming_settings = sync_config.filter_incoming_settings
is_hub_rule_setting = sync_config.is_hub_rule_setting
shared_setting_keys_for_categories = sync_config.shared_setting_keys_for_categories


class _FakeSettings:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def GetSetting(self, key):
        return self.data.get(key)


class SyncConfigTests(unittest.TestCase):
    def test_hub_rules_trimmed(self):
        self.assertNotIn("CHECKIN_REWARD_LIST", ALL_SHARED_SETTING_KEYS)
        self.assertNotIn("TELEPORT_COST_HOME", ALL_SHARED_SETTING_KEYS)
        self.assertNotIn("INVITE_REWARD_MONEY", ALL_SHARED_SETTING_KEYS)
        self.assertIn("PLAYER_INIT_MONEY_NUM", ALL_SHARED_SETTING_KEYS)
        self.assertIn("GUILD_CREATE_COST", ALL_SHARED_SETTING_KEYS)
        self.assertIn("DEFAULT_TITLE", ALL_SHARED_SETTING_KEYS)

    def test_player_category_has_no_shared_settings(self):
        keys = shared_setting_keys_for_categories(["player"])
        self.assertEqual(keys, set())

    def test_filter_incoming_only_allowed(self):
        raw = {
            "PLAYER_INIT_MONEY_NUM": "2000",
            "CHECKIN_DAILY_MONEY": "1000",
            "TELEPORT_COST_HOME": "50",
        }
        out = filter_incoming_settings(raw, ["economy"])
        self.assertEqual(out, {"PLAYER_INIT_MONEY_NUM": "2000"})

    def test_client_cannot_edit_hub_rules(self):
        sm = _FakeSettings(
            {
                "ENABLE_SYNC_CLIENT": "True",
                "ENABLE_SYNC_SERVER": "False",
            }
        )
        self.assertFalse(can_edit_setting_key(sm, "GUILD_CREATE_COST"))
        self.assertTrue(can_edit_setting_key(sm, "CHECKIN_DAILY_MONEY"))

    def test_hub_can_edit_hub_rules(self):
        sm = _FakeSettings({"ENABLE_SYNC_SERVER": "True"})
        self.assertTrue(can_edit_setting_key(sm, "GUILD_CREATE_COST"))

    def test_is_hub_rule_setting(self):
        self.assertTrue(is_hub_rule_setting("OP_TITLE"))
        self.assertFalse(is_hub_rule_setting("CHECKIN_REWARD_PICK_MIN"))


if __name__ == "__main__":
    unittest.main()
