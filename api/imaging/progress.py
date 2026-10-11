"""Progress over image-region pairs, delivered to the caller."""


class Progress:
    STAGES = {
        "load": 5, "segment": 20, "skeletonize": 60, "prune": 65,
        "topology": 75, "aggregate": 85, "render": 95,
    }

    def __init__(self, emit=None, units=1):
        self.emit = emit
        self.units = max(units, 1)
        self.done = 0

    def stage(self, name, region="Full"):
        if self.emit is not None:
            percent = (self.done + self.STAGES[name] / 100) / self.units * 100
            self.emit({"stage": name, "percent": round(percent, 1), "region": region})

    def unit_done(self):
        self.done += 1
