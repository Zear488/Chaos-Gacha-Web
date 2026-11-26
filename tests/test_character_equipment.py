import json
import os
import tempfile
import unittest

from character.character import Character
from character.stats_manager import StatsManager


class CharacterEquipmentTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.inventory_path = os.path.join(self.temp_dir.name, "inventory.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_inventory(self, rolls):
        with open(self.inventory_path, "w", encoding="utf-8") as file:
            json.dump({"version": 1, "rolls": rolls}, file)

    def test_only_equipped_instances_apply_description_modifiers(self):
        self.write_inventory([
            {
                "id": "equipped-1",
                "status": "equipped",
                "pull": {
                    "Type": "Skill",
                    "Element": "Equipped Skill",
                    "Description": (
                        "#STATS: STR +4, Mana +3\n"
                        "#RESISTANCES: Fire +20%\n"
                        "#FACTION: Test Order"
                    ),
                },
            },
            {
                "id": "stored-1",
                "status": "stored",
                "pull": {
                    "Type": "Skill",
                    "Element": "Stored Skill",
                    "Description": "#STATS: STR +100",
                },
            },
            {
                "id": "discarded-1",
                "status": "discarded",
                "pull": {
                    "Type": "Ability",
                    "Element": "Discarded Ability",
                    "Description": "#STATS: STR +200",
                },
            },
        ])

        character = Character()
        character.stats = StatsManager({
            "STR": 10,
            "Mana": 5,
            "AGI": 2,
        })
        character.load_equipped_rolls(self.inventory_path)
        character.apply_gacha_items()

        self.assertEqual(
            character.stats.finalize(),
            {"STR": 14, "Mana": 8, "AGI": 2},
        )
        self.assertEqual(character.resistances, {"Fire": 20})
        self.assertEqual(character.other_fields, {"FACTION": ["Test Order"]})

    def test_empty_equipped_inventory_does_not_apply_stored_rolls(self):
        self.write_inventory([
            {
                "id": "stored-1",
                "status": "stored",
                "pull": {
                    "Type": "Ability",
                    "Element": "Stored Ability",
                    "Description": "#STATS: STR +99",
                },
            },
        ])

        character = Character()
        character.stats = StatsManager({"STR": 1})
        character.load_equipped_rolls(self.inventory_path)
        character.apply_gacha_items()

        self.assertEqual(character.stats.finalize(), {"STR": 1})


if __name__ == "__main__":
    unittest.main()
