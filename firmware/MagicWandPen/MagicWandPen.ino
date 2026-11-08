/*
  MagicWandPen.ino
  Streams motion data from an Arduino Nano 33 BLE Sense Rev2 (BMI270 accel/gyro
  + BMM150 magnetometer) over USB serial AND Bluetooth LE at the same time.

  Libraries (Arduino IDE > Library Manager):
    - Arduino_BMI270_BMM150
    - ArduinoBLE
  Board package: "Arduino Mbed OS Nano Boards" -> Arduino Nano 33 BLE

  "Pen down" inputs (either or both, see docs/FORCE_SENSOR.md):
    - Push button between D2 and GND (internal pull-up, no resistor needed).
    - Force sensor (FSR) on A0 as a voltage divider:
          3.3V ---[FSR]---+--- A0
                          |
                        [10k]
                          |
                         GND
      Squeeze the grip to write, relax to stop. Force is also streamed as an
      extra data channel. No FSR wired? Set USE_FORCE_SENSOR to 0 below (or send
      "p,0") so a floating A0 can't fake pen-down.

  ---------------------------------------------------------------------------
  USB serial output (115200 baud, one line per sample):
      ms,ax,ay,az,gx,gy,gz,mx,my,mz,btn,force
      ms      board time in milliseconds
      ax..az  acceleration in g
      gx..gz  angular rate in degrees/second
      mx..mz  magnetic field in microtesla (updates ~10-20 Hz, last value held)
      btn     1 while the pen is "down" (button held and/or grip squeezed,
              depending on the pen-down mode), else 0
      force   grip force, raw 12-bit ADC counts 0..4095 (0 = no force sensor)
  Lines starting with '#' are status messages.

  Commands (send over serial, or write to the BLE command characteristic):
      r,<hz>        set output rate: 100, 50, 25, 20 or 10 Hz (sensor runs at
                    100 Hz, lower rates average consecutive samples)
      p,<mode>      pen-down source: 0 = button only, 1 = force only,
                    2 = button OR force (default)
      f,<on>,<off>  force thresholds in ADC counts: pen goes down when force
                    rises above <on>, up when it falls below <off> (on > off)
      i             print identification line "# MagicWandPen ..."

  BLE: device name "MagicWandPen"
      service  6e400000-b5a3-f393-e0a9-e50e24dc4179
      data     6e400001-...  notify, 22 bytes per sample, little endian:
                 uint8 seq,
                 uint8 flags  bit0 = pen down (same as serial "btn")
                              bit1 = button held
                              bit2 = force above threshold
                 int16 ax,ay,az  (milli-g)
                 int16 gx,gy,gz  (0.1 deg/s)
                 int16 mx,my,mz  (0.1 uT)
                 uint16 force    (ADC counts)        <- bytes 20-21
               If the central didn't negotiate a larger MTU, the stack trims
               notifications to 20 bytes: everything except force still arrives.
      command  6e400002-...  write, ASCII command as above
  ---------------------------------------------------------------------------
*/

#include <Arduino_BMI270_BMM150.h>
#include <ArduinoBLE.h>

#define FW_VERSION        "1.1"
#define BUTTON_PIN        2      // D2 -> button -> GND
#define SENSOR_HZ         100    // BMI270 output data rate set by the library

#define USE_FORCE_SENSOR  1      // 0 if no FSR is wired to FORCE_PIN
#define FORCE_PIN         A0     // FSR divider midpoint
#define FORCE_ON_DEFAULT  700    // counts: squeeze above this = pen down
#define FORCE_OFF_DEFAULT 450    // counts: relax below this  = pen up
#define FORCE_SMOOTH      0.3f   // 0..1, low-pass weight of the newest reading

#define PACKET_LEN        22

// ---- BLE ----
BLEService penService("6e400000-b5a3-f393-e0a9-e50e24dc4179");
BLECharacteristic dataChar("6e400001-b5a3-f393-e0a9-e50e24dc4179", BLERead | BLENotify, PACKET_LEN, true);
BLECharacteristic cmdChar ("6e400002-b5a3-f393-e0a9-e50e24dc4179", BLEWrite | BLEWriteWithoutResponse, 20, false);

// ---- state ----
float ax, ay, az, gx, gy, gz;
float mx = 0, my = 0, mz = 0;
float sum[7] = {0};              // ax ay az gx gy gz force
int   nAccum = 0;
int   decim = 1;                 // SENSOR_HZ / output rate
uint8_t seq = 0;
bool  bleOk = false;
String serialLine;

