"""Persistent identity for individual gacha pulls.

The CSV remains the source of pull details and keeps its existing columns.
This module stores one stable ID and inventory status per CSV row in
gacha_log/inventory.json. Identical pulls are distinguished by occurrence.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from collections import defaultdict
from typing import Any, Dict, Iterable, List

INVENTORY_FILE = os.path.join("gacha_log", "inventory.json")
INVENTORY_VERSION = 1
VALID_STATUSES = {"stored", "equipped", "discarded"}


class InventoryDataError(ValueError):
    """Raised when the persistent inventory file cannot be trusted."""


def _fingerprint(pull: Dict[str, Any]) -> str:
    payload = json.dumps(
        pull,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_inventory(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"version": INVENTORY_VERSION, "rolls": []}

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise InventoryDataError(
            f"No se pudo leer el inventario '{path}'. "
            "El archivo original se conserva para evitar pérdida de datos."
        ) from exc

    if not isinstance(data, dict) or not isinstance(data.get("rolls"), list):
        raise InventoryDataError(
            f"El formato de '{path}' no es válido. No se sobrescribió."
        )

    for roll in data["rolls"]:
        if not isinstance(roll, dict) or not roll.get("id"):
            raise InventoryDataError(
                f"Se encontró una instancia inválida en '{path}'. No se sobrescribió."
            )
        if roll.get("status", "stored") not in VALID_STATUSES:
            raise InventoryDataError(
                f"Estado de inventario inválido para la instancia {roll.get('id')}."
            )

    data.setdefault("version", INVENTORY_VERSION)
    return data


def _save_inventory(data: Dict[str, Any], path: str) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=directory,
            delete=False,
            suffix=".tmp",
        ) as temp_file:
            json.dump(data, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
            temp_path = temp_file.name
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def sync_roll_instances(
    history_rows: Iterable[Dict[str, Any]],
    path: str = INVENTORY_FILE,
) -> List[Dict[str, Any]]:
    """Assign stable IDs to history rows without merging repeated pulls.

    Existing IDs and statuses are retained when the same row appears again.
    For byte-for-byte identical rows, occurrence order distinguishes copies.
    """
    data = _load_inventory(path)
    previous = {}
    for saved_roll in data["rolls"]:
        key = (
            saved_roll.get("fingerprint"),
            int(saved_roll.get("occurrence", 0)),
        )
        previous[key] = saved_roll

    occurrences = defaultdict(int)
    synchronized = []
    changed = False

    for row in history_rows:
        if not isinstance(row, dict):
            continue

        pull = dict(row)
        fingerprint = _fingerprint(pull)
        occurrence = occurrences[fingerprint]
        occurrences[fingerprint] += 1
        key = (fingerprint, occurrence)

        saved = previous.get(key)
        if saved:
            instance = dict(saved)
            if instance.get("pull") != pull:
                instance["pull"] = pull
                changed = True
        else:
            instance = {
                "id": uuid.uuid4().hex,
                "fingerprint": fingerprint,
                "occurrence": occurrence,
                "status": "stored",
                "pull": pull,
            }
            data["rolls"].append(instance)
            previous[key] = instance
            changed = True

        synchronized.append(instance)

    if changed:
        _save_inventory(data, path)

    return synchronized


def get_inventory(path: str = INVENTORY_FILE) -> List[Dict[str, Any]]:
    """Return all saved instances, including equipped and discarded ones."""
    return list(_load_inventory(path)["rolls"])


def clear_inventory(path: str = INVENTORY_FILE) -> None:
    """Clear all pull instances when the user explicitly clears history."""
    _save_inventory({"version": INVENTORY_VERSION, "rolls": []}, path)
