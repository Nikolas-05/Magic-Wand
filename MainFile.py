
"""
live_predict.py

Live handwriting recognition using:
- Magic Wand Pen / Nano 33 BLE Sense Rev2
- PenTracker from live_draw.py
- Trained ONHW CNN model

SPACE: Start/stop recording and predict the letter
P:     Plot the last recording
B:     Recalibrate
Q:     Quit
"""

import os
import asyncio
import struct
import time
from collections import deque

import numpy as np
import torch
import torch.nn as nn
import matplotlib.pyplot as plt
import serial

from live_draw import (
    DEVICE_NAME, CHAR_UUID, PACKET_FMT, PACKET_LEN,
    find_usb_port, open_port, PenTracker, Canvas,
    BAUD, FPS
)


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "onhw_both_merged_acc2_gyro.pt"
)

device = "cuda" if torch.cuda.is_available() else "cpu"


# ---------------------------------------------------------
# CNN MODEL
# Same architecture as the training script
# ---------------------------------------------------------

class CNN(nn.Module):

    def __init__(self, n_in, n_cls, width=128):
        super().__init__()

        self.net = nn.Sequential(
            nn.Conv1d(n_in, width, 4),
            nn.ReLU(),
            nn.BatchNorm1d(width),
            nn.MaxPool1d(2),
            nn.Dropout(0.4),

            nn.Conv1d(width, width, 4),
            nn.ReLU(),
            nn.BatchNorm1d(width),
            nn.MaxPool1d(2),
            nn.Dropout(0.4),

            nn.Flatten(),

            nn.Linear(width * 13, 100),
            nn.ReLU(),
            nn.Dropout(0.4),

            nn.Linear(100, n_cls)
        )

    def forward(self, x):
        return self.net(x.transpose(1, 2))


# ---------------------------------------------------------
# LOAD TRAINED MODEL
# ---------------------------------------------------------

def load_model():

    checkpoint = torch.load(
        MODEL_PATH,
        map_location=device,
        weights_only=False
    )

    classes = checkpoint["classes"]

    model = CNN(
        n_in=len(checkpoint["cols"]),
        n_cls=len(classes),
        width=checkpoint["width"]
    ).to(device)

    model.load_state_dict(checkpoint["model"])
    model.eval()

    print("Model loaded successfully.")
    print("Device:", device)
    print("Classes:", classes)

    return model, checkpoint, classes


# ---------------------------------------------------------
# PREPROCESSING
# ---------------------------------------------------------

def resample(x, n=64):

    x = np.asarray(x, dtype=np.float32)

    t_old = np.linspace(0, 1, len(x))
    t_new = np.linspace(0, 1, n)

    out = np.stack([
        np.interp(t_new, t_old, x[:, c])
        for c in range(x.shape[1])
    ], axis=1)

    return out.astype(np.float32)


def preprocess(recording, checkpoint):

    # Live recording contains:
    # Acceleration XYZ + Gyroscope XYZ
    acc = np.asarray(recording["acc"], dtype=np.float32)
    gyr = np.asarray(recording["gyr"], dtype=np.float32)

    # Combine into six sensor channels.
    # IMPORTANT: Live acceleration must correspond to
    # the Acc2 channels used during model training.
    x = np.concatenate((acc, gyr), axis=1)

    if x.shape[1] != len(checkpoint["cols"]):
        raise ValueError(
            f"Expected {len(checkpoint['cols'])} channels, "
            f"received {x.shape[1]}"
        )

    # Resample to the training sequence length.
    x = resample(x, checkpoint["steps"])

    # Normalize using training statistics.
    x = (x - checkpoint["mean"]) / checkpoint["std"]

    # Add batch dimension: (64, 6) -> (1, 64, 6)
    x = torch.tensor(x, dtype=torch.float32)
    x = x.unsqueeze(0)

    return x.to(device)


# ---------------------------------------------------------
# PREDICTION
# ---------------------------------------------------------

def predict_letter(recording, model, checkpoint, classes):

    x = preprocess(recording, checkpoint)

    print("Input mean:", x.mean().item())
    print("Input std:", x.std().item())
    print("Input min:", x.min().item())
    print("Input max:", x.max().item())
    
    with torch.no_grad():

        output = model(x)

        # Convert logits into probabilities.
        probabilities = torch.softmax(output, dim=1)

        # Find the most likely class.
        confidence, prediction = probabilities.max(dim=1)

        index = prediction.item()
        letter = classes[index]

        confidence = confidence.item()

    return letter, confidence, probabilities.cpu().numpy()[0]


# ---------------------------------------------------------
# CANVAS WITH LIVE PREDICTION
# ---------------------------------------------------------

