"""Local narrative character profile and portrait persistence."""
from __future__ import annotations

import json
import os
import tempfile

PROFILE_FILE = os.path.join("characterfiles", "character_profile.json")
PORTRAIT_DIR = os.path.join("characterfiles", "portraits")
ALLOWED_PORTRAIT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_PORTRAIT_BYTES = 10 * 1024 * 1024

SCALAR_FIELDS = (
    "Name", "Race", "Class", "Lineage", "Talent", "Element",
    "Age", "Gender", "Origin", "Appearance", "Personality",
    "Background", "Notes",
)
LIST_FIELDS = ("Factions", "Reputations", "Resistances", "Titles")


def default_character_profile() -> dict:
    profile = {name: "" for name in SCALAR_FIELDS}
    profile.update({name: [] for name in LIST_FIELDS})
    profile["portrait"] = ""
    return profile


def load_character_profile(path: str = PROFILE_FILE) -> dict:
    profile = default_character_profile()
    if not os.path.exists(path):
        return profile
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError("Character profile must be a JSON object.")

        for name in SCALAR_FIELDS:
            value = data.get(name, "")
            if not isinstance(value, (str, int, float)):
                raise ValueError(f"Invalid value for {name}.")
            profile[name] = str(value)

        for name in LIST_FIELDS:
            value = data.get(name, [])
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise ValueError(f"Invalid list for {name}.")
            profile[name] = value

        portrait = data.get("portrait", "")
        if not isinstance(portrait, str):
            raise ValueError("Invalid portrait reference.")
        profile["portrait"] = os.path.basename(portrait)
        if os.path.splitext(profile["portrait"])[1].lower() not in ALLOWED_PORTRAIT_EXTENSIONS:
            profile["portrait"] = ""
        return profile
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            f"Could not read character profile '{path}'. "
            "The original file has been preserved."
        ) from exc


def _atomic_write_json(data: dict, path: str) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=directory,
            delete=False, suffix=".tmp"
        ) as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\\n")
            temp_path = file.name
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def save_character_profile(
    profile: dict,
    portrait_bytes: bytes | None = None,
    portrait_filename: str | None = None,
    path: str = PROFILE_FILE,
    portrait_dir: str = PORTRAIT_DIR,
) -> dict:
    if not isinstance(profile, dict):
        raise TypeError("Character profile must be a dictionary.")

    normalized = default_character_profile()
    for name in SCALAR_FIELDS:
        value = profile.get(name, "")
        if not isinstance(value, (str, int, float)):
            raise ValueError(f"Invalid value for {name}.")
        normalized[name] = str(value)

    for name in LIST_FIELDS:
        value = profile.get(name, [])
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise ValueError(f"Invalid list for {name}.")
        normalized[name] = [item.strip() for item in value if item.strip()]

    existing = load_character_profile(path) if os.path.exists(path) else default_character_profile()
    normalized["portrait"] = existing.get("portrait", "")

    if portrait_bytes is not None:
        if not isinstance(portrait_bytes, bytes) or not portrait_filename:
            raise ValueError("A valid portrait filename and image are required.")
        if not portrait_bytes or len(portrait_bytes) > MAX_PORTRAIT_BYTES:
            raise ValueError("Portrait must be between 1 byte and 10 MB.")
        extension = os.path.splitext(portrait_filename)[1].lower()
        if extension not in ALLOWED_PORTRAIT_EXTENSIONS:
            raise ValueError("Portrait must be PNG, JPG, JPEG or WEBP.")

        os.makedirs(portrait_dir, exist_ok=True)
        portrait_name = "character_portrait" + extension
        portrait_path = os.path.join(portrait_dir, portrait_name)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "wb", dir=portrait_dir, delete=False, suffix=".tmp"
            ) as file:
                file.write(portrait_bytes)
                temp_path = file.name
            os.replace(temp_path, portrait_path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

        # Remove obsolete portrait formats only after the new image is saved.
        for filename in os.listdir(portrait_dir):
            if (
                filename.startswith("character_portrait.")
                and filename != portrait_name
            ):
                os.remove(os.path.join(portrait_dir, filename))
        normalized["portrait"] = portrait_name

    _atomic_write_json(normalized, path)
    return normalized


def get_portrait_path(
    profile: dict | None = None,
    portrait_dir: str = PORTRAIT_DIR,
) -> str | None:
    profile = profile if profile is not None else load_character_profile()
    filename = os.path.basename(str(profile.get("portrait", "")))
    if os.path.splitext(filename)[1].lower() not in ALLOWED_PORTRAIT_EXTENSIONS:
        return None
    path = os.path.join(portrait_dir, filename)
    return path if os.path.isfile(path) else None


def multiline_to_list(value: str) -> list[str]:
    return [line.strip() for line in str(value).splitlines() if line.strip()]


def list_to_multiline(value: list[str]) -> str:
    return "\\n".join(value)
