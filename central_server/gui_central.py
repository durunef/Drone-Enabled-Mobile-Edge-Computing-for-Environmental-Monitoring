"""
Central Server GUI Component
- display of drone reports - display of:
  - average temperature and humidity
  - drone battery status
  - number of connected sensors
  - anomaly reports with timestamps
- automatic connection handling
- scrollable log of all received data
usage:
    python gui_central.py [--host HOST] [--port PORT]
    python gui_central.py --host 0.0.0.0 --port 6000
"""
import json
import socket
import threading
import time
import argparse
from tkinter import Tk
from tkinter.scrolledtext import ScrolledText

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from common.messages import DELIM
from common.messages import DroneReport
import logging


class Receiver(threading.Thread):
    """
    minimal blocking TCP server that pushes summaries to gui_q
    handles the network communication aspect of the Central Server
    receiving data from the Drone Edge and formatting it for display
    """

    def __init__(self, gui_q, host="0.0.0.0", port=6000):
        """
        initialises the Receiver thread
        gui_q: Queue for sending messages to GUI
        host: host address to bind to
        port: port number to listen on
        """
        super().__init__(daemon=True)
        self.gui_q = gui_q
        self.host = host
        self.port = port

    def run(self):
        """
        main receiver loop
        accepts connections from the Drone Edge and processes incoming data
        the loop:
        1. accepts a connection from the Drone
        2. Receives JSON-formatted DroneReports
        3. Formats the data for display
        4. Pushes formatted messages to the GUI queue
        """
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.host, self.port))
        srv.listen()
        logging.info(f"Central GUI Receiver listening on {self.host}:{self.port}")
        while True:
            conn, addr = srv.accept()
            logging.info(f"Drone connected from {addr} to Central GUI Receiver")
            with conn:
                buf = b""
                for chunk in iter(lambda: conn.recv(1024), b""):
                    buf += chunk
                    while DELIM.encode() in buf:
                        raw, buf = buf.split(DELIM.encode(), 1)
                        if not raw:
                            continue
                        try:
                            report = DroneReport(**json.loads(raw.decode()))
                            log_message = (
                                f"{time.strftime('%H:%M:%S')} | "
                                f"Drone: {report.drone_id}, Status: {report.status}, Batt: {report.battery_level}%, "
                                f"AvgTemp: {report.avg_temperature:.1f}°C, AvgHum: {report.avg_humidity:.0f}%, "
                                f"Sensors: {report.sensor_count}, Anomalies: {len(report.anomalies)}\\n"
                            )
                            if report.anomalies:
                                for anomaly in report.anomalies:
                                    log_message += (
                                        f"  └─ Anomaly: Sensor {anomaly.get('sensor_id', 'N/A')}, "
                                        f"Val: {anomaly.get('val', 'N/A')}, TS: {anomaly.get('ts', 'N/A')}\\n"
                                    )
                            self.gui_q.put(log_message)
                        except json.JSONDecodeError:
                            logging.error(f"Central GUI Receiver: Failed to decode JSON: {raw.decode()}")
                        except Exception as e:
                            logging.error(f"Central GUI Receiver: Error processing report: {e}")
            logging.info(f"Drone from {addr} disconnected from Central GUI Receiver")


class CentralGUI(Tk):
    """
    main GUI window for the Central Server
    displays a scrollable text area showing drone reports and anomalies
    updates are received through a queue from the Receiver thread
    """
    def __init__(self, host="0.0.0.0", port=6000):
        """
        initialises the Central Server GUI
        host: host address for the receiver to bind to
        port: port number for the receiver to listen on
        """
        super().__init__()

        # window basics
        self.title("Central Server – batch log")
        self.geometry("500x350")

        # scrolling text widget
        self.text = ScrolledText(self, state="disabled", font=("Courier", 10))
        self.text.pack(fill="both", expand=True, padx=8, pady=8)

        # thread-safe queue for receiver messages
        import queue
        self.gui_q: queue.Queue[str] = queue.Queue()

        # start receiver
        Receiver(self.gui_q, host=host, port=port).start()

        # poll queue
        self.after(200, self._refresh)

    def _refresh(self):
        """
        updates the GUI with new messages from the queue
        called periodically by the Tkinter event loop
        """
        while not self.gui_q.empty():
            line = self.gui_q.get_nowait()
            self.text.configure(state="normal")
            self.text.insert("end", line)
            self.text.configure(state="disabled")
            self.text.see("end")
        self.after(200, self._refresh)


def main(host="0.0.0.0", port=6000):
    """
   
    starts the Central Server GUI application
    """
    CentralGUI(host=host, port=port).mainloop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Central Server GUI")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host for the GUI receiver to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=6000, help="Port for the GUI receiver to bind to (default: 6000)")
    args = parser.parse_args()
    main(host=args.host, port=args.port)