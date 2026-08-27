# -*- coding: utf-8 -*-
"""天眼查询：模糊名与事件类型别名。"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_MOD_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "endstone_arc_core"
    / "sky_eye_log.py"
)
_spec = importlib.util.spec_from_file_location("sky_eye_log", _MOD_PATH)
assert _spec and _spec.loader
sky_eye_log = importlib.util.module_from_spec(_spec)
sys.modules["sky_eye_log"] = sky_eye_log
_spec.loader.exec_module(sky_eye_log)

SkyEyeStore = sky_eye_log.SkyEyeStore
format_sky_eye_records = sky_eye_log.format_sky_eye_records
resolve_event_kind = sky_eye_log.resolve_event_kind


class ResolveEventKindTests(unittest.TestCase):
    def test_death_aliases(self):
        actions, extra, _ = resolve_event_kind("death")
        self.assertEqual(actions, ["PlayerDeath"])
        self.assertEqual(extra, "")
        actions2, _, _ = resolve_event_kind("死亡")
        self.assertEqual(actions2, ["PlayerDeath"])

    def test_pvp_filter(self):
        actions, extra, _ = resolve_event_kind("pvp")
        self.assertEqual(actions, ["ActorDamage", "PlayerDeath"])
        self.assertIn("player", extra)

    def test_exact_action(self):
        actions, extra, _ = resolve_event_kind("PlayerDeath")
        self.assertEqual(actions, ["PlayerDeath"])
        self.assertEqual(extra, "")


class SkyEyeFuzzyQueryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = SkyEyeStore(Path(self._tmp.name) / "skyeye.db")
        self.store.append(
            7,
            "PlayerDeath",
            "SteveTheBuilder",
            "x1",
            "minecraft:overworld",
            1.0,
            64.0,
            1.0,
            detail="cause=fall",
            target_type="",
        )
        self.store.append(
            7,
            "ActorDamage",
            "AlexPvP",
            "x2",
            "minecraft:overworld",
            2.0,
            64.0,
            2.0,
            detail="damage=1",
            target_name="Bob",
            target_xuid="x3",
            target_type="player",
        )
        self.store.append(
            7,
            "ActorDamage",
            "Hunter",
            "x4",
            "minecraft:overworld",
            3.0,
            64.0,
            3.0,
            detail="damage=2",
            target_name="Zombie",
            target_type="minecraft:zombie",
        )
        self.store.flush()

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_fuzzy_name(self):
        rows = self.store.query(player_name="Steve", minutes=60, name_fuzzy=True)
        self.assertTrue(any(r["player_name"] == "SteveTheBuilder" for r in rows))

    def test_death_without_player(self):
        rows = self.store.query(action="death", minutes=60, limit=20)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "PlayerDeath")

    def test_pvp_only(self):
        rows = self.store.query(action="pvp", minutes=60, limit=20)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["player_name"], "AlexPvP")

    def test_format_mentions_players(self):
        rows = self.store.query(action="death", minutes=60)
        text = format_sky_eye_records(rows)
        self.assertIn("SteveTheBuilder", text)
        self.assertIn("涉及玩家", text)


if __name__ == "__main__":
    unittest.main()
