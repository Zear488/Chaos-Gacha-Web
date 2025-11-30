import os
from .parser import parse_stats, parse_resistances, parse_generic_field
from .loader import load_possession_json, load_csv_history, load_free_category, load_stats_base
from .validator import ValidationReport, validate_json, validate_csv, validate_txt_block
from .stats_manager import StatsManager

class Character:
    def __init__(self):
        self.possession = {}
        self.csv_rows = []
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
        """
        Carga el historial de tiradas con todos los detalles.
        """
        self.csv_rows = validate_csv(path, report)

    def load_free_categories(self, folder="characterfiles", report=None):
        for name in ["race", "class", "lineage", "talent", "element",
                     "factions", "reputations", "resistances",
                     "equipment_custom"]:
            fpath = os.path.join(folder, f"{name}.txt")
            self.free_categories[name] = load_free_category(fpath)

    def load_stats(self, report=None):

        base = load_stats_base()
        self.stats = StatsManager(base)


    # ---------------------
    # PROCESSORS
    # ---------------------
    def apply_gacha_items(self):
        """
        Fusiona JSON (posesión) con CSV (detalles completos)
        y aplica modificadores encontrados en Description.
        """
        for key, owned in self.possession.items():
            if not owned:
                continue

        # Esperado: "Type::Name"
            if "::" not in key:
                continue

            type_, name = key.split("::", 1)

        # Buscar la fila correcta en el CSV
            row = None
            for r in self.csv_rows:
            # Proteger contra filas incompletas
                if not isinstance(r, dict):
                    continue
                if "Type" not in r or "Element" not in r:
                # Fila inválida — simplemente se ignora
                    continue

                if r["Type"] == type_ and name in r["Element"]:
                    row = r
                    break

        # Si no se encuentra una fila con detalles válidos → ignorar
            if not row:
                continue

            desc = row.get("Description", "")

        # Procesar descripción línea por línea
            for line in desc.splitlines():
                if "#STATS" in line:
                    self.stats.add_stats(parse_stats(line))

                elif "#RESISTANCES" in line:
                    res = parse_resistances(line)
                    for k, v in res.items():
                        self.resistances[k] = self.resistances.get(k, 0) + v

                else:
                    tag, val = parse_generic_field(line)
                    if tag:
                        self.other_fields.setdefault(tag, []).append(val)


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
        self.apply_gacha_items()
        self.load_free_categories()
        final_stats = self.stats.finalize()

        return {
            "stats": final_stats,
            "resistances": self.resistances,
            "fields": self.other_fields
        }
