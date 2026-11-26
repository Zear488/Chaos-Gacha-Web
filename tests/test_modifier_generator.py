import json
import os
import random
import tempfile
import unittest
from unittest.mock import patch

from logic.modifier_generator import (
    STATS,
    TIER_RULES,
    generate_modifiers,
    luck_score,
    modifier_count,
    roll_magnitude,
)
from logic.roll_manager import sync_roll_instances, get_inventory


class ModifierGeneratorTests(unittest.TestCase):
    def test_luck_value_is_inverted_and_clamped(self):
        self.assertEqual(luck_score({"LuckValue": 0}), 100)
        self.assertEqual(luck_score({"LuckValue": 100}), 0)
        self.assertEqual(luck_score({"LuckValue": -20}), 100)
        self.assertEqual(luck_score({"LuckValue": 140}), 0)

    def test_tier_space_ranges(self):
        expected = {
            "Trash": (0, 0), "Common": (1, 1), "Uncommon": (1, 2),
            "Rare": (2, 2), "Elite": (2, 3), "Epic": (3, 3),
            "Legendary": (3, 4), "Mythical": (4, 4),
            "Divine": (4, 5), "Transcendent": (5, 6),
        }
        self.assertEqual(
            {tier: (values[0], values[1]) for tier, values in TIER_RULES.items()},
            expected,
        )

    def test_extra_slot_probability_uses_luck(self):
        class FixedRandom:
            def __init__(self, value):
                self.value = value
            def random(self):
                return self.value

        self.assertEqual(modifier_count("Uncommon", 0, FixedRandom(0.19)), 2)
        self.assertEqual(modifier_count("Uncommon", 0, FixedRandom(0.20)), 1)
        self.assertEqual(modifier_count("Uncommon", 100, FixedRandom(0.44)), 2)
        self.assertEqual(modifier_count("Uncommon", 100, FixedRandom(0.45)), 1)

    def test_magnitude_is_bounded_and_luck_shifts_distribution(self):
        class FixedRandom:
            def __init__(self, value):
                self.value = value
            def random(self):
                return self.value

        low_luck = roll_magnitude((2, 4), 0, FixedRandom(0.5))
        high_luck = roll_magnitude((2, 4), 100, FixedRandom(0.5))
        self.assertGreaterEqual(low_luck, 2)
        self.assertLessEqual(low_luck, 4)
        self.assertGreaterEqual(high_luck, 2)
        self.assertLessEqual(high_luck, 4)
        self.assertGreater(high_luck, low_luck)

    def test_generation_uses_distinct_stat_kind_pairs(self):
        pull = {"Type": "Skill", "Tier": "Transcendent", "LuckValue": 0}
        modifiers = generate_modifiers(pull, random.Random(4))
        pairs = [(item["stat"], item["kind"]) for item in modifiers]
        self.assertEqual(len(pairs), len(set(pairs)))
        self.assertLessEqual(len(modifiers), 6)
        self.assertTrue(all(item["stat"] in STATS for item in modifiers))
        self.assertTrue(all(item["kind"] in {"flat", "percent"} for item in modifiers))

    def test_item_and_trash_do_not_receive_modifiers(self):
        self.assertEqual(
            generate_modifiers({"Type": "Item", "Tier": "Divine"}),
            [],
        )
        self.assertEqual(
            generate_modifiers({"Type": "Skill", "Tier": "Trash"}),
            [],
        )

    def test_sync_persists_modifiers_once_per_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "inventory.json")
            pull = {
                "Type": "Skill", "Element": "Persist Test",
                "Tier": "Rare", "LuckValue": 30,
            }
            first = sync_roll_instances([pull], path=path)
            saved_first = first[0]["modifiers"]
            second = sync_roll_instances([pull], path=path)
            self.assertEqual(second[0]["id"], first[0]["id"])
            self.assertEqual(second[0]["modifiers"], saved_first)
            self.assertTrue(second[0]["modifiers_generated"])
            self.assertEqual(get_inventory(path)[0]["modifiers"], saved_first)

    def test_legacy_inventory_instance_gets_modifiers_on_next_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "inventory.json")
            with open(path, "w", encoding="utf-8") as file:
                json.dump({
                    "version": 1,
                    "rolls": [{
                        "id": "legacy-id", "fingerprint": "old",
                        "occurrence": 0, "status": "stored",
                        "pull": {
                            "Type": "Skill", "Element": "Old",
                            "Tier": "Common", "LuckValue": 50,
                        },
                    }],
                }, file)
            sync_roll_instances([{
                "Type": "Skill", "Element": "Old",
                "Tier": "Common", "LuckValue": 50,
            }], path=path)
            saved = get_inventory(path)[0]
            self.assertEqual(saved["id"], "legacy-id")
            self.assertTrue(saved["modifiers_generated"])
            self.assertEqual(len(saved["modifiers"]), 1)


if __name__ == "__main__":
    unittest.main()