class PredictionCanvas(Canvas):

    def __init__(self, tracker, model, checkpoint, classes):

        super().__init__(tracker)

        self.model = model
        self.checkpoint = checkpoint
        self.classes = classes

        self.predictions = []

    def stop_recording(self):

        previous_count = len(self.recordings)

        # Keep the original recording behavior.
        super().stop_recording()

        # Check whether a valid recording was added.
        if len(self.recordings) == previous_count:
            return

        recording = self.recordings[-1]

        try:

            letter, confidence, probabilities = predict_letter(
                recording,
                self.model,
                self.checkpoint,
                self.classes
            )

            self.predictions.append({
                "actual": recording["label"],
                "predicted": letter,
                "confidence": confidence
            })

            self.message = (
                f"PREDICTION: {letter} | "
                f"Confidence: {confidence * 100:.1f}% | "
                f"Actual label: {recording['label']}"
            )

            print("\n--------------------------")
            print("Actual label: ", recording["label"])
            print("Predicted:    ", letter)
            print(f"Confidence:    {confidence * 100:.2f}%")
            print("--------------------------\n")

        except Exception as e:

            self.message = f"Prediction failed: {e}"
            print("Prediction error:", e)


# ---------------------------------------------------------
# USB CONNECTION
# ---------------------------------------------------------

def run_usb(port, model, checkpoint, classes):

    ser = open_port(port)

    tracker = PenTracker()

    canvas = PredictionCanvas(
        tracker, model, checkpoint, classes
    )

    last_ms = None
    last_draw = 0.0

    try:

        ser.reset_input_buffer()

        print(f"Connected over USB: {port}")
        print("Keep the Nano still for calibration.")

        buf = b""

        while not canvas.quit and plt.fignum_exists(canvas.fig.number):

            buf += ser.read(ser.in_waiting or 1)

            *lines, buf = buf.split(b"\n")

            for raw in lines:

                line = raw.decode(errors="ignore").strip()

                if not line or line.startswith("#"):
                    continue

                try:
                    v = [float(x) for x in line.split(",")[:7]]
                except ValueError:
                    continue

                if len(v) < 7:
                    continue

                ms = v[0]

                dt = (
                    0.01 if last_ms is None
                    else (ms - last_ms) / 1000.0
                )

                last_ms = ms

                if not 0 < dt < 0.2:
                    continue

                acc = v[1:4]
                gyr = v[4:7]

                tracker.update(dt, acc, gyr)
                canvas.add_sample(dt, acc, gyr)

            now = time.time()

            if now - last_draw > 1 / FPS:

                canvas.redraw()
                last_draw = now

            else:
                time.sleep(0.002)

    finally:

        ser.close()
        plt.close(canvas.fig)

        print("USB connection closed.")


# ---------------------------------------------------------
# BLUETOOTH CONNECTION
# ---------------------------------------------------------

async def run_ble(model, checkpoint, classes):

    from bleak import BleakClient, BleakScanner

    print(f"Scanning for {DEVICE_NAME}...")

    board = await BleakScanner.find_device_by_name(
        DEVICE_NAME,
        timeout=15
    )

    if board is None:
        print("Nano not found.")
        return

    samples = deque()

    def on_data(_, data):

        seq, flags, ax, ay, az, gx, gy, gz, *_ = struct.unpack(
            PACKET_FMT,
            data[:PACKET_LEN]
        )

        samples.append((
            seq,
            (ax / 1000, ay / 1000, az / 1000),
            (gx / 10, gy / 10, gz / 10)
        ))

    tracker = PenTracker()

    canvas = PredictionCanvas(
        tracker, model, checkpoint, classes
    )

    last_seq = None

    async with BleakClient(board) as client:

        await client.start_notify(CHAR_UUID, on_data)

        print("Connected over Bluetooth.")
        print("Keep the Nano still for calibration.")

        while (
            client.is_connected
            and not canvas.quit
            and plt.fignum_exists(canvas.fig.number)
        ):

            while samples:

                seq, acc, gyr = samples.popleft()

                steps = (
                    1 if last_seq is None
                    else (seq - last_seq) % 256
                )

                last_seq = seq

                if not 0 < steps < 20:
                    continue

                dt = 0.01 * steps

                tracker.update(dt, acc, gyr)
                canvas.add_sample(dt, acc, gyr)

            canvas.redraw()

            await asyncio.sleep(1 / FPS)

    print("Bluetooth disconnected.")


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

async def main():

    plt.close("all")

    # Load the trained CNN before connecting to the pen.
    model, checkpoint, classes = load_model()

    port = find_usb_port()

    if port is not None:

        try:

            run_usb(port, model, checkpoint, classes)

        except KeyboardInterrupt:
            pass

        except serial.SerialException as e:

            print("USB connection error:", e)

        return

    # If USB is unavailable, try Bluetooth.
    await run_ble(model, checkpoint, classes)


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
