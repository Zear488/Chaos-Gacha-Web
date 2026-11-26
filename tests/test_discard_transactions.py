import json
import os
import tempfile
import unittest
from unittest.mock import patch

from logic.roll_manager import discard_roll, get_equipped_rolls, get_inventory
from logic.tracker import GachaHistoryTracker


class DiscardTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.inventory_path = os.path.join(self.temp_dir.name, "inventory.json")
        self.points_path = os.path.join(self.temp_dir.name, "points.json")
        self.repeats_path = os.path.join(self.temp_dir.name, "repeats.json")
        self.patches = [
            patch("logic.tracker.GACHA_LOG_DIR", self.temp_dir.name),
            patch("logic.tracker.POINTS_FILE", self.points_path),
            patch("logic.tracker.REPEATS_FILE", self.repeats_path),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self._stop_patches)
        self.tracker = GachaHistoryTracker()

    def _stop_patches(self):
        for item in reversed(self.patches):
            item.stop()

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_inventory(self, status="equipped", tier="Common"):
        with open(self.inventory_path, "w", encoding="utf-8") as file:
            json.dump({
                "version": 1,
                "rolls": [{
                    "id": "roll-unique-1",
                    "status": status,
                    "pull": {
                        "Type": "Skill",
                        "Element": "Test Skill",
                        "Tier": tier,
                    },
                }],
            }, file)

    def test_discard_awards_tier_points_once_and_deactivates_equipment(self):
        self.write_inventory(status="equipped", tier="Common")

        first = discard_roll(
            "roll-unique-1",
            self.tracker,
            path=self.inventory_path,
        )
        second = discard_roll(
            "roll-unique-1",
            self.tracker,
            path=self.inventory_path,
        )

        self.assertTrue(first["tp_awarded_now"])
        self.assertFalse(second["tp_awarded_now"])
        self.assertEqual(first["tp_value"], 0.001)
        self.assertEqual(self.tracker.get_points(), 0.001)
        self.assertEqual(get_equipped_rolls(self.inventory_path), [])
        self.assertEqual(get_inventory(self.inventory_path)[0]["status"], "discarded")

    def test_discard_points_survive_history_reload(self):
        self.write_inventory(status="stored", tier="Rare")
        discard_roll("roll-unique-1", self.tracker, path=self.inventory_path)

        self.tracker.load_from_log([])
        self.assertEqual(self.tracker.get_points(), 0.009)

    def test_corrupt_points_file_is_not_overwritten(self):
        with open(self.points_path, "w", encoding="utf-8") as file:
            file.write("{ broken")
        with self.assertRaises(ValueError):
            GachaHistoryTracker()
        with open(self.points_path, "r", encoding="utf-8") as file:
            self.assertEqual(file.read(), "{ broken")


if __name__ == "__main__":
    unittest.main()
