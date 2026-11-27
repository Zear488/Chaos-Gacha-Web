"""Portable, validated character save packages for local restore."""
from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile

from logic.history_csv import parse_history_csv, serialize_history_csv
from logic.roll_manager import INVENTORY_FILE, VALID_STATUSES, _fingerprint
from logic.tracker import POINTS_FILE, REPEATS_FILE
from character.progression import PROGRESS_FILE, STAT_NAMES
from character.profile_manager import (
    PROFILE_FILE,
    PORTRAIT_DIR,
    ALLOWED_PORTRAIT_EXTENSIONS,
    default_character_profile,
    get_portrait_path,
    load_character_profile,
)

SAVE_VERSION = 1
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_PORTRAIT_BYTES = 10 * 1024 * 1024


def _paths(base_dir: str) -> dict:
    return {
        "history": os.path.join(base_dir, "logs", "gacha_history.csv"),
        "inventory": os.path.join(base_dir, INVENTORY_FILE),
        "points": os.path.join(base_dir, POINTS_FILE),
        "repeats": os.path.join(base_dir, REPEATS_FILE),
        "progress": os.path.join(base_dir, PROGRESS_FILE),
        "profile": os.path.join(base_dir, PROFILE_FILE),
        "stats": os.path.join(base_dir, "characterfiles", "stats.json"),
        "portrait_dir": os.path.join(base_dir, PORTRAIT_DIR),
    }


