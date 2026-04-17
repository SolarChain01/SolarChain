#include <Wire.h>
#include <7semi_MAX17048.h>

#define SDA_PIN 21
#define SCL_PIN 22
#define LOAD_PIN 5        // MOSFET / relay control

#define BATTERY_ENERGY_J 26640.0   // 3.7V 2000mAh battery

MAX17048_7semi battery;

bool sensorReady = false;
bool draining = false;

float startSOC = 0;
float targetDrop = 0;

void setup() {

  Serial.begin(115200);
  Wire.begin(SDA_PIN, SCL_PIN);

  pinMode(LOAD_PIN, OUTPUT);
  digitalWrite(LOAD_PIN, LOW);

}

void loop() {

  if (!sensorReady) {
    if (battery.begin(&Wire)) {
      Serial.println("MAX17048 initialized");
      battery.quickStart();
      battery.setVoltageLimits(3.2, 4.2);
      sensorReady = true;
    } else {
      Serial.println("MAX17048 not detected...");
      delay(1000);
      return;
    }
  }

    Serial.print("Voltage: ");
    Serial.print(voltage);
    Serial.print(" V | SOC: ");
    Serial.print(soc);

  float soc = battery.cellPercent();
  float voltage = battery.cellVoltage();

  // Read Joule input
  if (Serial.available() && !draining) {

    Serial.println("Enter required energy to drain (J):");
    float joules = Serial.parseFloat();

    targetDrop = (joules / BATTERY_ENERGY_J) * 100.0;

    startSOC = soc;

    Serial.print("Target SOC drop: ");
    Serial.print(targetDrop);
    Serial.println(" %");

    digitalWrite(LOAD_PIN, HIGH);   // turn ON load
    draining = true;

    Serial.println("Load ON");
  }

  if (draining) {

    float drop = startSOC - soc;

    Serial.print("Voltage: ");
    Serial.print(voltage);
    Serial.print(" V | SOC: ");
    Serial.print(soc);
    Serial.print(" % | Drop: ");
    Serial.println(drop);

    if (drop >= targetDrop) {

      digitalWrite(LOAD_PIN, LOW);   // turn OFF load
      draining = false;

      Serial.println("Target energy drained. Load OFF.");
    }
  }

  delay(1000);
}