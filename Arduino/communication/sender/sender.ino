#include <WiFi.h>
#include <WebSocketsClient.h>
#include <Wire.h>
#include <7Semi_INA219.h>

#define CONTROL_PIN 5
#define JOULES_PER_UNIT 5.0

#define SDA_PIN 21
#define SCL_PIN 22

INA219_7Semi ina(0x40);

const char* ssid = "I have internet";
const char* password = "digak628@_99";

float voltage = 0;
float current = 0;
bool connect_status = 0;

float vBus_V     = 0;
float vShunt_mV  = 0;
float current_mA = 0;
float power_mW   = 0;
bool ovf         = false;

const char* host = "10.74.47.171";
const uint16_t port = 5000;

WebSocketsClient webSocket;

String role = "unknown";
String mac;

float totalEnergy_J = 0.0;
float targetEnergy_J = 0.0;

unsigned long lastTime = 0;

bool transferActive = false;

void startReceive(float joules)
{
    targetEnergy_J = joules;
    totalEnergy_J = 0;
    lastTime = millis();
    transferActive = true;

    Serial.print("Receiving energy target: ");
    Serial.print(joules);
    Serial.println(" J");
}

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length)
{
    switch(type)
    {
        case WStype_CONNECTED:
        {
            Serial.println("Connected to server");
            connect_status = 1;

            mac = WiFi.macAddress();
            webSocket.sendTXT("REGISTER:" + mac);
            break;
        }

        case WStype_TEXT:
        {
            String msg = String((char*)payload);

            Serial.print("Received: ");
            Serial.println(msg);

            if (msg.startsWith("ROLE:"))
            {
                role = msg.substring(5);
                Serial.print("Role assigned: ");
                Serial.println(role);
            }

            if (msg.startsWith("UNITS:"))
            {
                int units = msg.substring(6).toInt();
                float joules = units * JOULES_PER_UNIT;

                Serial.print("Units Input: ");
                Serial.println(units);

                Serial.print("Converted Joules: ");
                Serial.println(joules);

                startReceive(joules);
                webSocket.sendTXT("UNITS_RECEIVED");
            }

            break;
        }

        case WStype_DISCONNECTED:
        {
            Serial.println("Disconnected from server");
            Serial.println(WiFi.localIP());
            connect_status = 0;
            break;
        }

        default:
            break;
    }
}

void setup()
{
    Serial.begin(115200);

    Wire.begin(SDA_PIN, SCL_PIN);
    ina.begin(&Wire);

    bool range16V = false;
    uint8_t pga   = 3;
    uint8_t badc  = 0x0B;
    uint8_t sadc  = 0x0B;
    uint8_t mode  = 0x07;

    ina.configure(range16V, pga, badc, sadc, mode);

    float maxExpected_A = 2.0;
    float shunt_Ohms    = 0.1;
    ina.calibrateAuto(maxExpected_A, shunt_Ohms);

    pinMode(CONTROL_PIN, OUTPUT);
    digitalWrite(CONTROL_PIN, LOW);

    randomSeed(esp_random());

    WiFi.begin(ssid, password);

    while (WiFi.status() != WL_CONNECTED)
    {
        delay(500);
        Serial.print(".");
    }

    Serial.println("\nWiFi connected");

    webSocket.begin(host, port, "/");
    webSocket.onEvent(webSocketEvent);

    lastTime = millis();
}

void loop()
{
    webSocket.loop();

    if (!connect_status) return;

    if (ina.conversionReady())
    {
        vBus_V     = ina.readBusVoltage();
        vShunt_mV  = ina.readShuntVoltage();
        current_mA = ina.readCurrent();
        power_mW   = ina.readPower();
        ovf        = ina.overflow();
    }

    if (transferActive)
    {
        digitalWrite(CONTROL_PIN, HIGH);

        unsigned long now = millis();
        float dt_seconds = (now - lastTime) / 1000.0;
        lastTime = now;

        voltage = vBus_V;
        current = current_mA / 1000;
        float power_W = power_mW / 1000;

        totalEnergy_J += power_W * dt_seconds;

        Serial.print("Voltage: ");
        Serial.print(voltage, 3);

        Serial.print(" V  Current: ");
        Serial.print(current, 3);

        Serial.print(" A  Power: ");
        Serial.print(power_W, 3);

        Serial.print(" W  Energy: ");
        Serial.print(totalEnergy_J, 3);
        Serial.print(" / ");
        Serial.print(targetEnergy_J, 3);
        Serial.println(" J");

        if (totalEnergy_J >= targetEnergy_J)
        {
            digitalWrite(CONTROL_PIN, LOW);

            transferActive = false;

            Serial.println("Energy Sent");

            webSocket.sendTXT("RECEIVE_COMPLETE");
        }
    }

    delay(200);
}