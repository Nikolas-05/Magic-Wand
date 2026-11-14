/*
  Nano 33 BLE Sense Rev2: stream all 9 IMU axes over USB Serial and BLE.
  Same device name and UUIDs as imu_ble_stream.ino, so Initial_setup.py finds it.

  Libraries (Library Manager):
    - Arduino_BMI270_BMM150
    - ArduinoBLE

  Board: Tools > Board > Arduino Nano 33 BLE
  Each BLE notification is a 40-byte packet (little-endian):
    uint32 t_ms, float ax, ay, az (g), gx, gy, gz (deg/s), mx, my, mz (uT)
  The magnetometer updates slower (~20 Hz) than accel/gyro (~100 Hz); its last value is repeated.
*/

#include <ArduinoBLE.h>
#include <Arduino_BMI270_BMM150.h>

const char* DEVICE_NAME  = "Nano33-IMU";
const char* SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214";
const char* CHAR_UUID    = "19b10001-e8f2-537e-4f6c-d104768a1214";

struct __attribute__((packed)) Sample {
  uint32_t t_ms;
  float ax, ay, az;
  float gx, gy, gz;
  float mx, my, mz;
};

BLEService imuService(SERVICE_UUID);
BLECharacteristic imuChar(CHAR_UUID, BLERead | BLENotify, sizeof(Sample), true);

float gx = 0, gy = 0, gz = 0;   // latest gyro reading
float mx = 0, my = 0, mz = 0;   // latest magnetometer reading

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
  imuService.addCharacteristic(imuChar);
  BLE.addService(imuService);

  BLE.setEventHandler(BLEConnected, onConnected);
  BLE.setEventHandler(BLEDisconnected, onDisconnected);
  BLE.setConnectionInterval(6, 12);     // 7.5-15 ms (units of 1.25 ms); the central has the final say
  BLE.advertise();

  Serial.print("# Accel rate = ");  Serial.print(IMU.accelerationSampleRate());
  Serial.print(" Hz, gyro rate = "); Serial.print(IMU.gyroscopeSampleRate());
  Serial.print(" Hz, mag rate = ");  Serial.print(IMU.magneticFieldSampleRate());
  Serial.println(" Hz");
  Serial.println("t_ms,ax,ay,az,gx,gy,gz,mx,my,mz");
}

void loop() {
  BLE.poll();

  if (IMU.gyroscopeAvailable()) {
    IMU.readGyroscope(gx, gy, gz);
  }
  if (IMU.magneticFieldAvailable()) {
    IMU.readMagneticField(mx, my, mz);
  }

  if (IMU.accelerationAvailable()) {
    float x, y, z;
    IMU.readAcceleration(x, y, z);

    Sample s = { millis(), x, y, z, gx, gy, gz, mx, my, mz };

    // USB serial (CSV)
    Serial.print(s.t_ms);  Serial.print(',');
    Serial.print(s.ax, 4); Serial.print(',');
    Serial.print(s.ay, 4); Serial.print(',');
    Serial.print(s.az, 4); Serial.print(',');
    Serial.print(s.gx, 2); Serial.print(',');
    Serial.print(s.gy, 2); Serial.print(',');
    Serial.print(s.gz, 2); Serial.print(',');
    Serial.print(s.mx, 1); Serial.print(',');
    Serial.print(s.my, 1); Serial.print(',');
    Serial.println(s.mz, 1);

    // Bluetooth (only if a device is connected)
    if (BLE.connected()) {
      imuChar.writeValue((uint8_t*)&s, sizeof(s));
    }
  }
}
