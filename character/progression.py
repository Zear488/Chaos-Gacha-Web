"""Narrative character progression derived from the number of gacha pulls.

The character's attributes are descriptive only. This module never feeds
character stats or level back into the gacha draw engine.
"""
from __future__ import annotations

import json
import os
import tempfile

PROGRESS_FILE = os.path.join("gacha_log", "character_progress.json")
STAT_NAMES = (
    "STR", "AGI", "INT", "WIS", "CON", "LCK",
    "Mana", "Vitality", "Defensa", "Ataque",
)


def pulls_required_for_level(level: int) -> int:
    """Cumulative pulls required to reach a level (level 1 starts at zero).

    Reaching level N requires N additional pulls after level N-1.
    Therefore the cumulative threshold is 2 + 3 + ... + N.
    """
    if isinstance(level, bool) or not isinstance(level, int) or level < 1:
        raise ValueError("El nivel debe ser un entero mayor o igual a 1.")
    return level * (level + 1) // 2 - 1


def get_level_from_pulls(pull_count: int) -> int:
    """Resolve the current level from unique pull-history rows."""
    if isinstance(pull_count, bool) or not isinstance(pull_count, int) or pull_count < 0:
        raise ValueError("El número de tiradas debe ser un entero no negativo.")
    level = 1
    while pulls_required_for_level(level + 1) <= pull_count:
        level += 1
    return level


def get_progress_to_next_level(pull_count: int) -> dict:
    level = get_level_from_pulls(pull_count)
    current_threshold = pulls_required_for_level(level)
    next_threshold = pulls_required_for_level(level + 1)
    return {
        "level": level,
        "pulls_into_level": pull_count - current_threshold,
        "pulls_needed_for_next_level": next_threshold - pull_count,
        "pulls_for_this_level": next_threshold - current_threshold,
        "current_threshold": current_threshold,
        "next_threshold": next_threshold,
    }


def points_earned_for_level(level: int) -> int:
    """Total stat points earned by reaching the given level."""
    return pulls_required_for_level(level)


def _default_progress() -> dict:
    return {"version": 1, "allocated": {name: 0 for name in STAT_NAMES}}


def load_character_progress(path: str = PROGRESS_FILE) -> dict:
    if not os.path.exists(path):
        return _default_progress()
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict) or not isinstance(data.get("allocated"), dict):
            raise ValueError("Formato de progresión inválido.")
        allocated = {}
        for name in STAT_NAMES:
            value = data["allocated"].get(name, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"Asignación inválida para {name}.")
            allocated[name] = value
        return {"version": 1, "allocated": allocated}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            f"No se pudo leer la progresión del personaje ({path}). "
            "El archivo original se conserva."
        ) from exc


def save_character_progress(data: dict, path: str = PROGRESS_FILE) -> None:
    if not isinstance(data, dict) or not isinstance(data.get("allocated"), dict):
        raise ValueError("Datos de progresión inválidos.")
    normalized = _default_progress()
    for name in STAT_NAMES:
        value = data["allocated"].get(name, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Asignación inválida para {name}.")
        normalized["allocated"][name] = value

    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=directory,
            delete=False, suffix=".tmp"
        ) as file:
            json.dump(normalized, file, ensure_ascii=False, indent=2)
            file.write("\\n")
            temp_path = file.name
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def allocate_stat_points(
    stat_name: str,
    amount: int,
    pull_count: int,
    path: str = PROGRESS_FILE,
) -> dict:
    if stat_name not in STAT_NAMES:
        raise ValueError(f"Estadística desconocida: {stat_name}.")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
        raise ValueError("La cantidad debe ser un entero positivo.")

    progress = load_character_progress(path)
    earned = points_earned_for_level(get_level_from_pulls(pull_count))
    spent = sum(progress["allocated"].values())
    available = earned - spent
    if amount > available:
        raise ValueError(
            f"No hay suficientes puntos disponibles: {available} restante(s)."
        )

    progress["allocated"][stat_name] += amount
    save_character_progress(progress, path)
    return progress


def clear_character_progress(path: str = PROGRESS_FILE) -> None:
    save_character_progress(_default_progress(), path)
