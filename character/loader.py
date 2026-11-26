import json
import csv
import os

def load_possession_json(path="gacha_log.json"):
    """
    JSON del tipo:
    {
        "Skill::Fake Weapon": true,
        "Item::Iron Gloves": true
    }
    """
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_csv_history(path):
    """
    Carga cada tirada ya convertida en dict por tu Gacha_app.py
    """
    results = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(row)
    return results


def load_free_category(path):
    """
    Lee archivos como Race.txt, Class.txt, etc.
    Cada bloque está separado por líneas vacías.
    """
    if not os.path.exists(path):
        return []

    blocks = []
    temp = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() == "":
                if temp:
                    blocks.append(temp)
                    temp = []
            else:
                temp.append(line.rstrip("\n"))

    if temp:
        blocks.append(temp)

    return blocks


def load_stats_base(path="characterfiles/stats.json"):
    fallback = {
        "STR": 1, "AGI": 1, "INT": 1, "WIS": 1,
        "CON": 1, "LCK": 1, "Mana": 1,
        "Vitality": 1, "Defensa": 1, "Ataque": 1
    }

    if not os.path.exists(path):
        return fallback

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Invalid stats.json structure")
        return data
    except Exception:
        return fallback
