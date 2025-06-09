#include <WiFi.h>
#include <esp_now.h>
#include <math.h>

#define LED_PIN 2
#define CHANNEL 1

// Position data structure
typedef struct {
    uint16_t device_id;
    int8_t rssi;
    uint32_t timestamp;
    float estimated_distance;
    char message[32];
} position_data_t;

static position_data_t remote_position;
static bool device_connected = false;
static uint8_t peer_mac[6];

// Calculate distance from RSSI (approximate)
float rssi_to_distance(int8_t rssi) {
    // Simple path loss formula: distance = 10^((Tx_Power - RSSI)/(10*n))
    // Assuming Tx_Power = 0dBm, n = 2 (free space)
    return pow(10, (0 - rssi) / 20.0);
}

// Callback when data is received - Updated signature for newer ESP32 core
void onDataReceived(const esp_now_recv_info* recv_info, const uint8_t *data, int data_len) {
    const uint8_t *mac_addr = recv_info->src_addr;
    
    if (data_len == sizeof(position_data_t)) {
        position_data_t received_data;
        memcpy(&received_data, data, sizeof(position_data_t));
        
        // Store the received data and update with current timestamp
        remote_position = received_data;
        remote_position.timestamp = millis();
        
        // Calculate distance from received RSSI
        remote_position.estimated_distance = rssi_to_distance(remote_position.rssi);
        
        device_connected = true;
        
        Serial.printf("Received from: %02X:%02X:%02X:%02X:%02X:%02X\n",
                     mac_addr[0], mac_addr[1], mac_addr[2], 
                     mac_addr[3], mac_addr[4], mac_addr[5]);
        Serial.printf("Message: %s\n", remote_position.message);
        Serial.printf("RSSI: %d dBm, Distance: %.2f m\n", 
                     remote_position.rssi, remote_position.estimated_distance);
        
        // Store peer MAC for direct communication
        memcpy(peer_mac, mac_addr, 6);
    }
}

// Callback when data is sent
void onDataSent(const uint8_t *mac_addr, esp_now_send_status_t status) {
    Serial.printf("Send Status: %s\n", status == ESP_NOW_SEND_SUCCESS ? "Success" : "Failed");
}

void setup() {
    Serial.begin(115200);
    pinMode(LED_PIN, OUTPUT);
    
    Serial.println("ESP-NOW Coordinator Starting...");
    
    // Set WiFi mode
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    
    // Print MAC address
    Serial.printf("Coordinator MAC: %s\n", WiFi.macAddress().c_str());
    
    // Initialize ESP-NOW
    if (esp_now_init() != ESP_OK) {
        Serial.println("Error initializing ESP-NOW");
        return;
    }
    
    // Register callbacks
    esp_now_register_send_cb(onDataSent);
    esp_now_register_recv_cb(onDataReceived);
    
    // Set up broadcast peer for initial discovery
    esp_now_peer_info_t peerInfo = {};
    memset(&peerInfo, 0, sizeof(peerInfo));
    memcpy(peerInfo.peer_addr, "\xFF\xFF\xFF\xFF\xFF\xFF", 6);
    peerInfo.channel = CHANNEL;
    peerInfo.encrypt = false;
    
    if (esp_now_add_peer(&peerInfo) != ESP_OK) {
        Serial.println("Failed to add broadcast peer");
    }
    
    Serial.println("Coordinator ready, waiting for end devices...");
}

void send_discovery_beacon() {
    position_data_t beacon;
    beacon.device_id = 0x0001; // Coordinator ID
    beacon.rssi = 0; // Will be filled by receiver
    beacon.timestamp = millis();
    beacon.estimated_distance = 0.0;
    strcpy(beacon.message, "COORD_DISCOVERY");
    
    // Broadcast discovery beacon
    uint8_t broadcast_mac[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
    esp_now_send(broadcast_mac, (uint8_t*)&beacon, sizeof(beacon));
}

void loop() {
    static unsigned long last_beacon = 0;
    static unsigned long last_status = 0;
    
    // Send discovery beacon every 3 seconds
    if (millis() - last_beacon > 3000) {
        send_discovery_beacon();
        last_beacon = millis();
    }
    
    // Print status every 5 seconds
    if (millis() - last_status > 5000) {
        if (device_connected) {
            Serial.printf("=== Position Update ===\n");
            Serial.printf("Device ID: 0x%04X\n", remote_position.device_id);
            Serial.printf("RSSI: %d dBm\n", remote_position.rssi);
            Serial.printf("Distance: %.2f m\n", remote_position.estimated_distance);
            Serial.printf("Last seen: %lu ms ago\n", millis() - remote_position.timestamp);
            Serial.println("=====================");
        } else {
            Serial.println("No devices connected");
        }
        last_status = millis();
    }
    
    // Reset connection status if no recent data
    if (device_connected && (millis() - remote_position.timestamp > 10000)) {
        device_connected = false;
        Serial.println("Device disconnected (timeout)");
    }
    
    // Blink LED to show status
    digitalWrite(LED_PIN, device_connected ? HIGH : (millis() % 1000 < 500));
    
    delay(100);
}