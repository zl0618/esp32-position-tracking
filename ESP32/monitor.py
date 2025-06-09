import serial
import serial.tools.list_ports
import time
import json
import matplotlib.pyplot as plt
from datetime import datetime

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
        
    def monitor_communication(self, duration=60):
        """Monitor ESP-NOW communication for specified duration in seconds"""
        start_time = time.time()
        
        print(f"\nMonitoring ESP-NOW communication for {duration} seconds...")
        print("Press Ctrl+C to stop monitoring early")
        print("=" * 50)
        
        while time.time() - start_time < duration:
            # Read from coordinator
            if self.coord_serial and self.coord_serial.in_waiting:
                try:
                    coord_data = self.coord_serial.readline().decode().strip()
                    if coord_data:  # Only print non-empty lines
                        print(f"[COORD] {coord_data}")
                        self.parse_position_data(coord_data, "coordinator")
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
        
        print("=" * 50)
        print(f"Monitoring complete. Collected {len(self.position_data)} position data points.")
    
    def parse_position_data(self, data, device_type):
        """Parse RSSI and distance data from ESP-NOW serial output"""
        try:
            # Look for different patterns in ESP-NOW output
            if "RSSI:" in data and "dBm" in data:
                # Extract RSSI value
                rssi_start = data.find("RSSI:") + 5
                rssi_end = data.find("dBm", rssi_start)
                rssi = int(data[rssi_start:rssi_end].strip())
                
                # Extract distance if present
                distance = None
                if "Distance:" in data:
                    dist_start = data.find("Distance:") + 9
                    dist_end = data.find("m", dist_start)
                    distance = float(data[dist_start:dist_end].strip())
                else:
                    # Calculate distance from RSSI if not provided
                    distance = self.rssi_to_distance(rssi)
                
                position_entry = {
                    'timestamp': datetime.now().isoformat(),
                    'device': device_type,
                    'rssi': rssi,
                    'distance': distance,
                    'raw_data': data
                }
                
                self.position_data.append(position_entry)
                
            elif "Position report status:" in data or "Send Status:" in data:
                # Log communication status
                print(f"    -> {data}")
                
        except (ValueError, IndexError) as e:
            pass  # Skip malformed data
    
    def rssi_to_distance(self, rssi):
        """Calculate distance from RSSI using path loss formula"""
        import math
        return math.pow(10, (0 - rssi) / 20.0)
    
    def plot_position_data(self):
        """Create plots of RSSI and distance over time"""
        if not self.position_data:
            print("No position data to plot")
            return
        
        # Separate data by device type
        coord_data = [entry for entry in self.position_data if entry['device'] == 'coordinator']
        end_data = [entry for entry in self.position_data if entry['device'] == 'enddevice']
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
        
        # Plot coordinator data
        if coord_data:
            coord_times = [datetime.fromisoformat(entry['timestamp']) for entry in coord_data]
            coord_rssi = [entry['rssi'] for entry in coord_data]
            coord_dist = [entry['distance'] for entry in coord_data]
            
            ax1.plot(coord_times, coord_rssi, 'b-', marker='o', markersize=3, label='Coordinator')
            ax2.plot(coord_times, coord_dist, 'b-', marker='o', markersize=3, label='Coordinator')
        
        # Plot end device data
        if end_data:
            end_times = [datetime.fromisoformat(entry['timestamp']) for entry in end_data]
            end_rssi = [entry['rssi'] for entry in end_data]
            end_dist = [entry['distance'] for entry in end_data]
            
            ax1.plot(end_times, end_rssi, 'r-', marker='s', markersize=3, label='End Device')
            ax2.plot(end_times, end_dist, 'r-', marker='s', markersize=3, label='End Device')
        
        ax1.set_ylabel('RSSI (dBm)')
        ax1.set_title('ESP-NOW Communication Analysis')
        ax1.grid(True)
        ax1.legend()
        
        ax2.set_ylabel('Distance (m)')
        ax2.set_xlabel('Time')
        ax2.grid(True)
        ax2.legend()
        
        plt.tight_layout()
        plt.savefig('esp_now_position_analysis.png')
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
