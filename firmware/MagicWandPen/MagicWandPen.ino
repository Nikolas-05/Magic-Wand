/*
  MagicWandPen.ino
  Streams motion data from an Arduino Nano 33 BLE Sense Rev2 (BMI270 accel/gyro
  + BMM150 magnetometer) over USB serial AND Bluetooth LE at the same time.

  Libraries (Arduino IDE > Library Manager):
    - Arduino_BMI270_BMM150
    - ArduinoBLE
  Board package: "Arduino Mbed OS Nano Boards" -> Arduino Nano 33 BLE

  Optional "pen down" button: momentary push button between pin D2 and GND.
  Hold it while you write a letter, release when done. Without a button the
  flag is always 0 and the PC recorder can use keyboard or motion triggering.

  ---------------------------------------------------------------------------
  USB serial output (115200 baud, one line per sample):
      ms,ax,ay,az,gx,gy,gz,mx,my,mz,btn
      ms      board time in milliseconds
      ax..az  acceleration in g
      gx..gz  angular rate in degrees/second
      mx..mz  magnetic field in microtesla (updates ~10-20 Hz, last value held)
      btn     1 while the pen button is held, else 0
  Lines starting with '#' are status messages.

  Commands (send over serial, or write to the BLE command characteristic):
      r,<hz>   set output rate: 100, 50, 25, 20 or 10 Hz (sensor runs at 100 Hz,
               lower rates average consecutive samples)
      i        print identification line "# MagicWandPen ..."

  BLE: device name "MagicWandPen"
      service  6e400000-b5a3-f393-e0a9-e50e24dc4179
      data     6e400001-...  notify, 20 bytes per sample, little endian:
                 uint8 seq, uint8 flags(bit0 = button),
                 int16 ax,ay,az  (milli-g)
                 int16 gx,gy,gz  (0.1 deg/s)
                 int16 mx,my,mz  (0.1 uT)
      command  6e400002-...  write, ASCII command as above
  ---------------------------------------------------------------------------
*/

#include <Arduino_BMI270_BMM150.h>
#include <ArduinoBLE.h>

#define FW_VERSION   "1.0"
#define BUTTON_PIN   2           // D2 -> button -> GND
#define SENSOR_HZ    100         // BMI270 output data rate set by the library

// ---- BLE ----
BLEService penService("6e400000-b5a3-f393-e0a9-e50e24dc4179");
BLECharacteristic dataChar("6e400001-b5a3-f393-e0a9-e50e24dc4179", BLERead | BLENotify, 20, true);
BLECharacteristic cmdChar ("6e400002-b5a3-f393-e0a9-e50e24dc4179", BLEWrite | BLEWriteWithoutResponse, 20, false);

// ---- state ----
float ax, ay, az, gx, gy, gz;
float mx = 0, my = 0, mz = 0;
float sum[6] = {0};
int   nAccum = 0;
int   decim = 1;                 // SENSOR_HZ / output rate
uint8_t seq = 0;
bool  bleOk = false;
String serialLine;

void setRgb(bool r, bool g, bool b) {   // onboard RGB LED is active LOW
  digitalWrite(LEDR, r ? LOW : HIGH);
  digitalWrite(LEDG, g ? LOW : HIGH);
  digitalWrite(LEDB, b ? LOW : HIGH);
}

