import re

STAT_PATTERN = re.compile(r"(\w+)\s*([+\-])\s*(\d+)")
RES_PATTERN = re.compile(r"(\w+)\s*([+\-])\s*(\d+)%")

def parse_stats(line):
    """
    Ejemplo:
    #STATS: STR +4, CON +2
    """
    stats = {}
    for name, sign, value in STAT_PATTERN.findall(line):
        value = int(value) if sign == "+" else -int(value)
        stats[name.upper()] = stats.get(name.upper(), 0) + value
    return stats

def parse_resistances(line):
    """
    Ejemplo:
    #RESISTANCES: Fire +20%, Shadow -10%
    """
    res = {}
    for name, sign, value in RES_PATTERN.findall(line):
        value = int(value) if sign == "+" else -int(value)
        res[name.capitalize()] = res.get(name.capitalize(), 0) + value
    return res

def parse_generic_field(line):
    """
    #FACTION: Dragon Order → devuelve ("FACTION", "Dragon Order")
    #UTILITY: Sneak Bonus → devuelve ("UTILITY", "Sneak Bonus")
    """
    if not line.startswith("#"):
        return None, None

    try:
        tag, val = line[1:].split(":", 1)
        return tag.strip().upper(), val.strip()
    except:
        return None, None
