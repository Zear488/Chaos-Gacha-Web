import os
import tempfile
import unittest

from logic.history_csv import parse_history_csv, serialize_history_csv
from logic.roll_manager import sync_roll_instances, get_inventory, equip_roll


class HistoryCsvRoundTripTests(unittest.TestCase):
    def test_export_contains_required_pull_and_instance_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "inventory.json")
            pull = {
                "Type": "Skill",
                "Element": "★ Test Skill",
                "Rarity": "5.50",
                "Tier": "Epic",
                "LuckValue": 12.5,
                "Luck": "12.50%",
                "Description": "#STATS: STR +2\nTest description",
                "Color": "#6811d9",
                "Notes": "✨ Boosted Star Bonus — -5 TP",
            }
            instance = sync_roll_instances([pull], path=path)[0]
            csv_text = serialize_history_csv([pull], [instance])
            header = csv_text.splitlines()[0]
            for column in (
                "ID", "Status", "Type", "Element", "Rarity", "Tier",
                "LuckValue", "Luck", "Description", "Color", "Notes",
                "Modifiers", "ModifiersGenerated", "ModifierGenerationVersion",
                "SpecialModifiers", "SpecialModifiersGenerated", "SpecialModifierGenerationVersion",
            ):
                self.assertIn(column, header)

    def test_round_trip_preserves_id_status_and_modifiers(self):
        with tempfile.TemporaryDirectory() as directory:
            original_path = os.path.join(directory, "original.json")
            restored_path = os.path.join(directory, "restored.json")
            pull = {
                "Type": "Skill",
                "Element": "Test Skill",
                "Rarity": "5.50",
                "Tier": "Epic",
                "LuckValue": 12.5,
                "Luck": "12.50%",
                "Description": "#STATS: STR +2",
                "Color": "#6811d9",
                "Notes": "",
            }
            original = sync_roll_instances([pull], path=original_path)[0]
            original["status"] = "equipped"
            original["modifiers"] = [
                {"stat": "STR", "kind": "flat", "value": 8.5},
                {"stat": "STR", "kind": "percent", "value": 7.0},
            ]
            original["modifiers_generated"] = True
            original["modifier_generation_version"] = 1
            original["special_modifiers"] = {
                "family": "resistances",
                "effects": [{
                    "type": "resistance", "target": "Fire Resistance",
                    "mode": "resist", "value": 12.5, "unit": "%",
                }],
            }
            original["special_modifiers_generated"] = True
            original["special_modifier_generation_version"] = 1

            csv_text = serialize_history_csv([pull], [original])
            imported = parse_history_csv(csv_text)
            restored = sync_roll_instances(imported, path=restored_path)
            saved = get_inventory(restored_path)[0]

            self.assertEqual(saved["id"], original["id"])
            self.assertEqual(saved["status"], "equipped")
            self.assertEqual(saved["modifiers"], original["modifiers"])
            self.assertTrue(saved["modifiers_generated"])
            self.assertEqual(saved["modifier_generation_version"], 1)
            self.assertEqual(saved["special_modifiers"], original["special_modifiers"])
            self.assertTrue(saved["special_modifiers_generated"])
            self.assertEqual(saved["special_modifier_generation_version"], 1)


    def test_imported_stored_roll_can_be_equipped(self):
        with tempfile.TemporaryDirectory() as directory:
            inventory_path = os.path.join(directory, "inventory.json")
            pull = {
                "Type": "Skill",
                "Element": "Imported Skill",
                "Rarity": "4.50",
                "Tier": "Elite",
                "LuckValue": 40.0,
                "Luck": "40.00%",
                "Description": "Imported description",
                "Color": "#1172d9",
                "Notes": "",
            }
            original = sync_roll_instances(
                [pull], path=os.path.join(directory, "source.json")
            )[0]
            original["modifiers"] = [
                {"stat": "STR", "kind": "flat", "value": 5}
            ]
            original["modifiers_generated"] = True
            csv_text = serialize_history_csv([pull], [original])

            imported = parse_history_csv(csv_text)
            sync_roll_instances(imported, path=inventory_path)
            equipped = equip_roll(
                original["id"], level=1, path=inventory_path
            )

            self.assertEqual(equipped["status"], "equipped")
            self.assertEqual(
                get_inventory(inventory_path)[0]["modifiers"],
                original["modifiers"],
            )

    def test_legacy_csv_without_optional_fields_is_accepted(self):
        content = (
            "Type,Element,Rarity,Tier\n"
            "Skill,Old Skill,3.5,Rare\n"
        )
        rows = parse_history_csv(content)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Type"], "Skill")
        self.assertEqual(rows[0]["Luck"], "")

    def test_invalid_status_is_rejected(self):
        content = (
            "ID,Status,Type,Element,Rarity,Tier\n"
            "roll-1,broken,Skill,Skill,3.5,Rare\n"
        )
        with self.assertRaises(ValueError):
            parse_history_csv(content)


if __name__ == "__main__":
    unittest.main()
