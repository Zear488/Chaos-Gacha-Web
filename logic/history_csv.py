"""Lossless CSV export/import for gacha history and per-roll metadata."""
from __future__ import annotations

import csv
import io
import json

from .roll_manager import _fingerprint

PULL_REQUIRED = {"Type", "Element", "Rarity", "Tier"}
PULL_OPTIONAL = (
    "LuckValue", "Luck", "Description", "Color", "Notes",
)
EXPORT_COLUMNS = (
    "ID", "Status", "Type", "Element", "Rarity", "Tier",
    "LuckValue", "Luck", "Description", "Color", "Notes",
    "Modifiers", "ModifiersGenerated", "ModifierGenerationVersion",
)
VALID_STATUSES = {"stored", "equipped", "discarded"}


def parse_history_csv(content):
    """Parse complete exports and older minimal pull CSVs.

    New metadata columns are translated to private sync hints so they are
    never included in the pull fingerprint or sent to the TP tracker.
    """
    if not isinstance(content, str):
        raise TypeError("CSV content must be text.")
    sample = content[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("The CSV file has no header.")
    headers = {name.strip() for name in reader.fieldnames if name}
    missing = PULL_REQUIRED - headers
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))

    rows = []
    seen_ids = set()
    for line_number, raw in enumerate(reader, start=2):
        if not raw or not any(value not in (None, "") for value in raw.values()):
            continue
        row = {(key or "").strip(): value for key, value in raw.items() if key}
        pull = {key: row.get(key, "") for key in PULL_REQUIRED}
        for key in PULL_OPTIONAL:
            pull[key] = row.get(key, "") or ""
        if not pull["Luck"] and pull["LuckValue"] != "":
            pull["Luck"] = f"{pull['LuckValue']}%"
        if not pull["LuckValue"] and pull["Luck"]:
            pull["LuckValue"] = str(pull["Luck"]).replace("%", "").strip()

        roll_id = str(row.get("ID", "") or "").strip()
        status = str(row.get("Status", "") or "stored").strip().lower()
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid Status '{status}' on CSV line {line_number}.")

        if roll_id:
            if roll_id in seen_ids:
                raise ValueError("Duplicate roll ID on CSV line " + str(line_number) + ".")
            seen_ids.add(roll_id)
            pull["_roll_id"] = roll_id
            pull["_roll_status"] = status

        modifiers_text = row.get("Modifiers", "")
        if modifiers_text:
            try:
                modifiers = json.loads(modifiers_text)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"Invalid Modifiers JSON on CSV line {line_number}."
                ) from exc
            if not isinstance(modifiers, list):
                raise ValueError(
                    f"Modifiers must be a JSON list on CSV line {line_number}."
                )
            for modifier in modifiers:
                if not isinstance(modifier, dict):
                    raise ValueError("Invalid modifier on CSV line " + str(line_number) + ".")
                if not isinstance(modifier.get("stat"), str) or modifier.get("kind") not in {"flat", "percent"}:
                    raise ValueError("Invalid modifier fields on CSV line " + str(line_number) + ".")
                value = modifier.get("value")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                    raise ValueError("Invalid modifier value on CSV line " + str(line_number) + ".")
            pull["_roll_modifiers"] = modifiers
            pull["_roll_modifiers_generated"] = (
                str(row.get("ModifiersGenerated", "true")).strip().lower()
                in {"true", "1", "yes"}
            )
            version = row.get("ModifierGenerationVersion", "")
            if version:
                try:
                    pull["_roll_modifier_generation_version"] = int(version)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid ModifierGenerationVersion on CSV line {line_number}."
                    ) from exc
        rows.append(pull)
    return rows


def strip_import_metadata(row):
    """Return only the original gacha pull fields."""
    return {key: value for key, value in row.items() if not key.startswith("_roll_")}


def serialize_history_csv(history_rows, inventory_instances):
    """Serialize pulls plus their matching persistent ID/status/modifiers."""
    inventory_by_occurrence = {}
    for instance in inventory_instances:
        key = (
            instance.get("fingerprint"),
            int(instance.get("occurrence", 0)),
        )
        inventory_by_occurrence[key] = instance

    occurrences = {}
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output, fieldnames=EXPORT_COLUMNS, extrasaction="ignore"
    )
    writer.writeheader()

    for pull in history_rows:
        clean_pull = strip_import_metadata(pull)
        fingerprint = _fingerprint(clean_pull)
        occurrence = occurrences.get(fingerprint, 0)
        occurrences[fingerprint] = occurrence + 1
        instance = inventory_by_occurrence.get((fingerprint, occurrence), {})
        modifiers = instance.get("modifiers", [])
        writer.writerow({
            "ID": instance.get("id", ""),
            "Status": instance.get("status", "stored"),
            **{key: clean_pull.get(key, "") for key in EXPORT_COLUMNS if key in clean_pull},
            "Modifiers": json.dumps(modifiers, ensure_ascii=False, separators=(",", ":")),
            "ModifiersGenerated": str(bool(instance.get("modifiers_generated", False))).lower(),
            "ModifierGenerationVersion": instance.get("modifier_generation_version", ""),
        })
    return output.getvalue()
