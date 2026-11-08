# Adding a force sensor to the pen

This guide covers wiring a force sensor to the Arduino Nano 33 BLE Sense Rev2, where to put it in a handheld pen, power, and how the firmware uses it. The short version: an FSR (force-sensitive resistor) and one 10 kΩ resistor on pin A0 give you a squeeze-to-write grip. The pen streams the force value as an extra channel, and by default a squeeze counts as "pen down" exactly like holding the D2 button.

## 1. Which sensor

| Option | Parts | Good for | Downsides |
|---|---|---|---|
| **FSR (recommended)** e.g. Interlink FSR 400 (5 mm round), FSR 402 (13 mm round), FSR 406 (square) | FSR + 1 resistor | Pen-down trigger, rough grip force. Thin (~0.5 mm), cheap, 2 wires, almost no power | Not precise: ±10–25 % part to part, drifts under constant load. Fine for a trigger, not for weighing |
| Thin-film load cell / strain gauge + **HX711** amplifier | Sensor (4 wires) + HX711 board | Accurate, repeatable force, if you want force as a serious model feature | Bigger, more wiring, ~1.5–5 mA, and the HX711 tops out at 80 samples/s |
| Piezo disc | Disc + resistor | Detecting taps | Only senses *changes* in force, so it can't tell you "still squeezing" |
| Capacitive touch pad | Copper tape + resistor | Detecting a finger resting on the grip | Touch, not force. Any contact triggers it |

For an air-writing pen, the FSR is the right choice. You mainly need a reliable "I'm writing now" signal, and the FSR gives that with two wires and one resistor. The rest of this guide assumes an FSR, with the HX711 version in section 7.

## 2. Wiring (FSR)

An FSR is a resistor that drops from more than 1 MΩ (untouched) to a few hundred ohms (pressed hard). Put it in a voltage divider and read the middle point with an analog pin:

```
   Nano 3.3V ──────┐
                   │
                [ FSR ]          (either way round, it has no polarity)
                   │
   Nano A0  ───────┼───────┐
                   │       │
                [ 10 kΩ ] [0.1 µF]   (capacitor optional, smooths noise)
                   │       │
   Nano GND ───────┴───────┘
```

- **Use the 3.3V pin, never 5V.** The nRF52840 is a 3.3 V chip and its pins are damaged above about 3.6 V. (The Nano 33's "5V" pin isn't even connected by default.)
- Press harder → FSR resistance drops → A0 voltage rises. The firmware reads it at 12 bits, so 0 V = 0 and 3.3 V = 4095 counts.
- At rest the divider draws only microamps. Squeezed hard it draws at most 3.3 V / 10 kΩ ≈ 0.33 mA, so it doesn't affect battery life.
- The 10 kΩ resistor also acts as a pull-down. If the FSR comes unplugged, A0 reads 0 instead of floating around.

**Choosing the resistor.** It sets which force range uses most of the 0–3.3 V swing. Typical FSR 402 numbers (they vary a lot between parts):

| Force on the FSR | FSR resistance | A0 with 10 kΩ | A0 with 47 kΩ |
|---|---|---|---|
| none | > 1 MΩ | ~0.0 V (≈ 30 counts) | ~0.15 V |
| light touch, ~20 g | ~30 kΩ | 0.8 V (≈ 1000) | 2.0 V (≈ 2500) |
| firm finger, ~100 g | ~6 kΩ | 2.1 V (≈ 2550) | 2.9 V |
| hard squeeze, ~1 kg | ~1 kΩ | 3.0 V (≈ 3700) | 3.2 V |

- **10 kΩ** (default) suits a deliberate squeeze, which is what you want for a pen-down trigger: resting your finger doesn't trigger it, pressing does.
- **47 kΩ** makes it react to a light touch. Use it if a squeeze feels tiring, but then the reading saturates near 3.3 V with a firm grip.