int   penMode  = USE_FORCE_SENSOR ? 2 : 0;   // 0 button, 1 force, 2 either
int   forceOn  = FORCE_ON_DEFAULT;
int   forceOff = FORCE_OFF_DEFAULT;
float forceF   = 0;              // smoothed force, counts
bool  forceDown = false;         // force-trigger state with hysteresis
bool  btnDown   = false;
bool  penDown   = false;

void setRgb(bool r, bool g, bool b) {   // onboard RGB LED is active LOW
  digitalWrite(LEDR, r ? LOW : HIGH);
  digitalWrite(LEDG, g ? LOW : HIGH);
  digitalWrite(LEDB, b ? LOW : HIGH);
}

void printId() {
  if (!Serial) return;
  Serial.print("# MagicWandPen fw=");  Serial.print(FW_VERSION);
  Serial.print(" rate=");               Serial.print(SENSOR_HZ / decim);
  Serial.print(" ble=");                Serial.print(bleOk ? "on" : "off");
  Serial.print(" pen=");                Serial.print(penMode == 0 ? "button" : penMode == 1 ? "force" : "either");
  Serial.print(" force_on=");           Serial.print(forceOn);
  Serial.print(" force_off=");          Serial.println(forceOff);
  Serial.println("# ms,ax,ay,az,gx,gy,gz,mx,my,mz,btn,force");
}

void resetAccum() {
  nAccum = 0;
  for (int k = 0; k < 7; k++) sum[k] = 0;
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;
  if (cmd.startsWith("r,")) {
    int hz = cmd.substring(2).toInt();
    if (hz > 0 && hz <= SENSOR_HZ && (SENSOR_HZ % hz) == 0) {
      decim = SENSOR_HZ / hz;
      resetAccum();
    }
    printId();
  } else if (cmd.startsWith("p,")) {
    int m = cmd.substring(2).toInt();
    if (m >= 0 && m <= 2) penMode = m;
    printId();
  } else if (cmd.startsWith("f,")) {
    int comma = cmd.indexOf(',', 2);
    if (comma > 0) {
      int on  = cmd.substring(2, comma).toInt();
      int off = cmd.substring(comma + 1).toInt();
      if (on > off && off >= 0 && on <= 4095) { forceOn = on; forceOff = off; }
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
  analogReadResolution(12);         // 0..4095 over 0..3.3 V

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

uint8_t currentFlags() {
  return (penDown ? 1 : 0) | (btnDown ? 2 : 0) | (forceDown ? 4 : 0);
}

void emitSample() {
  float n = (float)nAccum;
  float a[3] = { sum[0] / n, sum[1] / n, sum[2] / n };
  float g[3] = { sum[3] / n, sum[4] / n, sum[5] / n };
  uint16_t force = (uint16_t)constrain(sum[6] / n + 0.5f, 0, 4095);
  resetAccum();

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
    Serial.print(penDown ? 1 : 0); Serial.print(',');
    Serial.println(force);
  }

  if (bleOk && BLE.connected() && dataChar.subscribed()) {
    uint8_t p[PACKET_LEN];
    p[0] = seq;
    p[1] = currentFlags();
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
    memcpy(p + 20, &force, 2);
    dataChar.writeValue(p, sizeof(p));
  }
  seq++;
}

void updatePenState() {
  btnDown = digitalRead(BUTTON_PIN) == LOW;

#if USE_FORCE_SENSOR
  int raw = analogRead(FORCE_PIN);
  forceF += FORCE_SMOOTH * ((float)raw - forceF);
  // hysteresis: a wobbly grip near the threshold won't chop a letter in two
  if (!forceDown && forceF > forceOn)  forceDown = true;
  if (forceDown  && forceF < forceOff) forceDown = false;
#endif

  switch (penMode) {
    case 0:  penDown = btnDown; break;
    case 1:  penDown = forceDown; break;
    default: penDown = btnDown || forceDown; break;
  }
  digitalWrite(LED_BUILTIN, penDown ? HIGH : LOW);   // orange LED = pen down
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
    updatePenState();
    sum[0] += ax; sum[1] += ay; sum[2] += az;
    sum[3] += gx; sum[4] += gy; sum[5] += gz;
    sum[6] += forceF;
    nAccum++;
    if (nAccum >= decim) emitSample();
  }
}
