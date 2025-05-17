# System Architecture - Drone-Enabled Mobile Edge Computing Environmental Monitoring

## Overview

This system implements a distributed environmental monitoring solution using drones as edge computing nodes. The architecture follows a three-tier model with sensor nodes, edge processing (drone), and a central server.

## System Flow

1. **Data Collection Layer (Sensor Nodes)**
   - Environmental sensors collect temperature and humidity data
   - Each sensor operates independently and connects to the Drone Edge via TCP
   - Sensors can send either random data within normal ranges or fixed test values
   - Automatic reconnection handling ensures data continuity

2. **Edge Processing Layer (Drone)**
   - Acts as both TCP server (for sensors) and TCP client (to central)
   - Performs real-time data aggregation and anomaly detection
   - Implements battery management with return-to-base behavior
   - Features:
     - Batches sensor readings (5 readings per batch)
     - Calculates averages and detects anomalies
     - Queues data during low-battery states
     - Provides real-time GUI monitoring

3. **Central Monitoring Layer (Server)**
   - Receives processed data from Drone Edge
   - Provides comprehensive visualization and monitoring
   - Supports multiple drone connections
   - Maintains system-wide logging

## Data Flow

```
[Sensor Node 1] ─┐
[Sensor Node 2] ─┼─TCP─→ [Drone Edge] ─TCP─→ [Central Server]
[Sensor Node n] ─┘

- Sensor → Drone: SensorReading messages
- Drone → Central: DroneReport messages
```

## Component Details

### 1. Sensor Nodes (`sensors/sensor.py`)
- **Input**: Simulated or fixed environmental data
- **Output**: SensorReading messages (JSON over TCP)
- **Features**:
  - Configurable data generation
  - Automatic reconnection
  - Error handling
  - Normal ranges: Temp (20-30°C), Humidity (40-60%)

### 2. Drone Edge (`drone_edge/`)
- **Input**: SensorReading messages from multiple sensors
- **Output**: DroneReport messages to central server
- **Processing**:
  - Data aggregation (batching)
  - Anomaly detection
  - Battery management
- **Thresholds**:
  - Temperature: 0-40°C
  - Humidity: 10-90%
  - Battery Low: 20%
  - Battery Critical: 90%

### 3. Central Server (`central_server/`)
- **Input**: DroneReport messages from drones
- **Output**: Visual display and logs
- **Features**:
  - Real-time monitoring
  - Anomaly tracking
  - System-wide logging
  - Multi-drone support

## Message Formats

### SensorReading
```json
{
    "sensor_id": "sensor1",
    "temperature": 25.6,
    "humidity": 45,
    "timestamp": "2025-05-14T14:29:39.439Z"
}
```

### DroneReport
```json
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
```

## System States

### Drone States
1. **Active**
   - Normal operation
   - Accepting sensor connections
   - Processing and forwarding data
   - Battery draining at normal rate

2. **Returning to Base**
   - Triggered by low battery (< 20%)
   - Queues incoming sensor data
   - Simulated travel time (2 ticks)
   - No data forwarding to central

3. **Charging**
   - At base station
   - Battery recharging
   - Resumes active state at 90%

### Sensor States
1. **Connected**: Sending data normally
2. **Disconnected**: Attempting reconnection
3. **Error**: Handling connection failures

## Network Architecture

- **Protocol**: TCP for reliable data transmission
- **Ports**:
  - Sensors → Drone: 5001 (default)
  - Drone → Central: 6000 (default)
- **Addressing**: IPv4
- **Message Delimitation**: Newline character

## GUI Components

### Drone Edge GUI
- Battery status display
- Live sensor readings
- Anomaly detection
- Interactive controls
- Event logging

### Central Server GUI
- Drone status monitoring
- Aggregated data display
- Anomaly tracking
- System-wide logging

## Error Handling

1. **Network Failures**
   - Automatic reconnection
   - Data queuing
   - Comprehensive logging

2. **Battery Management**
   - Low battery detection
   - Return-to-base behavior
   - Critical level shutdown

3. **Data Validation**
   - JSON parsing
   - Value range checking
   - Message format validation

## Logging

- All components log to both console and file
- Centralized logging configuration
- UTC timestamps
- Consistent format across components 