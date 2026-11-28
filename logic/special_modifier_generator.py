"""Independent special modifier generation for one-family-per-pull effects."""
from __future__ import annotations

import random

from .modifier_generator import TIER_RULES, luck_score, modifier_count, roll_magnitude

SPECIAL_CHANCE = 0.25
GENERATION_VERSION = 1
ELIGIBLE_TYPES = {"Ability", "Familiar", "Skill", "Trait"}

FAMILIES = {
    "resistances": [
        ("resistance", "Fire Resistance", "resist"),
        ("resistance", "Ice Resistance", "resist"),
        ("resistance", "Lightning Resistance", "resist"),
        ("resistance", "Poison Resistance", "resist"),
        ("resistance", "Acid Resistance", "resist"),
        ("resistance", "Corrosion Resistance", "resist"),
        ("resistance", "Radiation Resistance", "resist"),
        ("resistance", "Void / Pressure Resistance", "resist"),
        ("resistance", "Psychic Resistance", "resist"),
        ("resistance", "Corruption Resistance", "resist"),
        ("affinity", "Elemental Affinity", "amplify"),
    ],
    "unusual": [
        ("attribute", "Mental Stability", "bonus"),
        ("attribute", "Fortune / Karma", "bonus"),
        ("attribute", "Dark Charisma", "bonus"),
        ("attribute", "Survival Instinct", "bonus"),
        ("attribute", "Adaptability", "bonus"),
        ("attribute", "Resonance", "bonus"),
        ("attribute", "Soul Echo", "bonus"),
    ],
    "intimacy": [
        ("attribute", "Attractiveness / Sexual Magnetism", "bonus"),
        ("attribute", "Sensitivity", "bonus"),
        ("attribute", "Pleasure Resistance", "bonus"),
        ("attribute", "Dominance / Submission", "bonus"),
        ("attribute", "Emotional Affinity", "bonus"),
        ("attribute", "Libido / Desire", "bonus"),
        ("attribute", "Orgasm Control", "bonus"),
        ("attribute", "Pheromones / Sensual Aura", "bonus"),
        ("attribute", "Intimate Experience", "bonus"),
        ("attribute", "Emotional Vulnerability", "bonus"),
    ],
    "rare": [
        ("attribute", "Shadow", "bonus"),
        ("attribute", "Presence", "bonus"),
        ("attribute", "Temporal Resonance", "bonus"),
        ("attribute", "Pain Threshold", "bonus"),
        ("attribute", "Blood Echo", "bonus"),
        ("attribute", "Forbidden Affinity", "bonus"),
    ],
}


def generate_special_modifiers(pull, rng=None):
    """Return None or one family containing multiple unique percentage effects.

    The 25% special trigger is independent of Luck. Once triggered, effect
    count and magnitude use the same tier/Luck rules as normal modifiers.
    """
    rng = rng or random
    tier = str(pull.get("Tier", "")).strip()
    category = str(pull.get("Type", "")).strip()
    if category not in ELIGIBLE_TYPES or tier not in TIER_RULES or tier == "Trash":
        return None
    if rng.random() >= SPECIAL_CHANCE:
        return None

    family = rng.choice(tuple(FAMILIES))
    candidates = FAMILIES[family]
    luck = luck_score(pull)
    count = modifier_count(tier, luck, rng)
    if count <= 0:
        return None

    percent_range = TIER_RULES[tier][3]
    selected = rng.sample(candidates, min(count, len(candidates)))
    effects = [
        {
            "type": effect_type,
            "target": target,
            "mode": mode,
            "value": roll_magnitude(percent_range, luck, rng),
            "unit": "%",
        }
        for effect_type, target, mode in selected
    ]
    return {"family": family, "effects": effects}


def ensure_roll_special_modifiers(roll, rng=None):
    """Generate special effects once per inventory instance."""
    if not isinstance(roll, dict):
        return False
    pull = roll.get("pull", {})
    if not isinstance(pull, dict):
        return False
    if roll.get("special_modifiers_generated") is True:
        return False
    if isinstance(roll.get("special_modifiers"), dict):
        roll["special_modifiers_generated"] = True
        roll.setdefault("special_modifier_generation_version", GENERATION_VERSION)
        return True

    roll["special_modifiers"] = generate_special_modifiers(pull, rng=rng)
    roll["special_modifiers_generated"] = True
    roll["special_modifier_generation_version"] = GENERATION_VERSION
    return True
