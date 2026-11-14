# Compare your air-drawn letter to open data

`compare_letter.py` records one letter (default **A**) from your Nano 33 BLE over Bluetooth and compares it with open-source air-writing recordings. You get a printed report and a plot.

It talks to the same board as your `ArduinoDAQ.py` (it advertises as `Nano33-IMU`), so you don't need to change anything on the Arduino to start.

## Run it on Windows

Open **Anaconda Prompt** (or Command Prompt) and type:

```
cd "C:\Users\ramir\OneDrive\Documents\GitHub\Magic-Wand\compare_letter"
pip install -r requirements.txt
python compare_letter.py download
python compare_letter.py
```

1. `download` fetches the Kaggle A–Z dataset (about 37 MB) into `reference_data\kaggle\`. You only do this once. If Kaggle refuses, the script prints three steps: open the dataset page, click **Download**, and drop the `.zip` (or the `.csv` inside it) into `reference_data\kaggle\`.
2. `python compare_letter.py` connects to the board, then:
   - Hold the board the way you'll hold the pen, and keep it still.
   - Press **ENTER**, draw a big **A** in the air (about 1–2 seconds), hold still, and press **ENTER** again.
   - It saves the recording in `my_letters\` and shows the comparison. The plot is also saved next to it as `..._compare.png`.

Before running it, close ArduinoDAQ.py, the Serial Monitor, and any phone BLE app. The board accepts only one Bluetooth connection at a time.

Other commands:

```
python compare_letter.py record A                 # only record
python compare_letter.py compare                  # compare your newest recording again
python compare_letter.py compare --file my_letters\A_20261108-101500.csv
python compare_letter.py compare --file ..\imu_log.csv   # a log from ArduinoDAQ.py works too
python compare_letter.py B                        # draw and check a different letter
```

**Using Spyder?** Run it from the IPython console with `%run compare_letter.py` or `%run compare_letter.py compare`. The Bluetooth part runs in its own thread, so you don't need `nest_asyncio`.

## What the comparison does

| Step | Why |
|---|---|
| Trim the still parts before and after the letter | Only the drawing motion is compared |
| Convert units: your g → m/s², °/s → rad/s | The Kaggle data uses m/s² and rad/s (the script detects this and prints it) |
| Resample to 100 steps | The Kaggle samples are all 100 steps (50 Hz × 2 s). This also removes differences in writing speed |
| Remove each channel's mean, then scale to RMS = 1 | Removes gravity and sensor offset, and makes big and small letters comparable |
| Try all 24 axis mappings | The dataset used a glove-mounted MPU-6050, so its x/y/z don't point the same way as your board's. Each letter gets its own best mapping, so the letter ranking stays fair |
| DTW (dynamic time warping) distance | Lines up the parts of the stroke that were drawn faster or slower before measuring the difference |

The report shows:

- **DTW distance to the average A**, and what share of the dataset's own A samples are farther from that average than yours are. 50% or more means your A is a very typical A.
- **Nearest letters:** your movement against the average of all 26 letters. "A ranks #1" means it looks most like an A.
- **5-nearest-sample vote:** the 5 single recordings closest to yours, and which letters they are.
- **The axis mapping it used**, e.g. `--axes=-y,x,z`. Once you have a few good A's, pass that value with `--axes=...` (keep the `=`) to lock it in so the mapping isn't re-guessed each time.

The plot shows your A (red) over the open-data A's (blue) in three versions: in real units, normalized, and after DTW alignment. Below them is a bar chart of the distance to every letter.

## Accel only vs accel + gyro

Your current sketch (`imu_ble_stream.ino`) sends **acceleration only**, so the script compares the 3 accel channels with the dataset's accel channels. That works, but acceleration alone is noisy for handwriting. Most of the letter's shape is in how the pen **rotates**.

To add gyro, upload **`imu_ble_stream_gyro/imu_ble_stream_gyro.ino`** (same libraries, same board). It keeps everything the old sketch had, so `ArduinoDAQ.py` still works, and it adds a second Bluetooth characteristic carrying accel + gyro. `compare_letter.py` detects it automatically and then:

- compares all 6 channels with the Kaggle data, and
- turns the gyro into a **pen-pointing path** (where the pen points, like a laser pointer on a wall) and compares that 2D shape with the **virtual-notepad** strokes (Nano 33 BLE, A–Z, MIT license). That data is already included in `reference_data\`. The plot then shows your drawn A on top of theirs.

## Notes and limits

- None of the open datasets used your exact sensor (BMI270) or mounting. The comparison is good for checking "does my A look like an A?", not for exact numbers. For a real recognizer, record your own letters with `recorder/pen_recorder.py` (see `docs/COLLECTING_DATA.md`).
- The Kaggle file includes augmented copies (jitter, scaling, time-warp, rotation) next to the original recordings. That's fine for this comparison.
- I tested the script end to end on synthetic data built from the virtual-notepad strokes, because the Kaggle file can't be downloaded from where I work. The Kaggle column order and units are detected from the file itself, and the script prints what it found. If a detection looks wrong, you can override the column order with `--layout step` or `--layout channel`.

## Data credits

- Kaggle: *Air-Writing Gestures A–Z & 0–9 (ESP32 + MPU-6050)* by dinesh9890, https://www.kaggle.com/datasets/dinesh9890/air-writing-gestures-a-z-and-0-9-esp32-mpu-6050 (check the license on the page; credit the author)
- virtual-notepad by SoC Refugees, MIT license, https://github.com/va2465/virtual-notepad. Strokes were converted to `reference_data/virtual_notepad_strokes.json`, and the license is in `reference_data/virtual_notepad_LICENSE.txt`.
