"""

- SensorReading: raw data from sensor nodes to Drone Edge
- DroneReport: processed data from Drone Edge to Central Server

Sensor Node -> (SensorReading) -> Drone Edge -> (DroneReport) -> Central Server

format:
    SensorReading:
    {
        "sensor_id": "sensor1",
        "temperature": 25.6,
        "humidity": 45,
        "timestamp": "2025-05-14T14:29:39.439Z"
    }

    DroneReport:
    {
        "drone_id": "drone1",
        "timestamp": "2025-05-14T14:29:39.439Z",
        "battery_level": 85,
        "status": "active",
        "avg_temperature": 24.5,
        "avg_humidity": 48,
        "sensor_count": 3,
        "anomalies": [
            {
                "sensor_id": "sensor2",
                "val": [45.6, 95],
                "ts": "2025-05-14T14:29:38.123Z"
            }
        ]
    }
"""
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
import json

DELIM = "\n" 


@dataclass
class SensorReading:
    sensor_id: str
    temperature: float
    humidity: float
    timestamp: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )

    def to_bytes(self) -> bytes:
        """
        serializes the reading to JSON and encodes as bytes for network transmission
        """
        return (json.dumps(asdict(self)) + DELIM).encode()

    @staticmethod
    def from_bytes(raw: bytes) -> "SensorReading":
        """
        creates a SensorReading instance from received bytes
        raw: JSON-encoded reading received from network
        """
        return SensorReading(**json.loads(raw.decode()))

@dataclass
class DroneReport:
    """
    
    represents a batch report from drone edge to central server
    contains aggregated sensor data and system status information
    """
    drone_id: str
    timestamp: str
    battery_level: int
    status: str          # "active" | "returning"
    avg_temperature: float
    avg_humidity: float
    sensor_count: int
    anomalies: list      # list of dicts

    def to_bytes(self) -> bytes:
        """
        serializes the report to JSON and encodes as bytes for network transmission
        """
        return (json.dumps(asdict(self)) + DELIM).encode()