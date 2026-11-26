import os
import json
import re
import tempfile
from typing import List, Dict

GACHA_LOG_DIR = "gacha_log"
REPEATS_FILE = os.path.join(GACHA_LOG_DIR, "repeats.json")
POINTS_FILE = os.path.join(GACHA_LOG_DIR, "points.json")

DISCARD_TP_BY_TIER = {
    "Trash": 0.0,
    "Common": 0.001,
    "Uncommon": 0.003,
    "Rare": 0.009,
    "Elite": 0.025,
    "Epic": 0.075,
    "Legendary": 0.225,
    "Mythical": 0.675,
    "Divine": 2.025,
    "Transcendent": 6.075,
}

if not os.path.exists("logs"):
    os.makedirs("logs")

class GachaHistoryTracker:
    def __init__(self):
        os.makedirs(GACHA_LOG_DIR, exist_ok=True)
        self.repeats = self._load_json(REPEATS_FILE, default={})
        self.points = self._load_points()

    def _load_json(self, path: str, default):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return default

    def _load_points(self):
        if not os.path.exists(POINTS_FILE):
            return {"points": 0, "discard_transactions": {}}

        try:
            with open(POINTS_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"No se pudo leer {POINTS_FILE}; el archivo original se conserva."
            ) from exc

        if not isinstance(data, dict):
            raise ValueError(f"El formato de {POINTS_FILE} no es válido.")
        try:
            float(data.get("points", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Los puntos en {POINTS_FILE} no son válidos.") from exc

        transactions = data.get("discard_transactions", {})
        if not isinstance(transactions, dict):
            raise ValueError(f"El registro de descartes en {POINTS_FILE} no es válido.")
        data.setdefault("discard_transactions", {})
        return data

    def _save_json(self, path: str, data):
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=directory,
                delete=False, suffix=".tmp"
            ) as file:
                json.dump(data, file, indent=2, ensure_ascii=False)
                file.write("\n")
                temp_path = file.name
            os.replace(temp_path, path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def check_repeat(self, pull: Dict) -> bool:
        key = f"{pull['Type']}::{pull['Element']}"
        if key in self.repeats:
            self.points["points"] += 1
            self._save_json(POINTS_FILE, self.points)
            return True
        self.repeats[key] = True
        self._save_json(REPEATS_FILE, self.repeats)
        return False

    def get_points(self) -> float:
        return float(self.points.get("points", 0))

    def spend_points(self, cost: int) -> bool:
        if self.points["points"] >= cost:
            self.points["points"] = round(float(self.points["points"]) - cost, 6)
            self._save_json(POINTS_FILE, self.points)
            return True
        return False

    def award_discard_points(self, roll_id: str, tier: str) -> bool:
        """Credit discard TP once per persistent roll ID.

        Returns True only when this call creates a new TP transaction.
        """
        if not isinstance(roll_id, str) or not roll_id.strip():
            raise ValueError("Se requiere un ID de tirada válido.")
        if tier not in DISCARD_TP_BY_TIER:
            raise ValueError(f"Tier sin valor de descarte: {tier}")

        data = self._load_points()
        transactions = data.setdefault("discard_transactions", {})
        if roll_id in transactions:
            self.points = data
            return False

        amount = DISCARD_TP_BY_TIER[tier]
        data["points"] = round(float(data.get("points", 0)) + amount, 6)
        transactions[roll_id] = {"tier": tier, "amount": amount}
        self._save_json(POINTS_FILE, data)
        self.points = data
        return True

    def clear_all(self):
        self.repeats = {}
        self.points = {"points": 0, "discard_transactions": {}}
        self._save_json(REPEATS_FILE, self.repeats)
        self._save_json(POINTS_FILE, self.points)

    def load_from_log(self, log: List[Dict]):
        self.repeats = {f"{entry['Type']}::{entry['Element']}": True for entry in log}
        self._save_json(REPEATS_FILE, self.repeats)

        total_points = 0
        for entry in log:
            notes = str(entry.get("Notes", "")).strip()

        # Aceptar variantes de "Repeated" aunque el emoji esté dañado
            if "Repeated" in notes:
                total_points += 1

        # Aceptar cualquier "- X TP"
            match = re.search(r"-\s*(\d+)\s*TP", notes)
            if match:
                total_points -= int(match.group(1))

        transactions = self._load_points().get("discard_transactions", {})
        discard_total = sum(
            float(entry.get("amount", 0))
            for entry in transactions.values()
            if isinstance(entry, dict)
        )
        self.points = {
            "points": round(total_points + discard_total, 6),
            "discard_transactions": transactions,
        }
        self._save_json(POINTS_FILE, self.points)
