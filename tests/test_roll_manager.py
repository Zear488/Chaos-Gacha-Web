import json
import os
import tempfile
import unittest

from logic.roll_manager import (
    InventoryDataError,
    clear_inventory,
    get_inventory,
    sync_roll_instances,
)


class RollManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.inventory_path = os.path.join(self.temp_dir.name, "inventory.json")
        self.pull = {
            "Type": "Skill",
            "Element": "Test Skill",
            "Rarity": "3.50",
            "Tier": "Rare",
            "Luck": "50.00%",
            "Description": "Test description",
            "Color": "#11d939",
            "Notes": "",
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_identical_pulls_receive_different_ids(self):
        rolls = sync_roll_instances(
            [self.pull, self.pull],
            path=self.inventory_path,
        )

        self.assertEqual(len(rolls), 2)
        self.assertNotEqual(rolls[0]["id"], rolls[1]["id"])
        self.assertEqual(rolls[0]["status"], "stored")
        self.assertEqual(rolls[1]["status"], "stored")

    def test_ids_remain_stable_after_sync(self):
        first = sync_roll_instances(
            [self.pull, self.pull],
            path=self.inventory_path,
        )
        second = sync_roll_instances(
            [self.pull, self.pull],
            path=self.inventory_path,
        )

        self.assertEqual(
            [roll["id"] for roll in first],
            [roll["id"] for roll in second],
        )
        self.assertEqual(len(get_inventory(self.inventory_path)), 2)

    def test_existing_inventory_status_is_preserved(self):
        rolls = sync_roll_instances([self.pull], path=self.inventory_path)
        with open(self.inventory_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        data["rolls"][0]["status"] = "equipped"
        with open(self.inventory_path, "w", encoding="utf-8") as file:
            json.dump(data, file)

        synced = sync_roll_instances([self.pull], path=self.inventory_path)
        self.assertEqual(synced[0]["id"], rolls[0]["id"])
        self.assertEqual(synced[0]["status"], "equipped")

    def test_clear_inventory_removes_all_instances(self):
        sync_roll_instances([self.pull], path=self.inventory_path)
        clear_inventory(self.inventory_path)
        self.assertEqual(get_inventory(self.inventory_path), [])

    def test_corrupt_inventory_is_not_overwritten(self):
        original = "{ invalid json"
        with open(self.inventory_path, "w", encoding="utf-8") as file:
            file.write(original)

        with self.assertRaises(InventoryDataError):
            sync_roll_instances([self.pull], path=self.inventory_path)

        with open(self.inventory_path, "r", encoding="utf-8") as file:
            self.assertEqual(file.read(), original)


if __name__ == "__main__":
    unittest.main()
