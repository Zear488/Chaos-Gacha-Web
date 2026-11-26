"""Generate immutable random stat modifiers for individual gacha roll instances."""
from __future__ import annotations

import random

STATS = (
    "STR", "AGI", "INT", "WIS", "CON", "LCK",
    "Mana", "Vitality", "Defensa", "Ataque",
)

TIER_RULES = {
    "Trash": (0, 0, None, None),
    "Common": (1, 1, (2, 4), (1, 3)),
    "Uncommon": (1, 2, (3, 5), (2, 4)),
    "Rare": (2, 2, (4, 7), (3, 5)),
    "Elite": (2, 3, (5, 8), (4, 6)),
    "Epic": (3, 3, (6, 10), (5, 8)),
    "Legendary": (3, 4, (8, 13), (7, 10)),
    "Mythical": (4, 4, (10, 16), (9, 12)),
    "Divine": (4, 5, (13, 21), (11, 15)),
    "Transcendent": (5, 6, (17, 28), (14, 20)),
}
GENERATION_VERSION = 1


def luck_score(pull):
    """LuckValue is inverse: low values represent better luck."""
    raw = pull.get("LuckValue", 50)
    try:
        value = float(str(raw).strip().replace("%", ""))
    except (TypeError, ValueError):
        value = 50.0
    return 100.0 - max(0.0, min(100.0, value))


def modifier_count(tier, luck, rng=None):
    rng = rng or random
    minimum, maximum, _, _ = TIER_RULES.get(tier, (0, 0, None, None))
    if maximum <= minimum:
        return minimum
    probability = 0.20 + 0.25 * (max(0.0, min(100.0, luck)) / 100.0)
    return maximum if rng.random() < probability else minimum


def roll_magnitude(bounds, luck, rng=None):
    rng = rng or random
    low, high = bounds
    normalized_luck = max(0.0, min(100.0, luck)) / 100.0
    exponent = 2.0 - 1.5 * normalized_luck
    unit = rng.random() ** exponent
    return round(low + unit * (high - low), 2)


def generate_modifiers(pull, rng=None):
    """Generate once for one pull; each (stat, kind) pair is unique."""
    rng = rng or random
    tier = str(pull.get("Tier", "")).strip()
    minimum, maximum, flat_range, percent_range = TIER_RULES.get(
        tier, (0, 0, None, None)
    )
    if maximum == 0:
        return []

    luck = luck_score(pull)
    count = modifier_count(tier, luck, rng)
    available = [(stat, kind) for stat in STATS for kind in ("flat", "percent")]
    chosen = rng.sample(available, count)
    result = []
    for stat, kind in chosen:
        bounds = flat_range if kind == "flat" else percent_range
        result.append({
            "stat": stat,
            "kind": kind,
            "value": roll_magnitude(bounds, luck, rng),
        })
    return result


def ensure_roll_modifiers(roll):
    """Attach generated modifiers only if this eligible instance has none yet."""
    if not isinstance(roll, dict):
        return False
    pull = roll.get("pull", {})
    if not isinstance(pull, dict):
        return False
    category = str(pull.get("Type", "")).strip()
    tier = str(pull.get("Tier", "")).strip()
    if category not in {"Ability", "Familiar", "Skill", "Trait"}:
        return False
    if tier not in TIER_RULES or tier == "Trash":
        return False
    if roll.get("modifiers_generated") is True:
        return False

    # Preserve any manually/persistently supplied modifier payload rather than rerolling it.
    if isinstance(roll.get("modifiers"), list):
        roll["modifiers_generated"] = True
        roll.setdefault("modifier_generation_version", GENERATION_VERSION)
        return True

    roll["modifiers"] = generate_modifiers(pull)
    roll["modifiers_generated"] = True
    roll["modifier_generation_version"] = GENERATION_VERSION
    return True
