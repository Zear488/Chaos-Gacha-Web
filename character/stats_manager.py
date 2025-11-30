class StatsManager:
    def __init__(self, base_stats):
        self.base = base_stats
        self.mods = {}

    def add_stats(self, stat_dict):
        for k, v in stat_dict.items():
            self.mods[k] = self.mods.get(k, 0) + v

    def finalize(self):
        final = {}
        for k in self.base:
            final[k] = self.base[k] + self.mods.get(k, 0)
        return final
