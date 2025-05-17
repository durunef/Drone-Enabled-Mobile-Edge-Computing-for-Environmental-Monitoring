"""
Drone Edge GUI Component
-real-time display of sensor readings and anomalies
-battery level monitoring with visual indicators
-interactive controls for battery simulation and threshold adjustment
-comprehensive event logging
-multi-tabbed interface for different data views

Layout:
1. Left:
   -battery level indicator and status
   -interactive controls (battery drain, threshold adjustment)
   -data display

2. Right:
   -live sensor readings: table of recent readings
   -detected anomalies: list of out-of-range values
   -event log: system events and status changes

usage:
    python gui_drone.py [--port PORT] [--central-host HOST] [--central-port PORT]
"""
import threading
import queue
import time
import argparse
import logging
from tkinter import Tk, ttk, StringVar, scrolledtext, IntVar

# Add parent directory to path for module resolution
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from common.battery import Battery
from drone_edge.drone import DroneEdge
from common.messages import SensorReading, DroneReport

# Queue for log messages to be displayed in the GUI
gui_log_queue = queue.Queue()

class QueueLogHandler(logging.Handler):
    """
    a custom logging handler that writes log records to a queue for GUI display
    enables thread-safe logging from multiple components to the GUI
    """
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        log_entry = self.format(record)
        self.log_queue.put(log_entry)

