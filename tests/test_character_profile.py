import os
import tempfile
import unittest

from character.profile_manager import (
    load_character_profile,
    save_character_profile,
    get_portrait_path,
    default_character_profile,
    multiline_to_list,
    list_to_multiline,
)


class CharacterProfileTests(unittest.TestCase):
    def test_profile_fields_persist_locally(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "profile.json")
            profile = default_character_profile()
            profile["Name"] = "Aster"
            profile["Race"] = "Dragonkin"
            profile["Factions"] = ["Silver Order", "Northern Court"]
            profile["Resistances"] = ["Fire Resistance: 20%", "Ice Resistance: 10%"]

            save_character_profile(profile, path=path)
            loaded = load_character_profile(path)

            self.assertEqual(loaded["Name"], "Aster")
            self.assertEqual(loaded["Race"], "Dragonkin")
            self.assertEqual(loaded["Factions"], ["Silver Order", "Northern Court"])
            self.assertEqual(
                loaded["Resistances"],
                ["Fire Resistance: 20%", "Ice Resistance: 10%"],
            )

    def test_portrait_is_saved_and_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "profile.json")
            portrait_dir = os.path.join(directory, "portraits")
            profile = default_character_profile()
            profile["Name"] = "Aster"

            saved = save_character_profile(
                profile,
                portrait_bytes=b"fake-image-data",
                portrait_filename="portrait.png",
                path=path,
                portrait_dir=portrait_dir,
            )
            portrait_path = get_portrait_path(saved, portrait_dir)

            self.assertIsNotNone(portrait_path)
            with open(portrait_path, "rb") as file:
                self.assertEqual(file.read(), b"fake-image-data")

    def test_rejects_unsupported_portrait_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "profile.json")
            with self.assertRaises(ValueError):
                save_character_profile(
                    default_character_profile(),
                    portrait_bytes=b"image",
                    portrait_filename="portrait.exe",
                    path=path,
                    portrait_dir=os.path.join(directory, "portraits"),
                )

    def test_multiline_list_conversion(self):
        values = ["Silver Order", "Northern Court"]
        self.assertEqual(multiline_to_list(list_to_multiline(values)), values)


if __name__ == "__main__":
    unittest.main()
