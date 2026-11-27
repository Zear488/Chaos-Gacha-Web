"""Combine narrative character stats with modifiers from equipped gacha rolls.

Star bonuses are a global multiplier on every final character stat. They do
not influence gacha probabilities or modify the pull-generation process.
"""
from __future__ import annotations


class StatsManager:
    def __init__(self, base_stats):
        if not isinstance(base_stats, dict):
            raise TypeError("base_stats debe ser un diccionario.")
        self.base = dict(base_stats)
        self.mods = {}
        self.random_flat = {}
        self.random_percent = {}
        self.star_count = 0

    def _canonical_stat(self, name):
        return {str(key).casefold(): key for key in self.base}.get(
            str(name).casefold()
        )

    def add_stats(self, stat_dict):
        """Add legacy descriptive #STATS values without changing their behavior."""
        if not isinstance(stat_dict, dict):
            return
        for key, value in stat_dict.items():
            canonical = self._canonical_stat(key)
            if canonical is None:
                continue
            self.mods[canonical] = self.mods.get(canonical, 0) + value

    def add_random_modifiers(self, modifiers):
        """Accumulate persisted flat/percent modifiers from equipped instances."""
        if not isinstance(modifiers, (list, tuple)):
            raise TypeError("modifiers debe ser una lista.")
        for modifier in modifiers:
            if not isinstance(modifier, dict):
                raise ValueError("Cada modificador debe ser un objeto.")
            stat = self._canonical_stat(modifier.get("stat", ""))
            kind = modifier.get("kind")
            value = modifier.get("value")
            if stat is None:
                continue
            if kind not in {"flat", "percent"}:
                raise ValueError(f"Tipo de modificador inválido: {kind!r}.")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("El valor del modificador debe ser numérico.")
            if value < 0:
                raise ValueError("Los modificadores aleatorios no pueden ser negativos.")
            target = self.random_flat if kind == "flat" else self.random_percent
            target[stat] = target.get(stat, 0) + value

    def set_star_count(self, count):
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("star_count debe ser un entero no negativo.")
        self.star_count = min(count, 4)

    def finalize(self, star_count=None):
        """Return all character stats with a global bonus per equipped star roll."""
        if star_count is not None:
            self.set_star_count(star_count)

        star_multiplier = 1 + 0.05 * self.star_count
        final = {}
        for key, base_value in self.base.items():
            legacy = self.mods.get(key, 0)
            flat = self.random_flat.get(key, 0)
            percent = self.random_percent.get(key, 0)
            random_contribution = (
                (base_value + flat) * (1 + percent / 100) - base_value
            )
            final[key] = (base_value + legacy + random_contribution) * star_multiplier
        return final