**Connections to the FSR.** Don't solder directly onto the FSR's silver tabs, because they melt. Push them into a 2-pin female header, or use crimp connectors made for FSRs (e.g. Amphenol "Clincher"), then solder wires to those. Glue or tape the tail down so the connector doesn't flex the FSR at the joint, which is where they usually break.

**Quick test sketch** (paste into a new sketch, open Serial Plotter):

```cpp
void setup() { Serial.begin(115200); analogReadResolution(12); }
void loop()  { Serial.println(analogRead(A0)); delay(10); }
```

## 3. Where to put it in the pen

In air-writing there's no surface under the tip, so the force has to come from your grip:

```
   tip                                                     back
    ◄─────────────────────────────────────────────────────────►
    │  ●FSR  │        Nano 33 BLE Sense (fixed, rigid)         │ battery │
    │  under │                                                  │         │
    │  index │                                                  │         │
    │ finger │                                                  │         │
     2–4 cm from the tip
```

- **Under the index finger (or thumb) pad**, about 2–4 cm back from the tip, where your finger naturally sits when you hold a pen.
- **Rigid, flat backing.** An FSR only works when it's squeezed between two hard surfaces. Glue it to a flat spot on the shell, not over a gap or a curved, flexible wall.
- **Add a small "puck" on top.** A 5–8 mm dot of hot glue, a rubber bumper, or a 3D-printed button over the active area focuses your finger's force onto it. Without one, a soft fingertip spreads the force and readings get weak and inconsistent.
- **Don't bend the active area.** If the grip is round, use a small FSR (FSR 400, 5 mm) on a flattened section, or a flex sensor/strip FSR made to wrap.
- **Keep the Nano rigidly mounted and separate from the squeeze zone.** If squeezing flexes the board's mount, it shows up in the accelerometer and gyro too, and the model learns your squeeze instead of the letter.
- **Keep the button.** Mount the D2 button where your thumb can reach it. The firmware ORs the two, so either one starts a letter, and the button is handy for debugging.

## 4. Power and battery

The Nano 33 BLE Sense Rev2 runs everything (IMU, BLE, FSR) at 3.3 V from its onboard regulator.

- **Easiest:** a small USB power bank into the USB port. Note that some power banks switch off when the current is very low; if the pen turns off after a while, use one with an "always on" or low-current mode.
- **Built-in battery:** a 1-cell LiPo (3.7 V) is below the board's VIN range, so don't wire it straight to VIN. Use a small LiPo charger + 5 V boost module (e.g. Adafruit PowerBoost 500/1000 or an equivalent TP4056 + boost board) and connect its 5 V output to **VIN** and its ground to **GND**. Add a slide switch between the battery and the module. Check the VIN range for your board revision on the Arduino product page before you wire it.
- **Budget:** the board draws roughly 15–30 mA while streaming over BLE. A 500 mAh LiPo gives you many hours of writing. The FSR divider adds less than 0.3 mA even when squeezed.
- Put the battery at the back of the pen, so the weight balances in your hand and the IMU stays near your fingers.
- Never connect a battery to the 3.3V pin at the same time as USB.

## 5. How the firmware uses it

`firmware/MagicWandPen/MagicWandPen.ino` (firmware 1.1) reads A0 on every IMU sample (100 Hz), smooths it lightly, and:

1. **Streams it as an extra channel.** USB serial lines end in `,force` (raw counts 0–4095). BLE packets are now 22 bytes, with `uint16 force` in bytes 20–21.
2. **Uses it as pen-down.** Pen down starts when force rises above `force_on` (default 700 counts) and ends when it falls below `force_off` (default 450). The gap between the two (hysteresis) stops a wobbly grip from chopping a letter in half.
3. **Combines it with the button.** The existing `btn` value (serial column and BLE flags bit0) now means "pen down" and follows the pen-down mode:

| Command | Effect |
|---|---|
| `p,0` | button only (use this if no FSR is wired) |
| `p,1` | force sensor only |
| `p,2` | button OR force (default) |
| `f,<on>,<off>` | set thresholds in counts, e.g. `f,900,600` |
| `i` | print current settings |

