import os
import tempfile
import unittest

from character.progression import (
    allocate_stat_points,
    get_level_from_pulls,
    get_progress_to_next_level,
    load_character_progress,
    points_earned_for_level,
    pulls_required_for_level,
)


class PullBasedProgressionTests(unittest.TestCase):
    def test_cumulative_pull_thresholds(self):
        self.assertEqual(pulls_required_for_level(1), 0)
        self.assertEqual(pulls_required_for_level(2), 2)
        self.assertEqual(pulls_required_for_level(3), 5)
        self.assertEqual(pulls_required_for_level(4), 9)
        self.assertEqual(pulls_required_for_level(5), 14)

    def test_level_boundaries(self):
        self.assertEqual(get_level_from_pulls(0), 1)
        self.assertEqual(get_level_from_pulls(1), 1)
        self.assertEqual(get_level_from_pulls(2), 2)
        self.assertEqual(get_level_from_pulls(4), 2)
        self.assertEqual(get_level_from_pulls(5), 3)
        self.assertEqual(get_level_from_pulls(8), 3)
        self.assertEqual(get_level_from_pulls(9), 4)

    def test_level_up_points_accumulate_by_reached_level(self):
        self.assertEqual(points_earned_for_level(1), 0)
        self.assertEqual(points_earned_for_level(2), 2)
        self.assertEqual(points_earned_for_level(3), 5)
        self.assertEqual(points_earned_for_level(4), 9)

    def test_progress_to_next_level(self):
        progress = get_progress_to_next_level(2)
        self.assertEqual(progress["level"], 2)
        self.assertEqual(progress["pulls_into_level"], 0)
        self.assertEqual(progress["pulls_needed_for_next_level"], 3)
        self.assertEqual(progress["pulls_for_this_level"], 3)

    def test_allocation_is_persistent_and_cannot_exceed_earned_points(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "character_progress.json")
            allocate_stat_points("STR", 2, pull_count=2, path=path)
            allocate_stat_points("AGI", 3, pull_count=5, path=path)

            saved = load_character_progress(path)
            self.assertEqual(saved["allocated"]["STR"], 2)
            self.assertEqual(saved["allocated"]["AGI"], 3)
            self.assertEqual(sum(saved["allocated"].values()), 5)

            with self.assertRaises(ValueError):
                allocate_stat_points("INT", 1, pull_count=5, path=path)

    def test_invalid_stat_and_negative_pull_count_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "character_progress.json")
            with self.assertRaises(ValueError):
                allocate_stat_points("Unknown", 1, pull_count=2, path=path)
        with self.assertRaises(ValueError):
            get_level_from_pulls(-1)


if __name__ == "__main__":
    unittest.main()
