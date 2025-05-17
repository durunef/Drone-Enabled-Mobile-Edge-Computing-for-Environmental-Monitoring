#!/usr/bin/env python3
"""
Central Server Component
- headless TCP server that receives and processes DroneReport messages from the Drone Edge component
- provides a basic server implementation that can be used alongside or instead of the GUI version
- JSON message parsing and validation
- comprehensive logging of received data
- support for multiple drone connections (sequential)

usage:
    python server.py [--host HOST] [--port PORT]
"""
import json
import logging
import socket
import sys
import argparse
from pathlib import Path
from common.messages import DELIM, DroneReport

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))
import logconf  # noqa: F401


def main(host: str = "0.0.0.0", port: int = 6000):
    """
    runs the Central Server's main loop
    -creates a TCP socket with address reuse
    - accepts connections from Drone Edge components
    - receives and processes DroneReport messages
    - logs all received data and connection events
    """
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen()
    logging.info("Central Server listening on %s:%s", host, port)

    while True:
        conn, addr = srv.accept()
        logging.info("Drone connected from %s:%s", *addr)
        buffer = b""
        with conn:
            for chunk in iter(lambda: conn.recv(1024), b""):
                buffer += chunk
                while DELIM.encode() in buffer:
                    raw, buffer = buffer.split(DELIM.encode(), 1)
                    if not raw:
                        continue
                    batch = DroneReport(**json.loads(raw.decode()))
                    logging.info(
                        "Report Received: AvgT %.1f, AvgH %.1f, Batt %d%%, Status %s, Sensors %d, Anom %d",
                        batch.avg_temperature,
                        batch.avg_humidity,
                        batch.battery_level,
                        batch.status,
                        batch.sensor_count,
                        len(batch.anomalies)
                    )
                    if hasattr(self, 'gui_q'):
                        self.gui_q.put(batch)
                    else:
                        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Central Server for Drone Data")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind the server to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=6000, help="Port to bind the server to (default: 6000)")
    args = parser.parse_args()
    main(host=args.host, port=args.port)