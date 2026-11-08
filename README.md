# Magic-Wand

Air-writing pen built on the Arduino Nano 33 BLE Sense Rev2 (BMI270 + BMM150): write uppercase letters in the air and have them recognized and sent to another device.

## Contents

| Path | What it is |
|---|---|
| `firmware/MagicWandPen/` | Arduino sketch that streams accel/gyro/mag, grip force and a pen-down flag over USB and Bluetooth LE |
| `recorder/pen_recorder.py` | PC tool that records labeled letter samples, plots them, and exports training CSVs |
| `docs/COLLECTING_DATA.md` | Step-by-step guide to collecting training data |
| `docs/FORCE_SENSOR.md` | Wiring a force sensor (FSR) into the pen grip as a squeeze-to-write trigger |
| `ArduinoDAQ.py` | Original generic serial data-acquisition class |

Quick start: flash the sketch, then

```
cd recorder
pip install -r requirements.txt
python pen_recorder.py live
python pen_recorder.py record --writer yourname --reps 10
python pen_recorder.py export
```
