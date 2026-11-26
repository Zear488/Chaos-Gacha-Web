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

from .tracker import DISCARD_TP_BY_TIER
from .modifier_generator import ensure_roll_modifiers

INVENTORY_FILE = os.path.join("gacha_log", "inventory.json")
INVENTORY_VERSION = 1
VALID_STATUSES = {"stored", "equipped", "discarded"}


class InventoryDataError(ValueError):
    """Raised when the persistent inventory file cannot be trusted."""


def _fingerprint(pull: Dict[str, Any]) -> str:
    # CSV import may turn values such as "3.50" into 3.5 and
    # "50.00%" into 50.0. Normalize these fields so IDs survive reloads.
    normalized = {}
    for key, value in pull.items():
        if value is None or str(value).strip().lower() in {"nan", "none"}:
            normalized[key] = ""
            continue

        if key in {"Rarity", "Luck", "LuckValue"}:
            numeric_text = str(value).strip().replace("%", "")
            try:
                normalized[key] = f"{float(numeric_text):.2f}"
                continue
            except (TypeError, ValueError):
                pass

        normalized[key] = str(value).strip()

    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
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

        # Generate once for eligible legacy/new instances and persist on the instance.
        if ensure_roll_modifiers(instance):
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



class InventoryStateError(ValueError):
    """Raised when an inventory state transition is not allowed."""


EQUIPMENT_CATEGORIES = ("Ability", "Familiar", "Skill", "Trait")


def get_equipment_slots(level: int) -> int:
    """Return the slot capacity PER CATEGORY: 3 base, +1 per 10 levels."""
    if isinstance(level, bool) or not isinstance(level, int) or level < 0:
        raise ValueError("El nivel debe ser un entero mayor o igual a 0.")
    return 3 + (level // 10)


def _equipment_category(roll: Dict[str, Any]) -> str:
    """Resolve a roll's equipable category without changing its stored Type."""
    pull = roll.get("pull", {})
    roll_type = pull.get("Type", "") if isinstance(pull, dict) else ""
    for category in EQUIPMENT_CATEGORIES:
        if str(roll_type).strip().casefold() == category.casefold():
            return category
    raise InventoryStateError(
        f"La categoría '{roll_type}' no tiene espacios de equipamiento. "
        f"Categorías equipables: {', '.join(EQUIPMENT_CATEGORIES)}."
    )


def _safe_equipment_category(roll: Dict[str, Any]) -> str:
    """Return an empty category for legacy/non-equipable inventory entries."""
    try:
        return _equipment_category(roll)
    except InventoryStateError:
        return ""


def equip_roll(
    roll_id: str,
    level: int,
    path: str = INVENTORY_FILE,
) -> Dict[str, Any]:
    """Equip one stored pull instance by its unique ID.

    The level is supplied by the caller because the repository does not yet
    define a single authoritative character-level source.
    """
    if not isinstance(roll_id, str) or not roll_id.strip():
        raise ValueError("Se requiere un ID de tirada válido.")

    slots = get_equipment_slots(level)
    data = _load_inventory(path)
    target = None

    for roll in data["rolls"]:
        if roll.get("id") == roll_id:
            target = roll
            break

    if target is None:
        raise InventoryStateError(f"No existe una tirada con ID '{roll_id}'.")

    status = target.get("status", "stored")
    if status == "discarded":
        raise InventoryStateError("No se puede equipar una tirada descartada.")
    if status == "equipped":
        raise InventoryStateError("Esta tirada ya está equipada.")

    category = _equipment_category(target)
    equipped_count = sum(
        1 for roll in data["rolls"]
        if roll.get("status", "stored") == "equipped"
        and _safe_equipment_category(roll) == category
    )
    if equipped_count >= slots:
        raise InventoryStateError(
            f"No hay espacios disponibles para {category}: "
            f"{equipped_count}/{slots} ocupados."
        )

    target["status"] = "equipped"
    _save_inventory(data, path)
    return dict(target)


def unequip_roll(
    roll_id: str,
    path: str = INVENTORY_FILE,
) -> Dict[str, Any]:
    """Return one equipped pull instance to stored inventory by unique ID."""
    if not isinstance(roll_id, str) or not roll_id.strip():
        raise ValueError("Se requiere un ID de tirada válido.")

    data = _load_inventory(path)
    for roll in data["rolls"]:
        if roll.get("id") == roll_id:
            if roll.get("status", "stored") != "equipped":
                raise InventoryStateError("La tirada no está equipada.")
            roll["status"] = "stored"
            _save_inventory(data, path)
            return dict(roll)

    raise InventoryStateError(f"No existe una tirada con ID '{roll_id}'.")


def get_equipped_rolls(path: str = INVENTORY_FILE) -> List[Dict[str, Any]]:
    """Return only equipped instances, preserving their unique IDs."""
    return [
        roll for roll in get_inventory(path)
        if roll.get("status", "stored") == "equipped"
    ]



def discard_roll(
    roll_id: str,
    tracker,
    path: str = INVENTORY_FILE,
) -> Dict[str, Any]:
    """Discard one pull and award its tier TP exactly once per roll ID.

    The tracker keeps an idempotency ledger in points.json. TP is recorded
    before the inventory state is changed, so a retry after an interrupted
    inventory write cannot award the same roll twice.
    """
    if not isinstance(roll_id, str) or not roll_id.strip():
        raise ValueError("Se requiere un ID de tirada válido.")

    data = _load_inventory(path)
    target = next(
        (roll for roll in data["rolls"] if roll.get("id") == roll_id),
        None,
    )
    if target is None:
        raise InventoryStateError(f"No existe una tirada con ID '{roll_id}'.")

    pull = target.get("pull", {})
    if not isinstance(pull, dict):
        raise InventoryStateError("La tirada no contiene datos válidos.")

    tier = str(pull.get("Tier", "")).strip()
    if tier not in DISCARD_TP_BY_TIER:
        raise InventoryStateError(
            f"El tier '{tier or 'vacío'}' no tiene un valor de descarte definido."
        )

    tp_value = DISCARD_TP_BY_TIER[tier]
    newly_awarded = tracker.award_discard_points(roll_id, tier)

    if target.get("status", "stored") != "discarded":
        target["status"] = "discarded"
        _save_inventory(data, path)

    return {
        "roll": dict(target),
        "tier": tier,
        "tp_value": tp_value,
        "tp_awarded_now": newly_awarded,
    }
