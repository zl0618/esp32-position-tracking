import serial
import serial.tools.list_ports
import time
import json
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np
from collections import deque

class ESPNowMonitor:
    def __init__(self, coordinator_port=None, enddevice_port=None, baudrate=115200):
        # Auto-detect COM ports if not specified
        if coordinator_port is None or enddevice_port is None:
            available_ports = self.list_available_ports()
            if len(available_ports) < 2:
                raise Exception(f"Need at least 2 COM ports. Found: {available_ports}")
            coordinator_port = coordinator_port or available_ports[0]
            enddevice_port = enddevice_port or available_ports[1]
        
        print(f"Connecting to Coordinator: {coordinator_port}")
        print(f"Connecting to End Device: {enddevice_port}")
        
        # Try to connect with retries and better error handling
        self.coord_serial = None
        self.end_serial = None
        
        try:
            self.coord_serial = self.connect_with_retry(coordinator_port, baudrate, "Coordinator")
            self.end_serial = self.connect_with_retry(enddevice_port, baudrate, "End Device")
        except serial.SerialException as e:
            print(f"Error connecting to serial ports: {e}")
            self.print_troubleshooting()
            raise
        
        self.position_data = []
        
        # Signal smoothing parameters
        self.rssi_history = deque(maxlen=10)  # Keep last 10 RSSI readings
        self.distance_history = deque(maxlen=10)  # Keep last 10 distance readings
        self.smoothing_enabled = True
        self.outlier_threshold = 15  # dBm threshold for outlier detection
    
    def connect_with_retry(self, port, baudrate, device_name, max_retries=3):
        """Try to connect to serial port with retries"""
        for attempt in range(max_retries):
            try:
                print(f"  Attempting to connect to {device_name} on {port} (attempt {attempt + 1}/{max_retries})")
                return serial.Serial(port, baudrate, timeout=1)
            except serial.SerialException as e:
                if "PermissionError" in str(e) or "Access is denied" in str(e):
                    print(f"  Access denied to {port}. This usually means:")
                    print(f"    - Arduino IDE Serial Monitor is open")
                    print(f"    - Another program is using the port")
                    print(f"    - The device is being programmed")
                    if attempt < max_retries - 1:
                        print(f"    Waiting 3 seconds before retry...")
                        time.sleep(3)
                    else:
                        raise Exception(f"Cannot access {port}. Please close Arduino IDE Serial Monitor and try again.")
                else:
                    raise e
    
    def print_troubleshooting(self):
        """Print detailed troubleshooting information"""
        print("\n=== TROUBLESHOOTING ===")
        print("COM Port Access Issues:")
        print("1. Close Arduino IDE Serial Monitor if open")
        print("2. Close any other serial terminal programs")
        print("3. Unplug and replug the ESP32 devices")
        print("4. Try running this script as Administrator")
        print("5. Check Device Manager for COM port conflicts")
        print("\nDevice Issues:")
        print("1. Make sure both ESP32 devices are connected via USB")
        print("2. Verify both devices are programmed with the correct sketches")
        print("3. Check that devices are not stuck in boot/programming mode")
        print("4. Try pressing the reset button on both devices")
        
    def list_available_ports(self):
        """List all available COM ports"""
        ports = serial.tools.list_ports.comports()
        available = [port.device for port in ports]
        print(f"Available COM ports: {available}")
        return available
        
    def parse_position_data(self, data, device_type):
        """Parse RSSI and distance data from ESP-NOW serial output with smoothing"""
        try:
            # Look for different patterns in ESP-NOW output
            if "RSSI:" in data and "dBm" in data:
                # Extract raw RSSI value
                rssi_start = data.find("RSSI:") + 5
                rssi_end = data.find("dBm", rssi_start)
                raw_rssi = int(data[rssi_start:rssi_end].strip())
                
                # Apply smoothing if enabled
                if self.smoothing_enabled:
                    smoothed_rssi = self.smooth_rssi(raw_rssi)
                else:
                    smoothed_rssi = raw_rssi
                
                # Extract distance if present, otherwise calculate
                if "Distance:" in data:
                    dist_start = data.find("Distance:") + 9
                    dist_end = data.find("m", dist_start)
                    raw_distance = float(data[dist_start:dist_end].strip())
                else:
                    raw_distance = self.rssi_to_distance(smoothed_rssi)
                
                # Apply distance smoothing
                smoothed_distance = self.smooth_distance(raw_distance)
                
                position_entry = {
                    'timestamp': datetime.now().isoformat(),
                    'device': device_type,
                    'rssi': smoothed_rssi,
                    'raw_rssi': raw_rssi,
                    'distance': smoothed_distance,
                    'raw_distance': raw_distance,
                    'raw_data': data
                }
                
                self.position_data.append(position_entry)
                
            elif "Position report status:" in data or "Send Status:" in data:
                # Log communication status
                print(f"    -> {data}")
                
        except (ValueError, IndexError) as e:
            pass  # Skip malformed data
    
    def smooth_rssi(self, new_rssi):
        """Apply smoothing to RSSI readings to reduce fluctuations"""
        # Remove outliers before adding to history
        if self.rssi_history:
            median_rssi = np.median(list(self.rssi_history))
            if abs(new_rssi - median_rssi) > self.outlier_threshold:
                # Use median instead of outlier
                new_rssi = int(median_rssi)
        
        # Add to history
        self.rssi_history.append(new_rssi)
        
        # Calculate smoothed value using weighted average
        if len(self.rssi_history) >= 3:
            # Give more weight to recent readings
            weights = np.linspace(0.5, 1.0, len(self.rssi_history))
            smoothed = np.average(list(self.rssi_history), weights=weights)
            return int(smoothed)
        else:
            return new_rssi
    
    def smooth_distance(self, new_distance):
        """Apply smoothing to distance calculations"""
        # Add to history
        self.distance_history.append(new_distance)
        
        # Calculate smoothed distance using moving average
        if len(self.distance_history) >= 5:
            # Use median filter to remove spikes, then moving average
            sorted_distances = sorted(list(self.distance_history))
            # Remove extreme values (top and bottom 10%)
            trim_count = max(1, len(sorted_distances) // 10)
            trimmed = sorted_distances[trim_count:-trim_count] if trim_count < len(sorted_distances)//2 else sorted_distances
            return np.mean(trimmed)
        else:
            return new_distance
    
    def rssi_to_distance(self, rssi):
        """Improved distance calculation with environmental factors"""
        import math
        
        # Enhanced path loss model with calibration
        # d = 10^((Tx_Power - RSSI - A) / (10 * n))
        # Where: A = RSSI at 1m reference distance
        #        n = path loss exponent (2 for free space, 2-4 for indoor)
        
        tx_power = 0        # ESP32 transmission power in dBm
        rssi_1m = -40       # Measured RSSI at 1 meter (calibration value)
        path_loss_exp = 2.5 # Path loss exponent for indoor environment
        
        if rssi == 0:
            return 0.0
        
        # Calculate distance
        distance = math.pow(10, (tx_power - rssi - rssi_1m) / (10 * path_loss_exp))
        
        # Apply bounds (ESP-NOW typical range)
        distance = max(0.1, min(distance, 100.0))
        
        return round(distance, 2)
    
    def get_signal_quality(self, rssi):
        """Determine signal quality based on RSSI"""
        if rssi >= -30:
            return "Excellent"
        elif rssi >= -50:
            return "Good"
        elif rssi >= -60:
            return "Fair"
        elif rssi >= -70:
            return "Poor"
        else:
            return "Very Poor"
    
    def monitor_communication(self, duration=60):
        """Monitor ESP-NOW communication for specified duration in seconds"""
        start_time = time.time()
        
        print(f"\nMonitoring ESP-NOW communication for {duration} seconds...")
        print("Signal smoothing: ENABLED (reduces fluctuations)")
        print("Press Ctrl+C to stop monitoring early")
        print("=" * 60)
        
        while time.time() - start_time < duration:
            # Read from coordinator
            if self.coord_serial and self.coord_serial.in_waiting:
                try:
                    coord_data = self.coord_serial.readline().decode().strip()
                    if coord_data:  # Only print non-empty lines
                        print(f"[COORD] {coord_data}")
                        self.parse_position_data(coord_data, "coordinator")
                        
                        # Show signal quality for distance readings
                        if "RSSI:" in coord_data and self.position_data:
                            last_entry = self.position_data[-1]
                            quality = self.get_signal_quality(last_entry['rssi'])
                            print(f"        Signal: {quality} | Smoothed Distance: {last_entry['distance']}m")
                            
                except (UnicodeDecodeError, serial.SerialException):
                    pass  # Skip malformed data or connection issues
            
            # Read from end device
            if self.end_serial and self.end_serial.in_waiting:
                try:
                    end_data = self.end_serial.readline().decode().strip()
                    if end_data:  # Only print non-empty lines
                        print(f"[END] {end_data}")
                        self.parse_position_data(end_data, "enddevice")
                except (UnicodeDecodeError, serial.SerialException):
                    pass  # Skip malformed data or connection issues
            
            time.sleep(0.1)
        
        print("=" * 60)
        print(f"Monitoring complete. Collected {len(self.position_data)} position data points.")
        
        # Print summary statistics
        if self.position_data:
            distances = [entry['distance'] for entry in self.position_data]
            print(f"Distance stats: Min={min(distances):.2f}m, Max={max(distances):.2f}m, Avg={np.mean(distances):.2f}m")
    
    def plot_position_data(self):
        """Create enhanced plots showing both raw and smoothed data"""
        if not self.position_data:
            print("No position data to plot")
            return
        
        # Separate data by device type
        coord_data = [entry for entry in self.position_data if entry['device'] == 'coordinator']
        end_data = [entry for entry in self.position_data if entry['device'] == 'enddevice']
        
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
        
        # Plot coordinator data
        if coord_data:
            coord_times = [datetime.fromisoformat(entry['timestamp']) for entry in coord_data]
            coord_rssi_raw = [entry.get('raw_rssi', entry['rssi']) for entry in coord_data]
            coord_rssi_smooth = [entry['rssi'] for entry in coord_data]
            coord_dist_raw = [entry.get('raw_distance', entry['distance']) for entry in coord_data]
            coord_dist_smooth = [entry['distance'] for entry in coord_data]
            
            # RSSI plots
            ax1.plot(coord_times, coord_rssi_raw, 'lightblue', alpha=0.7, label='Raw RSSI')
            ax1.plot(coord_times, coord_rssi_smooth, 'b-', linewidth=2, label='Smoothed RSSI')
            ax1.set_ylabel('RSSI (dBm)')
            ax1.set_title('Coordinator RSSI - Raw vs Smoothed')
            ax1.grid(True)
            ax1.legend()
            
            # Distance plots
            ax3.plot(coord_times, coord_dist_raw, 'lightcoral', alpha=0.7, label='Raw Distance')
            ax3.plot(coord_times, coord_dist_smooth, 'r-', linewidth=2, label='Smoothed Distance')
            ax3.set_ylabel('Distance (m)')
            ax3.set_xlabel('Time')
            ax3.set_title('Coordinator Distance - Raw vs Smoothed')
            ax3.grid(True)
            ax3.legend()
        
        # Plot end device data
        if end_data:
            end_times = [datetime.fromisoformat(entry['timestamp']) for entry in end_data]
            end_rssi_raw = [entry.get('raw_rssi', entry['rssi']) for entry in end_data]
            end_rssi_smooth = [entry['rssi'] for entry in end_data]
            end_dist_raw = [entry.get('raw_distance', entry['distance']) for entry in end_data]
            end_dist_smooth = [entry['distance'] for entry in end_data]
            
            # RSSI plots
            ax2.plot(end_times, end_rssi_raw, 'lightgreen', alpha=0.7, label='Raw RSSI')
            ax2.plot(end_times, end_rssi_smooth, 'g-', linewidth=2, label='Smoothed RSSI')
            ax2.set_ylabel('RSSI (dBm)')
            ax2.set_title('End Device RSSI - Raw vs Smoothed')
            ax2.grid(True)
            ax2.legend()
            
            # Distance plots
            ax4.plot(end_times, end_dist_raw, 'lightsalmon', alpha=0.7, label='Raw Distance')
            ax4.plot(end_times, end_dist_smooth, 'orange', linewidth=2, label='Smoothed Distance')
            ax4.set_ylabel('Distance (m)')
            ax4.set_xlabel('Time')
            ax4.set_title('End Device Distance - Raw vs Smoothed')
            ax4.grid(True)
            ax4.legend()
        
        plt.tight_layout()
        plt.savefig('esp_now_position_analysis_smoothed.png', dpi=300)
        plt.show()
    
    def save_data(self, filename="esp_now_data.json"):
        """Save collected data to JSON file"""
        with open(filename, 'w') as f:
            json.dump(self.position_data, f, indent=2)
        print(f"Data saved to {filename}")
    
    def close(self):
        """Close serial connections"""
        if self.coord_serial:
            self.coord_serial.close()
        if self.end_serial:
            self.end_serial.close()

# Example usage
if __name__ == "__main__":
    print("ESP-NOW Position Monitoring System")
    print("=" * 40)
    
    try:
        # Auto-detect COM ports or specify manually
        monitor = ESPNowMonitor()  # Will auto-detect ports
        # monitor = ESPNowMonitor("COM3", "COM7")  # Manual specification
        
        monitor.monitor_communication(duration=60)  # Monitor for 1 minute
        monitor.plot_position_data()
        monitor.save_data()
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        try:
            if 'monitor' in locals():
                monitor.close()
        except:
            pass
