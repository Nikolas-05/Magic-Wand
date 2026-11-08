# Collecting pen motion data

This is how to record labeled air-writing samples (A–Z) with the Arduino Nano 33 BLE Sense Rev2 so you can train a letter recognizer.

## What the board can and can't measure

The Nano's IMU doesn't measure position. It gives you three things:

| Sensor | Measures | Units in our files |
|---|---|---|
| BMI270 accelerometer | acceleration, including gravity | g |
| BMI270 gyroscope | rotation speed | degrees/second |
| BMM150 magnetometer | Earth's magnetic field (a compass) | microtesla |

You *can* compute position by integrating acceleration twice, but small sensor errors grow with the square of time. After one second the pen tip is already off by tens of centimetres, so it's useless for drawing.

That's fine, because recognizers don't need position. Two approaches work well:

1. **Raw motion windows (recommended to start).** Record the 6 accel+gyro channels while a letter is written, resample to a fixed length (100 steps), and train a small 1D-CNN on them. That's the format of the Kaggle A–Z dataset, and `export` writes it for you.
2. **Pen-pointing path.** Integrate the gyro (with the accelerometer correcting tilt) to track which way the pen points. Over a 1–3 s letter this traces the letter shape quite well, as if the pen were a laser pointer drawing on a wall. `plot` shows you this path, and `export` saves it as stroke JSON for raster/stroke models like TensorFlow's magic_wand.

## 1. Hardware

- Arduino Nano 33 BLE Sense **Rev2** (the one with BMI270 + BMM150).
- Optional, but strongly recommended: a momentary push button between **D2** and **GND**. Hold it while writing a letter. This "pen down" signal is by far the most reliable way to cut recordings into letters, and the public datasets use one too. No resistor is needed (the sketch uses the internal pull-up).
- Optional: a force sensor (FSR) in the grip on **A0**, so squeezing the pen works as pen-down too. See [FORCE_SENSOR.md](FORCE_SENSOR.md) for wiring and placement. With no FSR wired, set `USE_FORCE_SENSOR` to 0 in the sketch.
- Mount the board firmly on the pen, with its long edge along the pen. Keep the same mounting for every recording session, because the model learns the axes.
- For wireless use: a small LiPo or a USB power bank.

LEDs: **green** means ready and advertising over BLE, **blue** means a BLE client is connected, **orange** lights while the pen is down (button held or grip squeezed), and a **fast red blink** means the IMU wasn't found.

## 2. Flash the firmware

1. Arduino IDE → Boards Manager → install **Arduino Mbed OS Nano Boards**.
2. Library Manager → install **Arduino_BMI270_BMM150** and **ArduinoBLE**.
3. Open `firmware/MagicWandPen/MagicWandPen.ino`, select *Arduino Nano 33 BLE*, and upload.
4. Optional check: open the Serial Monitor at 115200. You should see lines like `1234,0.0123,-0.0040,1.0011,0.31,-0.12,0.05,21.3,-4.0,-38.2,0,25`. **Close the Serial Monitor before running the recorder**, because only one program can hold the port.

## 3. Set up Python (once)

```
cd recorder
pip install -r requirements.txt
```

## 4. Check the connection

```
python pen_recorder.py ports       # the pen is marked "<-- pen (Arduino)"
python pen_recorder.py live        # live values; flat and still -> |a| ≈ 1.00 g, gyro ≈ 0
python pen_recorder.py live --ble  # same, over Bluetooth (unplug USB, power from battery)
```

The port is auto-detected, so you normally don't need `--port COM5`.

## 5. Record letters

```
python pen_recorder.py record --writer nikolas --reps 10
```

The recorder asks for letters in random order (`[3/260] Write: K`). For each one, hold the button, write the letter in the air, and release. It saves the sample and moves on.

