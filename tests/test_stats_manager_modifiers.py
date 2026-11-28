import unittest

from character.stats_manager import StatsManager


class StatsManagerModifierTests(unittest.TestCase):
    def setUp(self):
        self.manager = StatsManager({"STR": 20, "Mana": 1})

    def test_flat_then_percent(self):
        self.manager.add_random_modifiers([
            {"stat": "STR", "kind": "flat", "value": 5},
            {"stat": "STR", "kind": "percent", "value": 5},
        ])
        self.assertAlmostEqual(self.manager.finalize()["STR"], 26.25, places=2)

    def test_percent_modifiers_are_added_not_compounded(self):
        self.manager.add_random_modifiers([
            {"stat": "STR", "kind": "percent", "value": 5},
            {"stat": "STR", "kind": "percent", "value": 10},
        ])
        self.assertAlmostEqual(self.manager.finalize()["STR"], 23.0, places=2)

    def test_star_bonus_amplifies_only_random_modifier_contribution(self):
        self.manager.add_stats({"STR": 3})
        self.manager.add_random_modifiers([
            {"stat": "STR", "kind": "flat", "value": 5},
            {"stat": "STR", "kind": "percent", "value": 5},
        ])
        final = self.manager.finalize(star_count=2)
        # Base 20 + descriptive 3 + random contribution 6.25 * 1.20.
        self.assertAlmostEqual(final["STR"], 30.50, places=2)
        # A stat without random modifiers is not affected by star bonuses.
        self.assertAlmostEqual(final["Mana"], 1.00, places=2)

    def test_star_bonus_is_capped_at_four(self):
        self.manager.add_random_modifiers([
            {"stat": "STR", "kind": "flat", "value": 10},
        ])
        self.assertEqual(
            self.manager.finalize(star_count=99)["STR"],
            self.manager.finalize(star_count=4)["STR"],
        )
        # Four equipped stars mean +40% to the random contribution.
        self.assertAlmostEqual(self.manager.finalize(star_count=4)["STR"], 34.0, places=2)

    def test_case_insensitive_stat_names(self):
        self.manager.add_random_modifiers([
            {"stat": "str", "kind": "flat", "value": 2},
        ])
        self.assertEqual(self.manager.finalize()["STR"], 22)

    def test_negative_random_modifiers_are_rejected(self):
        with self.assertRaises(ValueError):
            self.manager.add_random_modifiers([
                {"stat": "STR", "kind": "flat", "value": -1},
            ])


if __name__ == "__main__":
    unittest.main()
