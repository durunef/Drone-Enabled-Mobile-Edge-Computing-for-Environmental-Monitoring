#!/usr/bin/env python3
"""
Sensor Node Simulator

This module simulates an environmental sensor that sends temperature and humidity data to a Drone Edge server. 
It can generate either random values within normal ranges or use fixed values for testing purposes.

-TCP connection to Drone Edge server
-configurable sensor ID and data transmission interval
-automatic reconnection on connection failure
-support for both random and fixed sensor values
-comprehensive logging of all operations

normal ranges:
- Temp: 20-30°C (random mode)
- Hum: 40-60% (random mode)

usage:
    python sensor.py [--sensor_id ID] [--drone_ip IP] [--drone_port PORT] [--interval SEC] [--temperature TEMP] [--humidity HUM]

#random values
    python sensor.py --sensor_id sensor1 --drone_ip 127.0.0.1 --drone_port 5001 --interval 2.0
    
#testing values
    python sensor.py --sensor_id anomaly_test --temperature 1000 --humidity 200
"""
import argparse
import random
import socket
import sys
import time
import logging
from pathlib import Path

#add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))
import logconf  #initialises logging
from common.messages import SensorReading

RETRY_DELAY = 5 #seconds between reconnects as stated


def run_sensor(drone_ip: str, drone_port: int, sensor_id: str, interval: float, fixed_temp: float | None, fixed_hum: float | None):
    """connects to the Drone Edge server and continuously sends sensor readings
        fixed_temp and fixed_hum (float or None): If set, use this fixed temperature or humidity value instead of random
    
    -attempt to connect to the Drone Edge server
    -on successful connection, send periodic sensor readings
    -on connection failure, retry after RETRY_DELAY seconds
    -log all operations and errors
    """
    while True:
        try:
            with socket.create_connection((drone_ip, drone_port), timeout=3) as sock:
                logging.info("[%s] connected to Drone at %s:%s", sensor_id, drone_ip, drone_port)
                while True:
                    temp_to_send = fixed_temp if fixed_temp is not None else random.uniform(20, 30)
                    hum_to_send = fixed_hum if fixed_hum is not None else random.uniform(40, 60)
                    
                    reading = SensorReading(
                        sensor_id=sensor_id,
                        temperature=temp_to_send,
                        humidity=hum_to_send,
                    )
                    sock.sendall(reading.to_bytes())
                    logging.info(
                        "[%s] Sent: Temp=%.1f°C, Hum=%.0f%%",
                        sensor_id,
                        reading.temperature,
                        reading.humidity,
                    )
                    time.sleep(interval)
        except (OSError, ConnectionError) as exc:
            logging.warning(
                "[%s] connection problem to %s:%s (%s) – retrying in %s s",
                sensor_id,
                drone_ip,
                drone_port,
                exc,
                RETRY_DELAY,
            )
            time.sleep(RETRY_DELAY)
        except Exception as e:
            logging.error("[%s] An unexpected error occurred: %s", sensor_id, e)
            time.sleep(RETRY_DELAY)


def main():
    """    
    command line arguments
    """
    ap = argparse.ArgumentParser(description="Environmental Sensor Simulator")
    ap.add_argument("--sensor_id", default=f"sensor-{random.randint(100,999)}")
    ap.add_argument("--drone_ip", default="127.0.0.1")
    ap.add_argument("--drone_port", type=int, default=5001)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--temperature", type=float, default=None, help="Fixed temperature value to send (optional)")
    ap.add_argument("--humidity", type=float, default=None, help="Fixed humidity value to send (optional)")
    args = ap.parse_args()

    run_sensor(
        args.drone_ip, 
        args.drone_port, 
        args.sensor_id, 
        args.interval,
        args.temperature,
        args.humidity
    )


if __name__ == "__main__":
    main()