- `r` deletes the last sample so you can redo it, `s` skips a letter, and `q` quits.
- Sessions resume: running the same command again only records what's still missing. Raise `--reps` to collect more.
- `--letters AEIOU` records a subset. `--ble` records wirelessly.
- Using the force sensor? Add `--pendown force` (or `either`) and your thresholds, e.g. `--force-on 900 --force-off 600`. See [FORCE_SENSOR.md](FORCE_SENSOR.md#6-tune-the-thresholds-and-record).
- No button? Use `--trigger key` (SPACE to start, SPACE to stop) or `--trigger motion` (it starts when you move and stops after you hold still for 0.4 s).
- `--rate 50` records at 50 Hz to match the Kaggle and IIT datasets. The default of 100 Hz keeps more detail, and `export` resamples anyway.

Tips for good data:

- Write each letter the same basic way (same stroke order), roughly 10–20 cm tall, in about 1–2 seconds.
- Aim for 20–40 reps per letter, spread over a few sessions. Get 3 or more people to record if you can (use a different `--writer` for each), so the model works for more than one hand.
- Hold the pen the same way each time. Rotating it in your hand changes every axis.
- On BLE, watch the `dropped` count. If it climbs, stay closer to the PC or use `--rate 50`.

### Where samples go

```
data/
  index.csv                         one row per sample: path,label,writer,n_samples,duration_s
  raw/<writer>/<LETTER>/<LETTER>_<time>.csv
```

Each raw CSV has `t_s, ax_g, ay_g, az_g, gx_dps, gy_dps, gz_dps, mx_uT, my_uT, mz_uT, btn, force`, starting 0.1 s before pen-down. `btn` is the pen-down flag and `force` is grip force in ADC counts (0 without a sensor).

## 6. Look at a sample

```
python pen_recorder.py plot data/raw/nikolas/A/A_20261108-....csv
```

This shows the accelerometer, the gyro, and the reconstructed pen-pointing path. If the letter comes out mirrored or upside down, try `--flip-x` / `--flip-y`. If it looks scrambled, the pen's long axis isn't the board's X axis: try `--pen-axis y` (or `-x`, `-y`, …) and use the same option with `export`.

## 7. Export for training

```
python pen_recorder.py export
```

| File | Contents | Use it with |
|---|---|---|
| `export_kaggle_100x6.csv` | `label`, then 100 steps × `ax ay az gx gy gz` interleaved (`ax_0, ay_0, …, gz_99`), in **m/s² and rad/s**, plus `writer`, `source_file` | Same layout and units as the Kaggle "Air-Writing Gestures A–Z" CSV, so you can stack the two. Drop the last two columns first. |
| `export_full_100x10.csv` | Same, but 10 channels: motion, magnetometer and grip force, in g, °/s, µT, ADC counts | Your own models |
| `export_strokes.json` | 2D pen path per sample (`strokePoints: [{x, y}]`, in degrees) | Stroke-raster models (magic_wand / virtual-notepad style) |

When you mix datasets, remember that the axes are oriented differently on every board (the Kaggle set used an MPU-6050 on a glove). Fine-tune on your own pen's data at the end, because that usually matters more than the total amount of data.

## Wireless protocol (for the partner app)

Name `MagicWandPen`, service `6e400000-b5a3-f393-e0a9-e50e24dc4179`.

- `…0001` (notify): 22 bytes per sample, little endian: `uint8 seq, uint8 flags (bit0 = pen down, bit1 = button, bit2 = force pressed), int16 ax ay az (mg), int16 gx gy gz (0.1 °/s), int16 mx my mz (0.1 µT), uint16 force (ADC counts)`. If the BLE packet size isn't raised, only the first 20 bytes arrive (no force).
- `…0002` (write): ASCII commands. `r,50` sets the rate (100/50/25/20/10 Hz), and `p,0|1|2` picks the pen-down source (button / force / either), `f,<on>,<off>` sets force thresholds, and `i` makes the pen print its ID and settings over USB.

USB serial uses the same commands at 115200 baud and streams the CSV line format shown above.