def _read_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _json_bytes(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def create_character_save(history_rows, inventory_instances, base_dir: str = ".") -> bytes:
    """Create a ZIP containing history, inventory, TP, progression and profile."""
    paths = _paths(base_dir)
    inventory_default = {"version": 1, "rolls": inventory_instances}
    points_default = {"points": 0, "discard_transactions": {}}
    progress_default = {"version": 1, "allocated": {name: 0 for name in STAT_NAMES}}
    profile_default = default_character_profile()
    stats_default = {
        "STR": 1, "AGI": 1, "INT": 1, "WIS": 1, "CON": 1,
        "LCK": 1, "Mana": 1, "Vitality": 1, "Defensa": 1, "Ataque": 1,
    }

    inventory = _read_json(paths["inventory"], inventory_default)
    points = _read_json(paths["points"], points_default)
    repeats = _read_json(paths["repeats"], {})
    progress = _read_json(paths["progress"], progress_default)
    profile = (
        load_character_profile(paths["profile"])
        if os.path.exists(paths["profile"])
        else profile_default
    )
    stats = _read_json(paths["stats"], stats_default)

    history_csv = serialize_history_csv(history_rows, inventory_instances)
    members = {
        "manifest.json": _json_bytes({
            "format": "ChaosGachaCharacterSave",
            "version": SAVE_VERSION,
        }),
        "gacha_history.csv": history_csv.encode("utf-8-sig"),
        "inventory.json": _json_bytes(inventory),
        "points.json": _json_bytes(points),
        "repeats.json": _json_bytes(repeats),
        "character_progress.json": _json_bytes(progress),
        "character_profile.json": _json_bytes(profile),
        "stats.json": _json_bytes(stats),
    }

    portrait_path = get_portrait_path(profile, paths["portrait_dir"])
    if portrait_path:
        extension = os.path.splitext(portrait_path)[1].lower()
        if extension not in ALLOWED_PORTRAIT_EXTENSIONS:
            raise ValueError("Unsupported portrait extension in local profile.")
        with open(portrait_path, "rb") as file:
            portrait = file.read()
        if len(portrait) > MAX_PORTRAIT_BYTES:
            raise ValueError("Character portrait exceeds the 10 MB limit.")
        members["portrait/" + os.path.basename(portrait_path)] = portrait

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    result = output.getvalue()
    if len(result) > MAX_ARCHIVE_BYTES:
        raise ValueError("Character save package exceeds the 50 MB limit.")
    return result


def _decode_and_validate(content: bytes) -> tuple[dict, list]:
    if not isinstance(content, bytes) or not content:
        raise ValueError("The character save file is empty or invalid.")
    if len(content) > MAX_ARCHIVE_BYTES:
        raise ValueError("Character save package exceeds the 50 MB limit.")

    try:
        archive = zipfile.ZipFile(io.BytesIO(content), "r")
    except zipfile.BadZipFile as exc:
        raise ValueError("The character save must be a valid ZIP package.") from exc

    with archive:
        names = set(archive.namelist())
        required = {
            "manifest.json", "gacha_history.csv", "inventory.json",
            "points.json", "repeats.json", "character_progress.json",
            "character_profile.json", "stats.json",
        }
        if not required.issubset(names):
            missing = sorted(required - names)
            raise ValueError("Character save is missing: " + ", ".join(missing))
        if any(name.startswith("/") or ".." in name.split("/") for name in names):
            raise ValueError("Unsafe path found inside character save package.")
        if any(info.file_size > MAX_ARCHIVE_BYTES for info in archive.infolist()):
            raise ValueError("A file inside the character save is too large.")

        def read_json(name):
            try:
                return json.loads(archive.read(name).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"Invalid JSON file in save package: {name}") from exc

        manifest = read_json("manifest.json")
        if (
            not isinstance(manifest, dict)
            or manifest.get("format") != "ChaosGachaCharacterSave"
            or manifest.get("version") != SAVE_VERSION
        ):
            raise ValueError("Unsupported character save format or version.")

        csv_bytes = archive.read("gacha_history.csv")
        try:
            rows = parse_history_csv(csv_bytes.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError(f"Invalid gacha history in save package: {exc}") from exc

        inventory = read_json("inventory.json")
        if not isinstance(inventory, dict) or not isinstance(inventory.get("rolls"), list):
            raise ValueError("Invalid inventory.json in character save.")
        inventory_by_id = {}
        for instance in inventory["rolls"]:
            if not isinstance(instance, dict):
                raise ValueError("Invalid inventory instance in character save.")
            roll_id = instance.get("id")
            if not isinstance(roll_id, str) or not roll_id or roll_id in inventory_by_id:
                raise ValueError("Missing or duplicate inventory ID in character save.")
            if instance.get("status", "stored") not in VALID_STATUSES:
                raise ValueError(f"Invalid inventory status for ID {roll_id}.")
            if not isinstance(instance.get("pull"), dict):
                raise ValueError(f"Invalid pull data for ID {roll_id}.")
            inventory_by_id[roll_id] = instance

        seen_csv_ids = set()
        for row in rows:
            roll_id = row.get("_roll_id")
            if not roll_id or roll_id in seen_csv_ids:
                raise ValueError("Complete save history must contain unique pull IDs.")
            seen_csv_ids.add(roll_id)
            instance = inventory_by_id.get(roll_id)
            if instance is None:
                raise ValueError(f"History pull ID {roll_id} is missing from inventory.")
            if instance.get("status", "stored") != row.get("_roll_status", "stored"):
                raise ValueError(f"Inventory status mismatch for pull ID {roll_id}.")

        points = read_json("points.json")
        if not isinstance(points, dict):
            raise ValueError("Invalid points.json in character save.")
        try:
            float(points.get("points", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid TP balance in character save.") from exc
        transactions = points.get("discard_transactions", {})
        if not isinstance(transactions, dict):
            raise ValueError("Invalid TP transaction ledger in character save.")
        for roll_id, transaction in transactions.items():
            if not isinstance(roll_id, str) or not isinstance(transaction, dict):
                raise ValueError("Invalid TP transaction in character save.")
            try:
                float(transaction.get("amount", 0))
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid TP transaction amount.") from exc

        repeats = read_json("repeats.json")
        if not isinstance(repeats, dict):
            raise ValueError("Invalid repeats.json in character save.")

        progress = read_json("character_progress.json")
        if not isinstance(progress, dict) or not isinstance(progress.get("allocated"), dict):
            raise ValueError("Invalid character progression in save package.")
        for stat in STAT_NAMES:
            value = progress["allocated"].get(stat, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"Invalid allocated points for {stat}.")

        profile = read_json("character_profile.json")
        if not isinstance(profile, dict):
            raise ValueError("Invalid character profile in save package.")
        profile = default_character_profile() | profile
        for field in ("Factions", "Reputations", "Resistances", "Titles"):
            if not isinstance(profile.get(field), list) or not all(
                isinstance(item, str) for item in profile[field]
            ):
                raise ValueError(f"Invalid profile list: {field}.")
        portrait_name = os.path.basename(str(profile.get("portrait", "")))
        profile["portrait"] = portrait_name
        portrait_member = "portrait/" + portrait_name if portrait_name else None
        portrait_members = [name for name in names if name.startswith("portrait/")]
        if portrait_name:
            extension = os.path.splitext(portrait_name)[1].lower()
            if extension not in ALLOWED_PORTRAIT_EXTENSIONS or portrait_member not in names:
                raise ValueError("The profile references a missing or unsupported portrait.")
            if len(archive.read(portrait_member)) > MAX_PORTRAIT_BYTES:
                raise ValueError("Character portrait exceeds the 10 MB limit.")
        elif portrait_members:
            raise ValueError("Portrait file exists but is not referenced by the profile.")

        stats = read_json("stats.json")
        if not isinstance(stats, dict):
            raise ValueError("Invalid stats.json in character save.")
        for name, value in stats.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Invalid base stat value for {name}.")

        allowed = required | set(portrait_members)
        unexpected = names - allowed
        if unexpected:
            raise ValueError("Unexpected files in character save: " + ", ".join(sorted(unexpected)))

        files = {
            "logs/gacha_history.csv": csv_bytes,
            "gacha_log/inventory.json": archive.read("inventory.json"),
            "gacha_log/points.json": archive.read("points.json"),
            "gacha_log/repeats.json": archive.read("repeats.json"),
            "gacha_log/character_progress.json": archive.read("character_progress.json"),
            "characterfiles/character_profile.json": _json_bytes(profile),
            "characterfiles/stats.json": archive.read("stats.json"),
        }
        if portrait_member:
            files["characterfiles/portraits/" + portrait_name] = archive.read(portrait_member)
        return files, rows


def restore_character_save(content: bytes, base_dir: str = ".") -> list:
    """Validate the entire package, then replace local files with rollback."""
    files, rows = _decode_and_validate(content)
    staged = {}
    backups = {}
    created = set()
    old_portraits = []
    profile_path = os.path.join(base_dir, "characterfiles", "character_profile.json")
    portrait_dir = os.path.join(base_dir, "characterfiles", "portraits")

    if os.path.isdir(portrait_dir):
        old_portraits = [
            os.path.join(portrait_dir, name)
            for name in os.listdir(portrait_dir)
            if name.startswith("character_portrait.")
        ]

    try:
        for relative, data in files.items():
            target = os.path.join(base_dir, relative)
            directory = os.path.dirname(target) or base_dir
            os.makedirs(directory, exist_ok=True)
            if os.path.exists(target):
                with open(target, "rb") as file:
                    backups[target] = file.read()
            else:
                created.add(target)

            with tempfile.NamedTemporaryFile(
                "wb", dir=directory, delete=False, suffix=".restore"
            ) as file:
                file.write(data)
                staged[target] = file.name

        for target, temp_path in staged.items():
            os.replace(temp_path, target)

        # Remove stale portrait formats only after all replacements succeed.
        new_portrait_targets = {
            os.path.join(base_dir, relative)
            for relative in files
            if relative.startswith("characterfiles/portraits/")
        }
        for old_path in old_portraits:
            if old_path not in new_portrait_targets and os.path.exists(old_path):
                os.remove(old_path)

    except Exception:
        for target in created:
            if os.path.exists(target):
                os.remove(target)
        for target, data in backups.items():
            directory = os.path.dirname(target) or "."
            os.makedirs(directory, exist_ok=True)
            with open(target, "wb") as file:
                file.write(data)
        raise
    finally:
        for temp_path in staged.values():
            if os.path.exists(temp_path):
                os.remove(temp_path)

    return rows