BLE flags byte: bit0 = pen down, bit1 = button held, bit2 = force above threshold.

If you don't have an FSR wired at all, set `#define USE_FORCE_SENSOR 0` at the top of the sketch. Otherwise an unconnected A0 can float and fake pen-down presses.

Settings sent as commands reset when the pen powers off. Once you've found thresholds you like, change `FORCE_ON_DEFAULT` / `FORCE_OFF_DEFAULT` in the sketch.

**Compatibility.** The recorder reads both old (no force column) and new firmware. A BLE app that only reads the first 20 bytes still works unchanged, and if a phone doesn't negotiate a bigger BLE packet size, the pen simply sends the first 20 bytes and the force value is left off.

## 6. Tune the thresholds and record

```
cd recorder
python pen_recorder.py live
```

The live line now shows `pen=0 force= 25`. Note three numbers: force at rest, force when you hold the pen normally, and force when you squeeze to write. Pick `force_on` about halfway between "holding" and "squeezing", and `force_off` about two thirds of that. Then:

```
python pen_recorder.py record --writer nikolas --pendown force --force-on 900 --force-off 600
```

`--pendown either` (button or squeeze) and `--pendown button` work too, and all three options also apply to `live`. Leave them off to keep whatever the pen is set to.

Recording tips with a squeeze trigger:

- **Keep squeezing for the whole letter**, including the moves between strokes (the jump from the top bar of a "T" to its stem). Letting go ends the sample.
- Squeeze, then start moving. The recorder keeps 0.1 s from before pen-down, so a small delay is fine.
- If letters get cut in two, lower `force_off`. If the pen triggers while you're just holding it, raise `force_on`.

Each saved sample now has a `force` column, `plot` shows a grip-force panel, and `export` writes `export_full_100x10.csv` (the 9 motion channels plus force). Older samples get force = 0. The Kaggle-style 6-channel export is unchanged.

**Should the model use force?** Start without it. Train on the motion channels, and use force only to cut letters. Grip pressure varies a lot between people and between pens, so it can make a model fit one writer. Once you have plenty of data, you can try the 10-channel export and see if accuracy improves.

## 7. Alternative: thin-film load cell + HX711

Use this if you want accurate, repeatable force readings.

Wiring (HX711 module powered at 3.3 V, so its outputs are safe for the Nano):

| HX711 | Nano 33 BLE Sense |
|---|---|
| VCC | 3.3V |
| GND | GND |
| DT (DOUT) | D3 |
| SCK | D4 |
| RATE (if your board exposes it) | 3.3V for 80 samples/s (default 10/s is too slow) |

The load cell's four wires go to E+, E−, A+, A− on the HX711 (usually red, black, white, green; check your sensor's sheet).

Install the **HX711** library by Bogdan Necula (bogde) from the Library Manager, then make these changes to `MagicWandPen.ino`:

```cpp
#include <HX711.h>
HX711 scale;
long  forceZero = 0;
const float FORCE_SCALE = 0.01f;   // raw units -> counts; tune so a firm squeeze ≈ 3000

// in setup():
scale.begin(3, 4);                 // DT, SCK
delay(400);
forceZero = scale.read_average(10);  // tare: don't touch the pen while it boots

// in updatePenState(), replace the analogRead() line with:
static float raw = 0;
if (scale.is_ready()) raw = constrain((scale.read() - forceZero) * FORCE_SCALE, 0, 4095);
```

`is_ready()` keeps the loop from blocking. The HX711 updates at 80 Hz while the IMU runs at 100 Hz, so a value repeats now and then, which is fine. Everything downstream (thresholds, BLE, recorder) works the same, because the reading is mapped to the same 0–4095 range.

## Parts list (FSR version)

- 1 × FSR (Interlink FSR 400 or 402)
- 1 × 10 kΩ resistor (47 kΩ for a lighter touch)
- 1 × 0.1 µF ceramic capacitor (optional)
- 2-pin female header or FSR crimp connectors, thin wire
- Something for the puck: hot glue, a rubber bumper, or a printed nub
