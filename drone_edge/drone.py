#!/usr/bin/env python3
"""
Drone Edge Component

performs edge computing tasks such as data aggregation and anomaly detection before forwarding processed data

- TCP server for multiple sensor connections
- edge processing (averaging, anomaly detection)
- battery simulation with return-to-base behavior
- data forwarding to central server
- comprehensive logging and error handling
- support for storing unsent data during return-to-base

thresholds:
- Temperature: 0-40°C (normal range)
- Humidity: 10-90% (normal range)
- Battery: 20% (default low battery threshold)

config:
- FORWARD_BATCH: Number of readings to collect before sending to central (default: 5)
- UNSENT_REPORTS_RETRY_INTERVAL: Seconds between retrying unsent reports (default: 60)
- BATTERY_CHECK_INTERVAL: Seconds between battery level checks (default: 10)
- EFFECTIVE_BATTERY_TICK_INTERVAL: Seconds between battery level updates (default: 1)
"""
import json
import logging
import queue
import socket
import sys
import threading
import time
import argparse
from pathlib import Path
import datetime

sys.path.append(str(Path(__file__).parent.parent))
import logconf 
from common.battery import Battery
from common.messages import SensorReading, DELIM, DroneReport

FORWARD_BATCH = 5 # send to central after 5 readings
UNSENT_REPORTS_RETRY_INTERVAL = 60 
BATTERY_CHECK_INTERVAL = 10  # seconds between battery checks
EFFECTIVE_BATTERY_TICK_INTERVAL = 1 

THRESHOLDS = {"temp": (0, 40), "hum": (10, 90)}

def is_anomaly(reading):
    """
    check if a sensor reading contains anomalous values
    returns True if either temperature or humidity is outside normal ranges
    """
    t_ok = THRESHOLDS["temp"][0] <= reading.temperature <= THRESHOLDS["temp"][1]
    h_ok = THRESHOLDS["hum"][0] <= reading.humidity <= THRESHOLDS["hum"][1]
    return not (t_ok and h_ok)

