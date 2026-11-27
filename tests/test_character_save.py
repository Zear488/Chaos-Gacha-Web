import json
import os
import tempfile
import unittest

from character.profile_manager import default_character_profile, save_character_profile
from logic.character_save import create_character_save, restore_character_save
from logic.roll_manager import sync_roll_instances, get_inventory


class PortableCharacterSaveTests(unittest.TestCase):
    def test_full_save_round_trip_preserves_character_and_gacha_state(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            pull = {
                "Type": "Skill",
                "Element": "★ Test Skill",
                "Rarity": "5.50",
                "Tier": "Epic",
                "LuckValue": 12.5,
                "Luck": "12.50%",
                "Description": "#STATS: STR +2\nA narrative skill.",
                "Color": "#6811d9",
                "Notes": "✨ Boosted Star Bonus — -5.025 TP",
            }
            inventory_path = os.path.join(source_dir, "gacha_log", "inventory.json")
            instances = sync_roll_instances([pull, pull], path=inventory_path)
            instances[0]["status"] = "equipped"
            instances[1]["status"] = "discarded"
            with open(inventory_path, "w", encoding="utf-8") as file:
                json.dump({"version": 1, "rolls": instances}, file)

            os.makedirs(os.path.join(source_dir, "gacha_log"), exist_ok=True)
            with open(os.path.join(source_dir, "gacha_log", "points.json"), "w", encoding="utf-8") as file:
                json.dump({
                    "points": 0.025,
                    "discard_transactions": {
                        instances[1]["id"]: {"tier": "Epic", "amount": 0.075}
                    },
                }, file)
            with open(os.path.join(source_dir, "gacha_log", "repeats.json"), "w", encoding="utf-8") as file:
                json.dump({"Skill::★ Test Skill": True}, file)
            with open(os.path.join(source_dir, "gacha_log", "character_progress.json"), "w", encoding="utf-8") as file:
                json.dump({
                    "version": 1,
                    "allocated": {
                        "STR": 2, "AGI": 0, "INT": 0, "WIS": 0, "CON": 0,
                        "LCK": 0, "Mana": 0, "Vitality": 0, "Defensa": 0, "Ataque": 0,
                    },
                }, file)

            profile = default_character_profile()
            profile["Name"] = "Aster"
            profile["Race"] = "Dragonkin"
            profile["Factions"] = ["Silver Order"]
            save_character_profile(
                profile,
                portrait_bytes=b"test-image-bytes",
                portrait_filename="portrait.png",
                path=os.path.join(source_dir, "characterfiles", "character_profile.json"),
                portrait_dir=os.path.join(source_dir, "characterfiles", "portraits"),
            )
            os.makedirs(os.path.join(source_dir, "characterfiles"), exist_ok=True)
            with open(os.path.join(source_dir, "characterfiles", "stats.json"), "w", encoding="utf-8") as file:
                json.dump({"STR": 1, "AGI": 1}, file)

            package = create_character_save([pull, pull], instances, base_dir=source_dir)
            restored_rows = restore_character_save(package, base_dir=target_dir)

            self.assertEqual(len(restored_rows), 2)
            restored_inventory = get_inventory(
                os.path.join(target_dir, "gacha_log", "inventory.json")
            )
            self.assertEqual(
                [item["id"] for item in restored_inventory],
                [item["id"] for item in instances],
            )
            self.assertEqual(
                [item["status"] for item in restored_inventory],
                ["equipped", "discarded"],
            )
            with open(os.path.join(target_dir, "characterfiles", "character_profile.json"), encoding="utf-8") as file:
                restored_profile = json.load(file)
            self.assertEqual(restored_profile["Name"], "Aster")
            self.assertEqual(restored_profile["Factions"], ["Silver Order"])
            with open(os.path.join(target_dir, "gacha_log", "character_progress.json"), encoding="utf-8") as file:
                restored_progress = json.load(file)
            self.assertEqual(restored_progress["allocated"]["STR"], 2)
            with open(os.path.join(target_dir, "gacha_log", "points.json"), encoding="utf-8") as file:
                restored_points = json.load(file)
            self.assertEqual(restored_points["points"], 0.025)
            self.assertTrue(os.path.isfile(os.path.join(
                target_dir, "characterfiles", "portraits", "character_portrait.png"
            )))

    def test_invalid_package_does_not_overwrite_local_files(self):
        with tempfile.TemporaryDirectory() as directory:
            os.makedirs(os.path.join(directory, "gacha_log"), exist_ok=True)
            target = os.path.join(directory, "gacha_log", "points.json")
            with open(target, "w", encoding="utf-8") as file:
                file.write('{"points": 7, "discard_transactions": {}}')

            with self.assertRaises(ValueError):
                restore_character_save(b"not-a-zip", base_dir=directory)

            with open(target, encoding="utf-8") as file:
                self.assertEqual(json.load(file)["points"], 7)


if __name__ == "__main__":
    unittest.main()
