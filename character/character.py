import os
from .parser import parse_stats, parse_resistances, parse_generic_field
from .loader import load_stats_base
from .validator import validate_json, validate_csv, validate_txt_block
from .stats_manager import StatsManager
from logic.roll_manager import get_equipped_rolls
from .progression import load_character_progress


def _has_star_bonus(pull):
    """Recognize the existing star marker without counting Element + Notes twice."""
    element = str(pull.get("Element", "")).lstrip()
    notes = str(pull.get("Notes", ""))
    return element.startswith("★") or "boosted star bonus" in notes.casefold()


class Character:
    def __init__(self):
        self.possession = {}
        self.csv_rows = []
        self.equipped_rolls = None
        self.free_categories = {}
        self.stats = None
        self.resistances = {}
        self.other_fields = {}

    # ---------------------
    # LOADERS
    # ---------------------
    def load_gacha_possession(self, path="gacha_log/repeats.json", report=None):
        """
        Carga la posesión TRUE/FALSE desde repeats.json,
        que es el archivo oficial de posesions del sistema gacha.
        """
        default = {}
        self.possession = validate_json(path, report, dict, default)

    def load_gacha_csv(self, path="logs/gacha_history.csv", report=None):
        """Carga el historial de tiradas con todos los detalles."""
        self.csv_rows = validate_csv(path, report)

    def load_stats(self, report=None):
        # Allocated level-up points are descriptive character-sheet values.
        # They are deliberately never passed to the gacha draw engine.
        base = load_stats_base()
        progression = load_character_progress()
        for stat, points in progression["allocated"].items():
            if stat in base:
                base[stat] += points
        self.stats = StatsManager(base)

    # ---------------------
    # PROCESSORS
    # ---------------------
    def load_equipped_rolls(self, path="gacha_log/inventory.json"):
        """Load only individual roll instances currently marked as equipped."""
        self.equipped_rolls = get_equipped_rolls(path)

    def apply_gacha_items(self):
        """
        Apply supported descriptive tags and persisted random modifiers from
        equipped instances only. Stored and discarded rolls never contribute.
        """
        if self.equipped_rolls is None:
            self.load_equipped_rolls()

        star_count = 0
        for instance in self.equipped_rolls:
            pull = instance.get("pull", {})
            if not isinstance(pull, dict):
                continue

            if _has_star_bonus(pull):
                star_count += 1

            modifiers = instance.get("modifiers", [])
            if modifiers:
                self.stats.add_random_modifiers(modifiers)

            desc = str(pull.get("Description", ""))
            for line in desc.splitlines():
                if "#STATS" in line:
                    self.stats.add_stats(parse_stats(line))
                elif "#RESISTANCES" in line:
                    res = parse_resistances(line)
                    for key, value in res.items():
                        self.resistances[key] = self.resistances.get(key, 0) + value
                else:
                    tag, value = parse_generic_field(line)
                    if tag:
                        self.other_fields.setdefault(tag, []).append(value)

        self.stats.set_star_count(star_count)

    def load_free_categories(self, folder="characterfiles", report=None):
        for name in ["race", "class", "lineage", "talent", "element",
                     "factions", "reputations", "resistances",
                     "equipment_custom"]:
            fpath = os.path.join(folder, f"{name}.txt")
            self.free_categories[name] = validate_txt_block(fpath, report)

    # ---------------------
    # FINAL BUILD
    # ---------------------
    def build(self):
        self.load_stats()
        if self.equipped_rolls is None:
            self.load_equipped_rolls()
        self.apply_gacha_items()
        self.load_free_categories()
        final_stats = self.stats.finalize()

        return {
            "stats": final_stats,
            "resistances": self.resistances,
            "fields": self.other_fields
        }