class DroneEdge:
    """
    handles sensor connections, data processing, and forwarding
    operates in two main modes:
    1. active: normal operation, accepting sensor connections and forwarding data
    2. returning: when battery is low, may queue data instead of forwarding
    """
    def __init__(self, listen_port: int = 5001, central_ip: str = "127.0.0.1", central_port: int = 6000):
        """
        initialises the DroneEdge instance
        """
        self.listen_port = listen_port
        self.central_addr = (central_ip, central_port)
        self.readings_q = queue.Queue() # for forwarding to central server
        self.gui_q = queue.Queue() # for the GUI to display
        self.battery = Battery(recharge=10, low_threshold=20) # explicitly set default, matches Battery class
        self._stop = threading.Event() # for stopping the drone
        self.unsent_dir = Path("unsent") # for storing unsent reports
        self.unsent_dir.mkdir(exist_ok=True) # create the directory if it doesn't exist
        self.last_battery_tick_time = time.time() # for time-based battery tick
        self.travel_ticks_remaining = 0 # for delayed charging
        self.charging_started_log_sent = False # to log charging start only once per cycle
        self.server_socket = None # for shutdown of server socket

    def _sensor_handler(self, conn: socket.socket, addr):
        """
        handles sensor connections, data processing, and forwarding
        """
        buffer = b""
        client_id = f"{addr[0]}:{addr[1]}"
        logging.info(f"Sensor {client_id} connected.")
        conn.settimeout(1.0) # set a timeout for recv
        try:
            with conn:
                while not self._stop.is_set(): #check stop event also in the outer loop
                    try:
                        chunk = conn.recv(1024)
                        if not chunk: #connection closed by client
                            break
                    except socket.timeout:
                        if self._stop.is_set(): #check if stop was set during timeout
                            break
                        continue # continue to allow recv to try again if not stopping
                    except ConnectionResetError:
                        logging.warning(f"Sensor {client_id} connection reset (recv).")
                        break
                    except Exception as e_recv:
                        logging.error(f"Error receiving data from {client_id}: {e_recv}")
                        break

                    buffer += chunk
                    while DELIM.encode() in buffer:
                        if self._stop.is_set(): #check before processing buffer
                            break
                        raw, buffer = buffer.split(DELIM.encode(), 1)
                        if not raw:
                            continue
                        try:
                            reading = SensorReading.from_bytes(raw)
                            logging.info(
                                "RX %s from %s: %.1f°C %.0f%%", 
                                reading.sensor_id, client_id, reading.temperature, reading.humidity
                            )
                            if not self._stop.is_set(): #check before putting on queue
                                self.readings_q.put(reading)
                                self.gui_q.put(reading) 
                        except json.JSONDecodeError:
                            logging.error(f"JSON decode error from {client_id}: {raw.decode()}")
                        except Exception as e:
                            logging.error(f"Error processing sensor data from {client_id}: {e}")
                    if self._stop.is_set(): # ensure loop stops if stop set during buffer processing
                        break 
        except ConnectionResetError: #this might catch reset if it happens outside the loop for some reason
            logging.warning(f"Sensor {client_id} connection reset (outer).")
        except Exception as e:
            logging.error(f"Error in sensor handler for {client_id}: {e}")
        finally:
            logging.info(f"Sensor {client_id} disconnected.")

    def _run_server(self):
        """
        Runs the TCP server that accepts sensor connections
        each sensor connection is handled in a separate thread
        """
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.settimeout(1.0) #set a timeout on the server socket
        try:
            self.server_socket.bind(("", self.listen_port))
            self.server_socket.listen()
            logging.info("Drone listening on port %s", self.listen_port)
            while not self._stop.is_set():
                try:
                    conn, addr = self.server_socket.accept()
                    threading.Thread(
                        target=self._sensor_handler,
                        args=(conn, addr),
                        daemon=True
                    ).start()
                except socket.timeout:
                    if self._stop.is_set(): #check if stop was set during timeout
                        break
                    continue # continue to allow accept to try again if not stopping
                except Exception as e_accept:
                    if self._stop.is_set(): #if socket was closed by stop()
                        logging.info(f"Server socket accept error during shutdown: {e_accept}")
                    else:
                        logging.error(f"Error accepting connection: {e_accept}")
                    break # exit loop on other accept errors or during shutdown
        except Exception as e_server_setup:
            logging.critical(f"Drone server setup failed: {e_server_setup}")
            self.stop()
        finally:
            if self.server_socket:
                logging.info("Closing server socket in _run_server finally block.")
                self.server_socket.close()
                self.server_socket = None
            logging.info("Drone server loop terminated.")

    def _forward_loop(self):
        """
        handles data processing and forwarding
        """
        batch = []
        anomalies = []
        last_known_returning_status = self.battery.returning

        while not self._stop.is_set():
            current_time = time.time()
            #battery tick logic
            if current_time - self.last_battery_tick_time >= EFFECTIVE_BATTERY_TICK_INTERVAL:
                #determine if charging should occur based on returning status and travel ticks
                should_charge_this_tick = False
                if self.battery.returning:
                    if self.travel_ticks_remaining > 0:
                        logging.info(f"Drone returning to base: {self.travel_ticks_remaining} travel ticks remaining. Draining battery.")
                        self.travel_ticks_remaining -= 1
                        # drone still drains while traveling
                    else: #travel_ticks_remaining is 0, drone arrived
                        if not self.charging_started_log_sent:
                            logging.info("Drone arrived at base. Commencing charge.")
                            self.charging_started_log_sent = True
                        should_charge_this_tick = True
                
                self.battery.tick(charging=should_charge_this_tick)
                self.last_battery_tick_time = current_time

                # 0% battery shutdown check
                if self.battery.level <= 0 and not self._stop.is_set():
                    logging.critical("!!! BATTERY CRITICAL - 0%. Drone initiating shutdown. !!!")
                    self.stop()
                    break # exit _forward_loop

            current_returning_status = self.battery.returning
            
            # status change detections
            # drone becomes active (previously returning, now not)
            if last_known_returning_status and not current_returning_status:
                logging.info(f"Drone now active. Battery: {self.battery.level}%.")
                self.charging_started_log_sent = False #reset for next cycle
                if batch: #flush any queued data
                    logging.info(f"Flushing {len(batch)} queued readings upon becoming active.")
                    self._send_report(list(batch), list(anomalies))
                    batch.clear()
                    anomalies.clear()

            #drone starts returning (previously not, now yes)
            if not last_known_returning_status and current_returning_status:
                logging.info(f"Drone initiating return to base (Threshold: {self.battery.LOW_BATTERY_THRESHOLD}%). Battery: {self.battery.level}%. Travel time: 2 ticks.")
                self.travel_ticks_remaining = 2 #set travel time
                self.charging_started_log_sent = False # Reset for next cycle

            last_known_returning_status = current_returning_status
            
            # queue reading
            try:
                reading = self.readings_q.get(timeout=1)
                if is_anomaly(reading):
                    anomaly_event = {
                        "sensor_id": reading.sensor_id,
                        "val": [reading.temperature, reading.humidity],
                        "ts": reading.timestamp
                    }
                    anomalies.append(anomaly_event)
                    # self.gui_q.put(anomaly_event)
                
                if self.battery.returning:
                    batch.append(reading)
                    logging.info(f"Battery low ({self.battery.level}%), queuing reading from {reading.sensor_id}")
                    continue
                
                batch.append(reading)
            except queue.Empty:
                pass

            if len(batch) >= FORWARD_BATCH and not self.battery.returning:
                self._send_report(list(batch), list(anomalies))
                batch.clear()
                anomalies.clear()
            elif not batch and not self.battery.returning: #if batch was cleared by status change flush
                pass # avoid trying to send an empty batch

    def _send_report(self, readings, anomalies_list):
        """
        sends a report to the central server
        """
        if not readings:
            return
        valid_readings = [r for r in readings if hasattr(r, 'temperature') and hasattr(r, 'humidity')]
        if not valid_readings:
            logging.warning("No valid readings with T/H to calculate averages for report.")
            return

        avg_t = sum(r.temperature for r in valid_readings) / len(valid_readings)
        avg_h = sum(r.humidity for r in valid_readings) / len(valid_readings)
        
        rpt = DroneReport(
            drone_id="drone1",
            timestamp=datetime.datetime.utcnow().isoformat(),
            battery_level=self.battery.level,
            status="returning" if self.battery.returning else "active",
            avg_temperature=avg_t,
            avg_humidity=avg_h,
            sensor_count=len({r.sensor_id for r in valid_readings if hasattr(r, 'sensor_id')}),
            anomalies=anomalies_list,
        )
        
        # send report to drone's own GUI
        self.gui_q.put(rpt) 

        try:
            with socket.create_connection(self.central_addr, timeout=2) as sock:
                sock.sendall(rpt.to_bytes())
            logging.info(f"Report sent to {self.central_addr}: status {rpt.status}, {len(valid_readings)} readings, {len(anomalies_list)} anomalies.")
        except OSError as exc:
            logging.warning(f"Central server {self.central_addr} unreachable ({exc}) – saving report to disk.")
            report_bytes = rpt.to_bytes()
            (self.unsent_dir / f"{time.time()}.json").write_bytes(report_bytes)
        except Exception as e_general:
            logging.error(f"An unexpected error occurred in _send_report: {e_general}")

    def _retry_unsent_reports_loop(self):
        while not self._stop.is_set():
            time.sleep(UNSENT_REPORTS_RETRY_INTERVAL)
            if not self.unsent_dir.exists() or not any(self.unsent_dir.iterdir()):
                continue # skip if directory doesn't exist or is empty

            logging.info(f"Checking for unsent reports in {self.unsent_dir}...")
            for report_file in list(self.unsent_dir.glob("*.json")):
                if self._stop.is_set(): break # exit early if drone is stopping
                logging.info(f"Attempting to resend {report_file.name}")
                try:
                    report_bytes = report_file.read_bytes()
                    # for simplicity, i assume the file contains exactly what to_bytes() produced
                    # report_data = json.loads(report_bytes.decode().rstrip(DELIM)) # if DELIM was an issue
                    # rpt_obj = DroneReport(**report_data) # this would re-validate if needed

                    with socket.create_connection(self.central_addr, timeout=5) as sock:
                        sock.sendall(report_bytes) #Send raw bytes from file
                    logging.info(f"Successfully resent {report_file.name} to {self.central_addr}")
                    report_file.unlink() #Delete file after successful send
                except FileNotFoundError:
                    logging.warning(f"Unsent report {report_file.name} vanished before sending.")
                except json.JSONDecodeError:
                    logging.error(f"Could not parse {report_file.name} as JSON. Deleting corrupt file.")
                    report_file.unlink()
                except OSError as exc:
                    logging.warning(f"Failed to resend {report_file.name} to {self.central_addr} ({exc}). Will retry later.")
                except Exception as e:
                    logging.error(f"Unexpected error resending {report_file.name}: {e}")

    def manual_drain_battery(self, amount: int):
        if amount <= 0:
            return
        old_level = self.battery.level
        self.battery.level = max(0, self.battery.level - amount)
        logging.info(f"Battery MANUALLY DRAINED by {amount}%. Level: {old_level}% -> {self.battery.level}%.")
        
        # explicitly check and set returning status if thresholds are crossed by manual drain
        if self.battery.level < self.battery.LOW_BATTERY_THRESHOLD and not self.battery.returning:
            self.battery.returning = True
            # when manually drained below new threshold, initiate travel ticks
            logging.warning(f"Battery level CRITICALLY LOW ({self.battery.level}%) due to manual drain. Threshold: {self.battery.LOW_BATTERY_THRESHOLD}%. Drone now RETURNING TO BASE.")
            if self.travel_ticks_remaining == 0: # only set if not already traveling
                self.travel_ticks_remaining = 2
                self.charging_started_log_sent = False
                logging.info("Initiating 2-tick travel time due to manual drain crossing new threshold.")
        elif self.battery.level >= Battery.CRITICAL_BATTERY_THRESHOLD and self.battery.returning:
            self.battery.returning = False
            self.travel_ticks_remaining = 0 # stop travel if any was pending
        
        #GUI will pick up self.battery.level and self.battery.returning in its own refresh cycle
        #DroneReport status will reflect the new self.battery.returning state on the next report generation

    def _monitor_battery(self):
        """
        monitors battery level and logs status changes
        runs in a separate thread
        """
        while not self._stop.is_set():
            logging.info("Battery level: %d%% (Low Threshold: %d%%)", self.battery.level, self.battery.LOW_BATTERY_THRESHOLD)
            if self.battery.level < self.battery.LOW_BATTERY_THRESHOLD:
                logging.warning("Low battery warning: %d%%", self.battery.level)
            if self.battery.level <= 0:
                logging.critical("Battery depleted!")
            time.sleep(BATTERY_CHECK_INTERVAL)

    def stop(self):
        """
        closes all connections and sets the stop event
        """
        logging.info("Drone shutdown initiated.")
        self._stop.set()
        if self.server_socket:
            try:
                # this might interrupt self.server_socket.accept() in _run_server
                self.server_socket.shutdown(socket.SHUT_RDWR) 
                self.server_socket.close()
                logging.info("Server socket explicitly shut down and closed.")
                self.server_socket = None
            except OSError as e:
                logging.warning(f"Error shutting down/closing server socket in stop(): {e}")
            except Exception as e:
                logging.error(f"Unexpected error closing server socket in stop(): {e}")

    def set_low_battery_threshold(self, new_threshold: int):
        """
        updates the low battery threshold
        drones behavior changes based on battery level and threshold:
        - Above threshold: normal operation
        -Below threshold: return to base mode
        - at 0%: critical, stops accepting connections
        """
        if not (5 <= new_threshold <= 80):
            logging.warning(f"Invalid battery threshold {new_threshold}%. Must be between 5% and 80%.")
            return False
            
        current_level = self.battery.level
        currently_returning = self.battery.returning

        if not currently_returning and current_level < new_threshold:
            self.battery.returning = True
            logging.info(f"Drone state changed to RETURNING TO BASE due to new threshold ({new_threshold}%). Current level: {current_level}%.")
            if self.travel_ticks_remaining == 0: # only start travel if not already in a return sequence
                self.travel_ticks_remaining = 2
                self.charging_started_log_sent = False # reset for this new return sequence
                logging.info("Initiating 2-tick travel time.")
        elif currently_returning and current_level >= new_threshold and current_level < Battery.CRITICAL_BATTERY_THRESHOLD:
            logging.info(f"Low battery threshold raised to {new_threshold}%. Drone is currently returning/charging; will continue until active or 0%.")
        elif currently_returning and current_level >= Battery.CRITICAL_BATTERY_THRESHOLD:
            pass 

    def run(self):
        """
        starts all drone operations in separate threads:
        - TCP server for sensors
        - battery monitoring
        - unsent reports retry
        - data forwarding to central
        """
        threading.Thread(target=self._run_server, daemon=True).start()
        threading.Thread(target=self._monitor_battery, daemon=True).start()
        threading.Thread(target=self._retry_unsent_reports_loop, daemon=True).start()
        
        try:
            self._forward_loop()
        finally:
            logging.info("Drone forward loop terminated.")


def main():
    """
    command line arguments
    """
    ap = argparse.ArgumentParser(description="Drone Edge Component")
    ap.add_argument("--port", type=int, default=5001, help="Port to listen on for sensor connections (default: 5001)")
    ap.add_argument("--central_ip", default="127.0.0.1", help="IP address of the central server (default: 127.0.0.1)")
    ap.add_argument("--central_port", type=int, default=6000, help="Port of the central server (default: 6000)")
    args = ap.parse_args()
    
    drone = DroneEdge(listen_port=args.port, central_ip=args.central_ip, central_port=args.central_port)
    drone.run()


if __name__ == "__main__":
    main()