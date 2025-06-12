# ESP32 Position Tracking System

ESP-NOW based wireless position tracking and communication system using XIAO ESP32C6 devices.

## Features
- Real-time position tracking using RSSI measurements
- Signal smoothing to reduce distance fluctuations
- Automatic device discovery and pairing
- Data logging and visualization
- Python monitoring interface

## Hardware Requirements
- 2x Seeed Studio XIAO ESP32C6
- USB cables for programming and power

## Project Structure
```
ESP32/
├── esp_now_coordinator/
│   └── esp_now_coordinator.ino    # Main coordinator device
├── esp_now_enddevice/
│   └── esp_now_enddevice.ino      # End device that reports position
├── monitor.py                     # Python monitoring script
└── communication.py               # Enhanced monitoring with smoothing
```

## Setup Instructions
1. Flash `esp_now_coordinator.ino` to first ESP32C6
2. Flash `esp_now_enddevice.ino` to second ESP32C6
3. Run `python monitor.py` to monitor communication
4. View real-time distance measurements and plots

## Usage
```bash
cd ESP32
python monitor.py
```

## Distance Calculation
Uses enhanced path-loss model with environmental calibration:
- RSSI smoothing with outlier detection
- Distance smoothing using trimmed mean
- Configurable path loss exponent for different environments
