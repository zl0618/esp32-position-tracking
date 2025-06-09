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

static position_data_t coordinator_position;
static bool coordinator_found = false;
static uint8_t coordinator_mac[6];

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
        memcpy(&received_data, data, sizeof(received_data));
        
        // Check if this is a coordinator beacon
        if (strstr(received_data.message, "COORD_DISCOVERY") != NULL) {
            coordinator_found = true;
            memcpy(coordinator_mac, mac_addr, 6);
            
            Serial.printf("Found coordinator: %02X:%02X:%02X:%02X:%02X:%02X\n",
                         mac_addr[0], mac_addr[1], mac_addr[2], 
                         mac_addr[3], mac_addr[4], mac_addr[5]);
            
            // Add coordinator as peer if not already added
            if (!esp_now_is_peer_exist(coordinator_mac)) {
                esp_now_peer_info_t peerInfo = {};
                memcpy(peerInfo.peer_addr, coordinator_mac, 6);
                peerInfo.channel = CHANNEL;
                peerInfo.encrypt = false;
                esp_now_add_peer(&peerInfo);
            }
        }
    }
}

// Callback when data is sent
void onDataSent(const uint8_t *mac_addr, esp_now_send_status_t status) {
    Serial.printf("Position report status: %s\n", 
                 status == ESP_NOW_SEND_SUCCESS ? "Success" : "Failed");
}

void setup() {
    Serial.begin(115200);
    pinMode(LED_PIN, OUTPUT);
    
    Serial.println("ESP-NOW End Device Starting...");
    
    // Set WiFi mode
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    
    // Print MAC address
    Serial.printf("End Device MAC: %s\n", WiFi.macAddress().c_str());
    
    // Initialize ESP-NOW
    if (esp_now_init() != ESP_OK) {
        Serial.println("Error initializing ESP-NOW");
        return;
    }
    
    // Register callbacks
    esp_now_register_send_cb(onDataSent);
    esp_now_register_recv_cb(onDataReceived);
    
    Serial.println("End device ready, searching for coordinator...");
}

void send_position_report() {
    if (coordinator_found) {
        // Simulate RSSI measurement (in real implementation, you'd measure actual signal strength)
        static int8_t simulated_rssi = -50;
        simulated_rssi += random(-5, 6); // Add variation
        if (simulated_rssi < -90) simulated_rssi = -90;
        if (simulated_rssi > -30) simulated_rssi = -30;
        
        position_data_t report;
        report.device_id = 0x0002; // End device ID
        report.rssi = simulated_rssi;
        report.timestamp = millis();
        report.estimated_distance = rssi_to_distance(simulated_rssi);
        strcpy(report.message, "POSITION_REPORT");
        
        // Send position report to coordinator
        esp_now_send(coordinator_mac, (uint8_t*)&report, sizeof(report));
        
        Serial.printf("Sent position report - RSSI: %d dBm, Distance: %.2f m\n", 
                     report.rssi, report.estimated_distance);
    }
}

void loop() {
    static unsigned long last_report = 0;
    static unsigned long last_status = 0;
    static unsigned long last_coordinator_seen = 0;
    
    // Send position report every 2 seconds if coordinator is found
    if (coordinator_found && (millis() - last_report > 2000)) {
        send_position_report();
        last_report = millis();
        last_coordinator_seen = millis();
    }
    
    // Print status every 5 seconds
    if (millis() - last_status > 5000) {
        if (coordinator_found) {
            Serial.printf("=== End Device Status ===\n");
            Serial.printf("Coordinator found: YES\n");
            Serial.printf("Last report: %lu ms ago\n", millis() - last_report);
            Serial.println("========================");
        } else {
            Serial.println("Searching for coordinator...");
        }
        last_status = millis();
    }
    
    // Reset coordinator status if no recent beacon
    if (coordinator_found && (millis() - last_coordinator_seen > 15000)) {
        coordinator_found = false;
        Serial.println("Coordinator lost (timeout)");
    }
    
    // Blink LED to show status
    digitalWrite(LED_PIN, coordinator_found ? HIGH : (millis() % 500 < 250));
    
    delay(100);
}
