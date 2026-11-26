class StatsManager:
    def __init__(self, base_stats):
        self.base = base_stats
        self.mods = {}

    def add_stats(self, stat_dict):
        # Description tags are parsed in uppercase, while the existing base
        # stats file uses mixed-case names such as Mana and Vitality.
        base_names = {str(name).casefold(): name for name in self.base}
        for key, value in stat_dict.items():
            canonical_key = base_names.get(str(key).casefold())
            if canonical_key is not None:
                self.mods[canonical_key] = self.mods.get(canonical_key, 0) + value

    def finalize(self):
        final = {}
        for key in self.base:
            final[key] = self.base[key] + self.mods.get(key, 0)
        return final
