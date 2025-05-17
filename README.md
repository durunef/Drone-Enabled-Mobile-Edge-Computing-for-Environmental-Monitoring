# Drone-Enabled Mobile Edge Computing for Environmental Monitoring

This project implements a distributed system for environmental monitoring using drones as edge computing nodes. The system consists of three main components: Sensor Nodes, Drone Edge, and Central Server.

## System Architecture

```
Sensor Nodes -> Drone Edge -> Central Server
   (TCP)         (TCP)         (GUI)
```

### Components

1. **Sensor Nodes**: Simulate environmental sensors sending temperature and humidity data
2. **Drone Edge**: Acts as both TCP server (for sensors) and client (to central), with edge processing
3. **Central Server**: Receives processed data and provides visualization

## Setup and Installation

### Prerequisites

- Python 3.8 or higher
- Tkinter (for GUI components)

## Running the System

### 1. Start the Central Server

```bash
# Start the Central Server GUI (default port 6000)
python central_server/gui_central.py --host 0.0.0.0 --port 6000
```

### 2. Start the Drone Edge

```bash
# Start the Drone Edge GUI (default sensor port 5001, connects to central at localhost:6000)
python drone_edge/gui_drone.py --port 5001 --central-host 127.0.0.1 --central-port 6000
```

### 3. Start Sensor Nodes

```bash
# Start a normal sensor (sends random data)
python sensors/sensor.py --sensor_id sensor1 --drone_ip 127.0.0.1 --drone_port 5001 --interval 2.0

# Start an anomaly testing sensor (sends out-of-range values)
python sensors/sensor.py --sensor_id anomaly_test --drone_ip 127.0.0.1 --drone_port 5001 --temperature 1000 --humidity 200
```

## Component Details

### Sensor Nodes (`sensors/sensor.py`)
- Simulates environmental sensors
- Sends temperature and humidity readings to Drone
- Supports fixed or random value generation
- Automatic reconnection on failure

### Drone Edge (`drone_edge/`)
- TCP server for sensors
- Edge processing (averaging, anomaly detection)
- Battery simulation with return-to-base behavior
- GUI dashboard showing real-time status
- Forwards processed data to Central Server

### Central Server (`central_server/`)
- Receives processed data from Drone
- Real-time visualization of:
  - Average temperature and humidity
  - Anomaly reports
  - Drone status and battery level
  - Connected sensor count

## Configuration

### Logging
- All components log to both console and `logs/system.log`
- Log level can be adjusted in `logconf.py`

### Thresholds
- Temperature normal range: 0-40°C
- Humidity normal range: 10-90%
- Battery low threshold: 20% (configurable via GUI)

## Testing

To test anomaly detection:
1. Start all components
2. Run a sensor with extreme values:
```bash
python sensors/sensor.py --temperature 1000 --humidity 200
```

## Troubleshooting

1. **Connection Refused**
   - Ensure components are started in order: Central -> Drone -> Sensors
   - Check if ports are available

2. **No Data in Central Server**
   - Verify Drone's central_ip and central_port settings
   - Check if any firewall is blocking connections

3. **GUI Not Showing**
   - Ensure Tkinter is installed
   - Check system logs for error messages 