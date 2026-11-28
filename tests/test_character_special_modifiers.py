import unittest

from character.character import Character
from character.stats_manager import StatsManager


class CharacterSpecialModifierTests(unittest.TestCase):
    def test_equipped_special_effects_project_and_receive_star_bonus(self):
        character = Character()
        character.stats = StatsManager({"STR": 10})
        character.equipped_rolls = [
            {
                "status": "equipped",
                "pull": {"Type": "Skill", "Element": "★ Starred Skill", "Notes": ""},
                "special_modifiers": {
                    "family": "resistances",
                    "effects": [{
                        "type": "resistance",
                        "target": "Fire Resistance",
                        "mode": "resist",
                        "value": 10.0,
                        "unit": "%",
                    }],
                },
            },
            {
                "status": "equipped",
                "pull": {"Type": "Trait", "Element": "Fortune Trait", "Notes": ""},
                "special_modifiers": {
                    "family": "unusual",
                    "effects": [{
                        "type": "attribute",
                        "target": "Fortune / Karma",
                        "mode": "bonus",
                        "value": 5.0,
                        "unit": "%",
                    }],
                },
            },
        ]

        character.apply_gacha_items()

        self.assertEqual(character.resistances["Fire Resistance"], 11.0)
        self.assertEqual(
            character.other_fields["Special Attributes"][0]["value"], 5.5
        )
        self.assertEqual(
            len(character.special_effects["resistances"]), 1
        )
        self.assertEqual(
            character.special_effects["unusual"][0]["base_value"], 5.0
        )


if __name__ == "__main__":
    unittest.main()