void printId() {
  if (!Serial) return;
  Serial.print("# MagicWandPen fw=");  Serial.print(FW_VERSION);
  Serial.print(" rate=");               Serial.print(SENSOR_HZ / decim);
  Serial.print(" ble=");                Serial.println(bleOk ? "on" : "off");
  Serial.println("# ms,ax,ay,az,gx,gy,gz,mx,my,mz,btn");
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;
  if (cmd.startsWith("r,")) {
    int hz = cmd.substring(2).toInt();
    if (hz > 0 && hz <= SENSOR_HZ && (SENSOR_HZ % hz) == 0) {
      decim = SENSOR_HZ / hz;
      nAccum = 0;
      for (int k = 0; k < 6; k++) sum[k] = 0;
    }
    printId();
  } else if (cmd == "i") {
    printId();
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(LEDR, OUTPUT); pinMode(LEDG, OUTPUT); pinMode(LEDB, OUTPUT);
  setRgb(false, false, false);

  // Wait up to 2 s for a USB host so the first status lines aren't lost,
  // but keep going on battery power.
  unsigned long t0 = millis();
  while (!Serial && millis() - t0 < 2000) {}

  if (!IMU.begin()) {
    while (true) {                  // fast red blink = IMU not found
      setRgb(true, false, false); delay(100);
      setRgb(false, false, false); delay(100);
      if (Serial) Serial.println("# ERROR: IMU.begin() failed");
    }
  }

  if (BLE.begin()) {
    BLE.setLocalName("MagicWandPen");
    BLE.setDeviceName("MagicWandPen");
    BLE.setAdvertisedService(penService);
    penService.addCharacteristic(dataChar);
    penService.addCharacteristic(cmdChar);
    BLE.addService(penService);
    // ask for a short connection interval (7.5-15 ms) so 100 Hz notifications fit
    BLE.setConnectionInterval(6, 12);
    BLE.advertise();
    bleOk = true;
  }
  setRgb(false, true, false);       // green = ready, advertising
  printId();
}

void emitSample(bool btn) {
  float n = (float)nAccum;
  float a[3] = { sum[0] / n, sum[1] / n, sum[2] / n };
  float g[3] = { sum[3] / n, sum[4] / n, sum[5] / n };
  nAccum = 0;
  for (int k = 0; k < 6; k++) sum[k] = 0;

  if (Serial) {
    // Serial.print(float, digits) avoids relying on printf float support
    Serial.print(millis());  Serial.print(',');
    Serial.print(a[0], 4);   Serial.print(',');
    Serial.print(a[1], 4);   Serial.print(',');
    Serial.print(a[2], 4);   Serial.print(',');
    Serial.print(g[0], 2);   Serial.print(',');
    Serial.print(g[1], 2);   Serial.print(',');
    Serial.print(g[2], 2);   Serial.print(',');
    Serial.print(mx, 1);     Serial.print(',');
    Serial.print(my, 1);     Serial.print(',');
    Serial.print(mz, 1);     Serial.print(',');
    Serial.println(btn ? 1 : 0);
  }

  if (bleOk && BLE.connected() && dataChar.subscribed()) {
    uint8_t p[20];
    p[0] = seq;
    p[1] = btn ? 1 : 0;
    int16_t v[9] = {
      (int16_t)constrain(a[0] * 1000.0f, -32767, 32767),
      (int16_t)constrain(a[1] * 1000.0f, -32767, 32767),
      (int16_t)constrain(a[2] * 1000.0f, -32767, 32767),
      (int16_t)constrain(g[0] * 10.0f,   -32767, 32767),
      (int16_t)constrain(g[1] * 10.0f,   -32767, 32767),
      (int16_t)constrain(g[2] * 10.0f,   -32767, 32767),
      (int16_t)constrain(mx * 10.0f,     -32767, 32767),
      (int16_t)constrain(my * 10.0f,     -32767, 32767),
      (int16_t)constrain(mz * 10.0f,     -32767, 32767)
    };
    memcpy(p + 2, v, sizeof(v));    // nRF52840 is little endian
    dataChar.writeValue(p, sizeof(p));
  }
  seq++;
}

void loop() {
  // ---- BLE housekeeping + commands ----
  if (bleOk) {
    BLE.poll();
    static bool wasConnected = false;
    bool c = BLE.connected();
    if (c != wasConnected) { setRgb(false, !c, c); wasConnected = c; }  // blue = BLE connected
    if (cmdChar.written()) {
      char buf[21] = {0};
      int len = cmdChar.valueLength();
      memcpy(buf, cmdChar.value(), min(len, 20));
      handleCommand(String(buf));
    }
  }
  while (Serial && Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n') { handleCommand(serialLine); serialLine = ""; }
    else if (serialLine.length() < 32) serialLine += ch;
  }

  // ---- sensors ----
  if (IMU.magneticFieldAvailable()) IMU.readMagneticField(mx, my, mz);

  if (IMU.accelerationAvailable()) {
    IMU.readAcceleration(ax, ay, az);
    IMU.readGyroscope(gx, gy, gz);
    sum[0] += ax; sum[1] += ay; sum[2] += az;
    sum[3] += gx; sum[4] += gy; sum[5] += gz;
    nAccum++;

    bool btn = digitalRead(BUTTON_PIN) == LOW;
    digitalWrite(LED_BUILTIN, btn ? HIGH : LOW);   // orange LED = pen down
    if (nAccum >= decim) emitSample(btn);
  }
}