class DroneGUI(Tk):
    """
    main GUI window for the Drone Edge component
    provides a real-time interface for monitoring drone status, sensor data, and system events
    """
    MAX_ROWS_SENSORS = 15
    MAX_ROWS_ANOMALIES = 10
    MAX_LOG_ENTRIES = 100

    def __init__(self, drone: DroneEdge):
        """
        creates the main window layout with:
        - status displays and controls (left pane)
        - data views in tabs (right pane)
        - periodic refresh for real-time updates
        """
        super().__init__()
        self.drone = drone

        # window setup
        self.title("Drone Edge - Monitoring Dashboard")
        self.geometry("800x750")
        self.resizable(True, True)

        # main panes
        main_pane = ttk.PanedWindow(self, orient="horizontal")
        main_pane.pack(fill="both", expand=True, padx=10, pady=10)

        left_pane = ttk.Frame(main_pane, padding=5)
        main_pane.add(left_pane, weight=1)

        right_pane = ttk.Frame(main_pane, padding=5)
        main_pane.add(right_pane, weight=2)

        # left pane: status & controls
        status_frame = ttk.LabelFrame(left_pane, text="Drone Status", padding=10)
        status_frame.pack(fill="x", pady=5)

        self.batt_var = StringVar(value=f"Battery: {drone.battery.level} %")
        self.battery_label = ttk.Label(status_frame, textvariable=self.batt_var)
        self.battery_label.pack(pady=(0,2))
        self.progress = ttk.Progressbar(
            status_frame,
            orient="horizontal",
            mode="determinate",
            length=200,
            maximum=100,
            value=drone.battery.level,
        )
        self.progress.pack(pady=(0, 10))

        self.drone_status_var = StringVar(value="Status: Unknown")
        ttk.Label(status_frame, textvariable=self.drone_status_var).pack(pady=2)
        
        self.returning_banner_var = StringVar(value="")
        self.returning_banner_label = ttk.Label(status_frame, textvariable=self.returning_banner_var, foreground="red", font=("Helvetica", 10, "bold"))
        self.returning_banner_label.pack(pady=2)

        # interactive controls frame
        controls_frame = ttk.LabelFrame(left_pane, text="Controls", padding=10)
        controls_frame.pack(fill="x", pady=5, after=status_frame)

        self.drain_button = ttk.Button(controls_frame, text="Simulate Event: Drain Battery (-10%)", command=self._simulate_battery_drain)
        self.drain_button.pack(pady=5, fill="x")

        # low battery threshold slider
        ttk.Label(controls_frame, text="Low Battery Threshold (%):").pack(pady=(10,0))
        self.threshold_val_var = IntVar(value=self.drone.battery.LOW_BATTERY_THRESHOLD) # Initial value from drone's battery
        self.threshold_label_var = StringVar(value=f"{self.threshold_val_var.get()}%")
        
        self.threshold_slider = ttk.Scale(
            controls_frame, 
            from_=5, 
            to=50, 
            orient="horizontal", 
            variable=self.threshold_val_var,
            command=self._on_low_threshold_slider_changed
        )
        self.threshold_slider.pack(fill="x", pady=(0,2))
        ttk.Label(controls_frame, textvariable=self.threshold_label_var).pack()

        # aggregated data display
        agg_frame = ttk.LabelFrame(left_pane, text="Aggregated Data (from last report)", padding=10)
        agg_frame.pack(fill="x", pady=5, after=controls_frame)

        self.avg_temp_var = StringVar(value="Avg Temp: --.-")
        ttk.Label(agg_frame, textvariable=self.avg_temp_var).pack(anchor="w")
        self.avg_hum_var = StringVar(value="Avg Hum: --%")
        ttk.Label(agg_frame, textvariable=self.avg_hum_var).pack(anchor="w")
        self.sensor_count_var = StringVar(value="Sensors in report: -")
        ttk.Label(agg_frame, textvariable=self.sensor_count_var).pack(anchor="w")

        # right pane: data views (tabbed)
        notebook = ttk.Notebook(right_pane)
        notebook.pack(fill="both", expand=True)

        # sensor readings tab
        sensor_tab = ttk.Frame(notebook, padding=5)
        notebook.add(sensor_tab, text='Live Sensor Readings')
        self.sensor_tree = ttk.Treeview(
            sensor_tab,
            columns=("timestamp", "sensor", "temp", "humidity"),
            show="headings",
            height=8,
        )
        self.sensor_tree.heading("timestamp", text="Timestamp")
        self.sensor_tree.heading("sensor", text="Sensor ID")
        self.sensor_tree.heading("temp", text="Temp (°C)")
        self.sensor_tree.heading("humidity", text="Hum (%)")
        self.sensor_tree.column("timestamp", anchor="w", width=150)
        self.sensor_tree.column("sensor", anchor="center", width=100)
        self.sensor_tree.column("temp", anchor="center", width=80)
        self.sensor_tree.column("humidity", anchor="center", width=80)
        self.sensor_tree.pack(fill="both", expand=True)

        # anomalies tab
        anomaly_tab = ttk.Frame(notebook, padding=5)
        notebook.add(anomaly_tab, text='Detected Anomalies')
        self.anomaly_tree = ttk.Treeview(
            anomaly_tab,
            columns=("ts", "sensor_id", "value"),
            show="headings",
            height=8
        )
        self.anomaly_tree.heading("ts", text="Timestamp")
        self.anomaly_tree.heading("sensor_id", text="Sensor ID")
        self.anomaly_tree.heading("value", text="Value (T, H)")
        self.anomaly_tree.column("ts", anchor="w", width=150)
        self.anomaly_tree.column("sensor_id", anchor="center", width=100)
        self.anomaly_tree.column("value", anchor="w", width=150)
        self.anomaly_tree.pack(fill="both", expand=True)
        
        # event log tab
        log_tab = ttk.Frame(notebook, padding=5)
        notebook.add(log_tab, text='Event Log')
        self.log_text_area = scrolledtext.ScrolledText(log_tab, state='disabled', height=10, wrap='char', font=("TkFixedFont", 9))
        self.log_text_area.pack(fill='both', expand=True)
        self.log_text_area.configure(state='normal')
        self.log_text_area.insert('end', "Drone GUI log initialized.\n")
        self.log_text_area.configure(state='disabled')
        self.log_text_area.see('end')
        self.after(250, self._refresh)

    def _simulate_battery_drain(self):
        """
        triggers a 10% battery drain and logs the action
        """
        if self.drone:
            drain_amount = 10
            self.drone.manual_drain_battery(drain_amount)
            log_message = f"GUI Action: Simulated battery drain of {drain_amount}% triggered."
            self.log_text_area.configure(state='normal')
            self.log_text_area.insert('end', log_message + '\n')
            self.log_text_area.configure(state='disabled')
            self.log_text_area.see('end')

    def _on_low_threshold_slider_changed(self, value_str):
        """
        handles changes to the low battery threshold slider
        updates the threshold display and drone configuration
        """
        try:
            new_threshold = int(float(value_str))
            self.threshold_label_var.set(f"{new_threshold}%")
            if self.drone:
                self.drone.set_low_battery_threshold(new_threshold)
                log_message = f"GUI Action: Low battery threshold set to {new_threshold}%."
                self.log_text_area.configure(state='normal')
                self.log_text_area.insert('end', log_message + '\n')
                self.log_text_area.configure(state='disabled')
                self.log_text_area.see('end')
        except ValueError:
            pass

    def _update_sensor_tree(self, reading: SensorReading):
        """
        updates the sensor readings table with a new reading
        maintains a maximum number of rows by removing oldest entries
        """
        self.sensor_tree.insert(
            "",
            0,
            values=(
                reading.timestamp.split('.')[0],
                reading.sensor_id,
                f"{reading.temperature:.1f}",
                f"{reading.humidity:.0f}",
            ),
        )
        # Keep only latest rows
        for iid in self.sensor_tree.get_children()[self.MAX_ROWS_SENSORS:]:
            self.sensor_tree.delete(iid)

    def _update_aggregated_data(self, report: DroneReport):
        """
        updates the aggregated data display with a new drone report
        updates averages, status, and anomaly information
        """
        self.avg_temp_var.set(f"Avg Temp: {report.avg_temperature:.1f}°C")
        self.avg_hum_var.set(f"Avg Hum: {report.avg_humidity:.0f}%")
        self.drone_status_var.set(f"Status: {report.status.capitalize()}")
        self.sensor_count_var.set(f"Sensors in report: {report.sensor_count}")

        for iid in self.anomaly_tree.get_children():
            self.anomaly_tree.delete(iid)
        
        for anomaly in report.anomalies:
            self.anomaly_tree.insert(
                "",
                "end",
                values=(
                    anomaly.get('ts', '').split('.')[0],
                    anomaly.get('sensor_id', 'N/A'),
                    str(anomaly.get('val', 'N/A'))
                )
            )
        for iid in self.anomaly_tree.get_children()[:-self.MAX_ROWS_ANOMALIES]:
             self.anomaly_tree.delete(iid)

    def _refresh(self):
        """
        for updating all GUI elements
        - battery status updates
        - processing new sensor readings
        - processing new drone reports
        - updating log messages
        
        called every 250ms by the Tkinter event loop
        """
        level = self.drone.battery.level
        self.progress["value"] = level
        self.batt_var.set(f"Battery: {level} %")

        if self.drone.battery.returning:
            self.returning_banner_var.set("Status: RETURNING TO BASE (Low Battery)")
            self.returning_banner_label.config(foreground="red")
        else:
            if self.drone_status_var.get().startswith("Status: Active") :
                 self.returning_banner_var.set("")

        # process items from the drone's GUI data queue
        items_processed_this_cycle = 0
        while not self.drone.gui_q.empty():
            if items_processed_this_cycle >= 10:
                break
            try:
                item = self.drone.gui_q.get_nowait()
                if isinstance(item, SensorReading):
                    self._update_sensor_tree(item)
                elif isinstance(item, DroneReport):
                    self._update_aggregated_data(item)
                items_processed_this_cycle += 1
            except queue.Empty:
                break 
        
        log_items_processed = 0
        while not gui_log_queue.empty():
            if log_items_processed >= 20:
                break
            try:
                log_message = gui_log_queue.get_nowait()
                self.log_text_area.configure(state='normal')
                self.log_text_area.insert('end', log_message + '\n')
                self.log_text_area.configure(state='disabled')
                self.log_text_area.see('end')
                current_lines = int(self.log_text_area.index('end-1c').split('.')[0])
                if current_lines > self.MAX_LOG_ENTRIES:
                    self.log_text_area.configure(state='normal')
                    self.log_text_area.delete('1.0', f'{current_lines - self.MAX_LOG_ENTRIES + 1}.0')
                    self.log_text_area.configure(state='disabled')
                log_items_processed +=1
            except queue.Empty:
                break
            except Exception as e:
                print(f"Error processing log queue for GUI: {e}")
                break

        self.after(250, self._refresh)


def main():
    parser = argparse.ArgumentParser(description="Run Drone Edge with GUI.")
    parser.add_argument("--port", type=int, default=5001, help="Port for DroneEdge to listen on (default: 5001)")
    parser.add_argument("--central-host", dest='central_ip', default="127.0.0.1", help="IP address of the Central Server (default: 127.0.0.1)")
    parser.add_argument("--central-port", type=int, default=6000, help="Port of the Central Server (default: 6000)")
    args = parser.parse_args()

    #configure logging for GUI 
    log_formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(name)-15s | %(message)s")
    gui_handler = QueueLogHandler(gui_log_queue)
    gui_handler.setFormatter(log_formatter)
    gui_handler.setLevel(logging.INFO)

    #add GUI handler to root logger
    logging.getLogger().addHandler(gui_handler)

    #create and run DroneEdge in a separate thread
    drone = DroneEdge(
        listen_port=args.port, 
        central_ip=args.central_ip, 
        central_port=args.central_port
    )
    threading.Thread(target=drone.run, daemon=True).start()
    
    #start
    app = DroneGUI(drone)
    app.mainloop()


if __name__ == "__main__":
    main()