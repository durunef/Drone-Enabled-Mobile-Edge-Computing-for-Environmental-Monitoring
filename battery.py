class Battery:
    """
    phase-2: minimal drain only
    tick() in a loop and read the .level attribute (0–100)
    """

    def __init__(self, start: int = 100, drain_rate: int = 1):
        self.level = start
        self.drain_rate = drain_rate  # percent per call

    def tick(self) -> int:
        self.level = max(0, self.level - self.drain_rate)
        return self.level