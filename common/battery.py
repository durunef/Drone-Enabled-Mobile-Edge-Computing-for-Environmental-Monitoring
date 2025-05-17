
class Battery:
    """
    simulates a drone battery with charging and status management
    the battery operates with two key thresholds:
    1. LOW_BATTERY_THRESHOLD: triggers return-to-base behavior
    2. CRITICAL_BATTERY_THRESHOLD: required level for resuming normal operation
    """
    CRITICAL_BATTERY_THRESHOLD = 90 # Should be >LOW_BATTERY_THRESHOLD
    RECHARGE_RATE = 10  #per tick during recharge
    DRAIN_RATE = 3      #per tick during normal operation

    def __init__(self, start=100, drain=DRAIN_RATE, recharge=RECHARGE_RATE, low_threshold=20):
        self.level = start
        self.drain_rate = drain
        self.recharge_rate = recharge
        self.LOW_BATTERY_THRESHOLD = low_threshold
        self.returning = False

    def tick(self, charging=False) -> int:
        """
        simulates one time unit of battery operation
        charging: whether the battery is being charged
        updates the battery's returning status based on:
        - if level drops below LOW_BATTERY_THRESHOLD: sets returning=True
        - if level reaches CRITICAL_BATTERY_THRESHOLD: sets returning=False
        """
        if charging:
            self.level = min(100, self.level + self.recharge_rate)
        else:
            self.level = max(0, self.level - self.drain_rate)
        if not self.returning and self.level < self.LOW_BATTERY_THRESHOLD:
            self.returning = True
        elif self.returning and self.level >= self.CRITICAL_BATTERY_THRESHOLD:
            self.returning = False
        return self.level 