import json
import os
import tempfile
import unittest

from logic.roll_manager import (
    InventoryDataError,
    clear_inventory,
    get_inventory,
    sync_roll_instances,
    equip_roll,
    unequip_roll,
    get_equipment_slots,
    get_equipped_rolls,
    InventoryStateError,
    EQUIPMENT_CATEGORIES,
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

    def test_ids_survive_csv_numeric_type_conversion(self):
        first = sync_roll_instances([self.pull], path=self.inventory_path)
        reloaded_pull = dict(self.pull)
        reloaded_pull["Rarity"] = 3.5
        reloaded_pull["Luck"] = 50.0

        second = sync_roll_instances(
            [reloaded_pull],
            path=self.inventory_path,
        )
        self.assertEqual(first[0]["id"], second[0]["id"])

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

    def test_equipment_slots_increase_every_ten_levels(self):
        self.assertEqual(get_equipment_slots(1), 3)
        self.assertEqual(get_equipment_slots(9), 3)
        self.assertEqual(get_equipment_slots(10), 4)
        self.assertEqual(get_equipment_slots(19), 4)
        self.assertEqual(get_equipment_slots(20), 5)

    def test_equip_and_unequip_by_unique_id(self):
        rolls = sync_roll_instances(
            [self.pull, self.pull],
            path=self.inventory_path,
        )
        equipped = equip_roll(
            rolls[0]["id"],
            level=1,
            path=self.inventory_path,
        )
        self.assertEqual(equipped["status"], "equipped")
        self.assertEqual(len(get_equipped_rolls(self.inventory_path)), 1)

        returned = unequip_roll(
            rolls[0]["id"],
            path=self.inventory_path,
        )
        self.assertEqual(returned["status"], "stored")
        self.assertEqual(get_equipped_rolls(self.inventory_path), [])

        # The identical second pull remains a separate stored instance.
        inventory = get_inventory(self.inventory_path)
        self.assertEqual(inventory[1]["id"], rolls[1]["id"])
        self.assertEqual(inventory[1]["status"], "stored")

    def test_equipment_slot_limit_is_enforced_per_category(self):
        skill_pulls = [
            dict(self.pull, Type="Skill", Element=f"Skill {i}")
            for i in range(4)
        ]
        ability_pulls = [
            dict(self.pull, Type="Ability", Element=f"Ability {i}")
            for i in range(3)
        ]
        rolls = sync_roll_instances(
            skill_pulls + ability_pulls,
            path=self.inventory_path,
        )

        # Three Skill instances fill only the Skill category.
        for roll in rolls[:3]:
            equip_roll(roll["id"], level=9, path=self.inventory_path)

        with self.assertRaises(InventoryStateError):
            equip_roll(rolls[3]["id"], level=9, path=self.inventory_path)

        # Ability has its own independent three slots at the same level.
        for roll in rolls[4:]:
            equip_roll(roll["id"], level=9, path=self.inventory_path)

        self.assertEqual(len(get_equipped_rolls(self.inventory_path)), 6)

        # The fourth Skill slot becomes available at level 10.
        equip_roll(rolls[3]["id"], level=10, path=self.inventory_path)
        self.assertEqual(len(get_equipped_rolls(self.inventory_path)), 7)

    def test_item_is_not_an_equipable_category(self):
        item = dict(self.pull, Type="Item", Element="Test Item")
        roll = sync_roll_instances([item], path=self.inventory_path)[0]

        with self.assertRaises(InventoryStateError):
            equip_roll(roll["id"], level=1, path=self.inventory_path)

        self.assertEqual(get_inventory(self.inventory_path)[0]["status"], "stored")

    def test_equipment_categories_match_the_agreed_four_types(self):
        self.assertEqual(
            EQUIPMENT_CATEGORIES,
            ("Ability", "Familiar", "Skill", "Trait"),
        )

    def test_discarded_roll_cannot_be_equipped(self):
        rolls = sync_roll_instances([self.pull], path=self.inventory_path)
        with open(self.inventory_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        data["rolls"][0]["status"] = "discarded"
        with open(self.inventory_path, "w", encoding="utf-8") as file:
            json.dump(data, file)

        with self.assertRaises(InventoryStateError):
            equip_roll(rolls[0]["id"], level=1, path=self.inventory_path)

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
