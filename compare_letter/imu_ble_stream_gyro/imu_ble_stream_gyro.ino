/*
  Nano 33 BLE Rev2: stream accelerometer AND gyroscope over USB Serial and BLE.

  Same as imu_ble_stream.ino (same name "Nano33-IMU", same accel characteristic,
  so ArduinoDAQ.py keeps working), plus a second characteristic with gyro:

    19b10001-...  16 bytes: uint32 t_ms, float ax, ay, az            (g)      <- unchanged
    19b10002-...  16 bytes: uint32 t_ms, int16 ax, ay, az (milli-g),
                                         int16 gx, gy, gz (0.1 deg/s)        <- new

  The new packet is also 16 bytes, so it fits a default BLE packet with no
  MTU negotiation. compare_letter.py uses 19b10002 automatically when present.

  Libraries (Library Manager): Arduino_BMI270_BMM150, ArduinoBLE
  Board: Tools > Board > Arduino Nano 33 BLE
*/

#include <ArduinoBLE.h>
#include <Arduino_BMI270_BMM150.h>

const char* DEVICE_NAME  = "Nano33-IMU";
const char* SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214";
const char* ACCEL_UUID   = "19b10001-e8f2-537e-4f6c-d104768a1214";
const char* IMU6_UUID    = "19b10002-e8f2-537e-4f6c-d104768a1214";

struct __attribute__((packed)) AccelSample {
  uint32_t t_ms;
  float ax, ay, az;
};

struct __attribute__((packed)) Imu6Sample {
  uint32_t t_ms;
  int16_t ax, ay, az;   // milli-g
  int16_t gx, gy, gz;   // 0.1 deg/s
};

BLEService imuService(SERVICE_UUID);
BLECharacteristic accelChar(ACCEL_UUID, BLERead | BLENotify, sizeof(AccelSample), true);
BLECharacteristic imu6Char(IMU6_UUID, BLERead | BLENotify, sizeof(Imu6Sample), true);

float gx = 0, gy = 0, gz = 0;   // latest gyro reading, deg/s

int16_t clamp16(float v) {
  if (v > 32767) return 32767;
  if (v < -32767) return -32767;
  return (int16_t)lroundf(v);
}

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000);

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
  imuService.addCharacteristic(imu6Char);
  BLE.addService(imuService);
  BLE.setConnectionInterval(6, 12);     // 7.5-15 ms
  BLE.advertise();

  Serial.print("# Accel rate = "); Serial.print(IMU.accelerationSampleRate());
  Serial.print(" Hz, gyro rate = "); Serial.print(IMU.gyroscopeSampleRate()); Serial.println(" Hz");
  Serial.println("t_ms,ax,ay,az,gx,gy,gz");
}

void loop() {
  BLE.poll();

  if (IMU.gyroscopeAvailable()) {
    IMU.readGyroscope(gx, gy, gz);
  }

  if (IMU.accelerationAvailable()) {
    float x, y, z;
    IMU.readAcceleration(x, y, z);
    uint32_t t = millis();

    Serial.print(t);      Serial.print(',');
    Serial.print(x, 4);   Serial.print(',');
    Serial.print(y, 4);   Serial.print(',');
    Serial.print(z, 4);   Serial.print(',');
    Serial.print(gx, 2);  Serial.print(',');
    Serial.print(gy, 2);  Serial.print(',');
    Serial.println(gz, 2);

    if (BLE.connected()) {
      AccelSample a = { t, x, y, z };
      accelChar.writeValue((uint8_t*)&a, sizeof(a));
      Imu6Sample s = { t, clamp16(x * 1000), clamp16(y * 1000), clamp16(z * 1000),
                       clamp16(gx * 10), clamp16(gy * 10), clamp16(gz * 10) };
      imu6Char.writeValue((uint8_t*)&s, sizeof(s));
    }
  }
}
