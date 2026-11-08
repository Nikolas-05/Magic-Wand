/*
  Nano 33 BLE Rev2: stream accelerometer data over USB Serial and BLE.

  Libraries (Library Manager):
    - Arduino_BMI270_BMM150
    - ArduinoBLE

  Board: Tools > Board > Arduino Nano 33 BLE
  Each BLE notification is a 16-byte packet: uint32 t_ms, float ax, ay, az (little-endian).
  Acceleration is in g.
*/

#include <ArduinoBLE.h>
#include <Arduino_BMI270_BMM150.h>

const char* DEVICE_NAME  = "Nano33-IMU";
const char* SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214";
const char* CHAR_UUID    = "19b10001-e8f2-537e-4f6c-d104768a1214";

struct __attribute__((packed)) Sample {
  uint32_t t_ms;
  float ax, ay, az;
};

BLEService imuService(SERVICE_UUID);
BLECharacteristic accelChar(CHAR_UUID, BLERead | BLENotify, sizeof(Sample), true);

void onConnected(BLEDevice central) {
  Serial.print("# BLE connected: ");
  Serial.println(central.address());
}

void onDisconnected(BLEDevice central) {
  Serial.println("# BLE disconnected, advertising again");
}

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000);   // don't hang forever if no USB monitor

  if (!IMU.begin()) {
    Serial.println("Failed to initialize IMU!");
    while (1);
  }
  if (!BLE.begin()) {
    Serial.println("Failed to start BLE!");
    while (1);
  }

  BLE.setLocalName(DEVICE_NAME);
  BLE.setDeviceName(DEVICE_NAME);
  BLE.setAdvertisedService(imuService);
  imuService.addCharacteristic(accelChar);
  BLE.addService(imuService);

  BLE.setEventHandler(BLEConnected, onConnected);
  BLE.setEventHandler(BLEDisconnected, onDisconnected);
  BLE.setConnectionInterval(6, 12);     // 7.5-15 ms (units of 1.25 ms); the central has the final say
  BLE.advertise();

  Serial.print("# Accel sample rate = ");
  Serial.print(IMU.accelerationSampleRate());
  Serial.println(" Hz");
  Serial.println("t_ms,ax,ay,az");
}

void loop() {
  BLE.poll();

  if (IMU.accelerationAvailable()) {
    float x, y, z;
    IMU.readAcceleration(x, y, z);

    Sample s;
    s.t_ms = millis();
    s.ax = x;
    s.ay = y;
    s.az = z;

    // USB serial (CSV)
    Serial.print(s.t_ms);  Serial.print(',');
    Serial.print(s.ax, 4); Serial.print(',');
    Serial.print(s.ay, 4); Serial.print(',');
    Serial.println(s.az, 4);

    // Bluetooth (only if a device is connected)
    if (BLE.connected()) {
      accelChar.writeValue((uint8_t*)&s, sizeof(s));
    }
  }
}
