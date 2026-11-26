import unittest
from unittest.mock import patch

from character.character import Character, _has_star_bonus
from character.stats_manager import StatsManager


class CharacterRandomModifierIntegrationTests(unittest.TestCase):
    def test_element_and_notes_marker_count_as_one_star(self):
        self.assertTrue(_has_star_bonus({
            "Element": "★ Flame",
            "Notes": "✨ Boosted Star Bonus — -1 TP",
        }))

    def test_notes_can_identify_star_when_element_has_no_prefix(self):
        self.assertTrue(_has_star_bonus({
            "Element": "Flame",
            "Notes": "✨ Boosted Star Bonus — -1 TP",
        }))

    def test_equipped_modifiers_and_legacy_stats_are_combined(self):
        character = Character()
        character.stats = StatsManager({"STR": 20})
        character.equipped_rolls = [{
            "id": "equipped-starred",
            "status": "equipped",
            "pull": {
                "Type": "Skill",
                "Element": "★ Flame",
                "Notes": "✨ Boosted Star Bonus — -1 TP",
                "Description": "#STATS: STR +3",
            },
            "modifiers": [
                {"stat": "STR", "kind": "flat", "value": 5},
                {"stat": "STR", "kind": "percent", "value": 5},
            ],
        }]
        character.apply_gacha_items()
        self.assertAlmostEqual(character.stats.finalize()["STR"], 29.875, places=3)


if __name__ == "__main__":
    unittest.main()
