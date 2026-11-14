"""
live_draw.py  -  record a letter written in the air and draw its pen-pointing path.

Works with firmware/MagicWandPen/MagicWandPen.ino on a bare Nano 33 BLE Sense Rev2
(USB cable first, Bluetooth if no cable), same connection logic as Initial_setup.py.

HOW IT WORKS: PEN-POINTING PATH (laser pointer on a wall)
  Double-integrating the accelerometer to get position drifts by many cm within a
  second, so instead this tracks which way the pen POINTS:
    * the gyro is integrated into a 3D orientation (quaternion),
    * the accelerometer gently corrects the tilt (complementary filter), so the
      orientation can't slowly tip over,
    * the pen's long axis is turned into a heading (left/right) and an elevation
      (up/down) angle, exactly the spot a laser pointer would hit on a wall in front.
  Over a 1-3 s letter the heading drift is tiny, so the path traces the letter shape.
  Write with wrist and forearm motion, as if drawing on a wall with a laser pointer.

STEPS
  1. Keep the Nano still (on the table is best) while the window says
     "Calibrating" (~0.5 s, 2 s at most). This measures the gyro bias.
  2. Pick it up and CLICK ON THE PLOT WINDOW so it gets your key presses.
  3. Press SPACE to START recording, write the letter, press SPACE to STOP.
     Nothing is drawn or recorded until you press SPACE.
  4. Press P to plot that recording, E to export your recordings as stroke JSON.

KEYS (plot window must be focused)
  SPACE      start / stop recording a letter (each recording starts in the centre)
  Shift+A-Z  set the label for the next recordings (default "L")
  P          plot the last recording: pen path + accelerometer + gyro
  E          export all recordings of this run to strokes_<time>.json (next to this
             script). This is the ONLY thing that writes a file.
  BACKSPACE  delete the last recording
  C          clear the canvas
  R          re-centre the cursor
  B          recalibrate the gyro bias (hold the pen still first)
  x / y      mirror left-right / up-down, if letters come out flipped
  Q          quit (or just close the window)

EXPORT FORMAT (same as recorder/pen_recorder.py's export_strokes.json)
  [{"index": 0, "label": "L", "writer": "live_draw",
    "strokePoints": [{"x": 0.0, "y": 0.0}, {"x": -0.4, "y": 1.2}, ...]}, ...]
  x = left/right, y = down/up, both in degrees of pen rotation from where the
  recording started. A stroke/raster model (TensorFlow magic_wand / virtual-notepad
  style) rasterises these points into an image.
"""
import asyncio
import builtins
import json
import math
import os
import struct
import time
from collections import deque

import numpy as np
import matplotlib.pyplot as plt
import serial                              # pip install pyserial
from serial.tools import list_ports

# ---------------- connection settings (same as Initial_setup.py) ----------------
DEVICE_NAME = "MagicWandPen"
CHAR_UUID = "6e400001-b5a3-f393-e0a9-e50e24dc4179"
PACKET_FMT = "<BB9h"
PACKET_LEN = struct.calcsize(PACKET_FMT)
ARDUINO_VID = 0x2341
BAUD = 115200

# ---------------- drawing settings ----------------
PEN_AXIS = (0.0, 1.0, 0.0)   # board axis the pen tip points along (Y = the Nano's long axis).
                             # Mirrored drawing? use the X / Y keys. Tilting draws sideways? try (1, 0, 0).
CALIB_SECONDS = 0.5          # still-pen time for gyro bias (on a table the gyro noise is ~0.6 deg/s, so
                             # half a second already pins the bias to ~0.1 deg/s, well under DEADBAND)
STILL_LIMIT = 3.0            # deg/s: a window this still is accepted right away
CALIB_TIMEOUT = 2.0          # s: after this long, use the stillest window so far if it is under HAND_LIMIT
HAND_LIMIT = 8.0             # deg/s: steady hand-held noise; more than this = really moving, keep waiting
DEADBAND = 1.0               # deg/s: slower rotations are ignored (kills slow drift while holding still)
TILT_GAIN = 0.5              # how strongly the accelerometer pulls the tilt back to gravity (0 = gyro only)
LABEL = "L"                  # label given to new recordings (change live with Shift+letter)
MIN_RECORD_S = 0.2           # recordings shorter than this are thrown away
VIEW = 30.0                  # half-width of the canvas in degrees of pen rotation
FPS = 30


def find_usb_port():
    for port in list_ports.comports():
        if port.vid == ARDUINO_VID or "Nano 33 BLE" in (port.description or ""):
            return port.device
    return None


def open_port(port, tries=5):
    """Open the Nano's COM port. First closes a port left open by an earlier run in this
    same Spyder console, then retries for a few seconds in case Windows hasn't let go yet."""
    old = getattr(builtins, "_magic_wand_serial", None)
    if old is not None:
        try:
            old.close()
        except Exception:
            pass
        builtins._magic_wand_serial = None
    for attempt in range(tries):
        try:
            ser = serial.Serial(port, BAUD, timeout=0)
            builtins._magic_wand_serial = ser      # remembered so the next run can close it
            return ser
        except serial.SerialException:
            if attempt == tries - 1:
                raise
            print(f"{port} is busy, retrying ({attempt + 1}/{tries - 1})...")
            time.sleep(1)


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def _qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _qrot(q, v):
    """Rotate vector v by quaternion q (board -> world)."""
    return _qmul(_qmul(q, np.array([0.0, *v])), q * np.array([1, -1, -1, -1]))[1:]


def _q_from_gravity(acc):
    """Starting orientation: turn the measured 'up' (board frame) onto world +Z. Heading is arbitrary."""
    a0 = _unit(np.asarray(acc, float))
    v = np.cross(a0, [0, 0, 1.0])
    s, c = np.linalg.norm(v), float(np.dot(a0, [0, 0, 1.0]))
    if s < 1e-6:
        return np.array([1.0, 0, 0, 0]) if c > 0 else np.array([0.0, 1, 0, 0])
    ang = math.atan2(s, c)
    return np.array([math.cos(ang / 2), *(math.sin(ang / 2) * v / s)])


class PenTracker:
    """Turns (dt, accel g, gyro deg/s) samples into the pen-pointing direction, as 2D degrees."""

    def __init__(self, pen_axis=PEN_AXIS):
        self.pen = _unit(np.array(pen_axis, float))
        self.bias = np.zeros(3)
        self.calibrated = False
        self.q = np.array([1.0, 0, 0, 0])      # board -> world orientation
        self.yaw = self.pitch = 0.0            # where the pen points, degrees (yaw is unwrapped)
        self.yaw_ref = self.pitch_ref = 0.0    # the "centre of the wall"
        self.x = self.y = 0.0
        self.flip_x = self.flip_y = 1.0
        self.samples = 0
        self.start_calibration()

    def start_calibration(self):
        self.calibrated = False
        self._calib_time = 0.0                 # total time spent calibrating
        self._best = None                      # (spread, mean) of the stillest window so far
        self._reset_window()
        self.status = "Calibrating: keep the Nano still..."

    def _reset_window(self):
        # running sums only (no sample buffer): count, time, sum and sum of squares of ax..gz
        self._n, self._t = 0, 0.0
        self._sum = np.zeros(6)
        self._sq = np.zeros(6)

    def _finish_calibration(self, mean, spread):
        self.bias = mean[3:]
        self.q = _q_from_gravity(mean[:3])
        self._point()
        self.recenter()
        self.calibrated = True
        note = "" if spread <= STILL_LIMIT else " (was moving a bit, press B to redo if it drifts)"
        self.status = (f"Ready{note}. Gyro bias {np.round(self.bias, 2)} deg/s, noise {spread:.1f}. "
                       "SPACE = start recording")

    def update(self, dt, acc, gyr):
        acc = np.asarray(acc, float)
        gyr = np.asarray(gyr, float)
        self.samples += 1
        if not self.calibrated:
            row = np.concatenate([acc, gyr])
            self._n += 1
            self._t += dt
            self._sum += row
            self._sq += row * row
            self._calib_time += dt
            mean = self._sum / self._n
            spread = float(np.sqrt(np.maximum(self._sq[3:] / self._n - mean[3:] ** 2, 0)).max())
            if self._n > 5 and spread > HAND_LIMIT:     # clearly moving: start the window over
                self._reset_window()
            elif self._t >= CALIB_SECONDS:
                if self._best is None or spread < self._best[0]:
                    self._best = (spread, mean)
                if spread <= STILL_LIMIT:
                    self._finish_calibration(mean, spread)
                    return
                self._reset_window()
            if self._calib_time >= CALIB_TIMEOUT and self._best is not None:
                self._finish_calibration(self._best[1], self._best[0])
                return
            if self._calib_time >= CALIB_TIMEOUT:
                self.status = (f"Too much movement (gyro noise {spread:.0f} deg/s). "
                               "Set the Nano down on the table for a moment.")
            else:
                self.status = (f"Calibrating: keep the Nano still... gyro noise {spread:.1f} deg/s "
                               f"(want < {STILL_LIMIT:.0f})")
            return

        w = gyr - self.bias
        w[np.abs(w) < DEADBAND] = 0.0
        w = np.radians(w)
        # tilt correction (Mahony complementary filter): where the orientation thinks gravity is,
        # vs where the accelerometer says it is; turn a little toward the measurement
        a_norm = np.linalg.norm(acc)
        if TILT_GAIN > 0 and 0.8 < a_norm < 1.2:          # only trust accel when it's mostly gravity
            up_pred = _qrot(self.q * np.array([1, -1, -1, -1]), [0, 0, 1.0])
            w = w + TILT_GAIN * np.cross(acc / a_norm, up_pred)
        # integrate the gyro into the orientation
        self.q = _unit(_qmul(self.q, np.array([1.0, *(0.5 * w * dt)])))
        self._point()

    def _point(self):
        d = _qrot(self.q, self.pen)                       # pen axis in the world
        yaw = math.degrees(math.atan2(d[1], d[0]))
        self.yaw += (yaw - self.yaw + 180) % 360 - 180    # unwrapped, no jump at +-180
        self.pitch = math.degrees(math.asin(max(-1.0, min(1.0, d[2]))))
        self.x = -(self.yaw - self.yaw_ref) * self.flip_x
        self.y = (self.pitch - self.pitch_ref) * self.flip_y

    def recenter(self):
        self.yaw_ref, self.pitch_ref = self.yaw, self.pitch
        self.x = self.y = 0.0


class Canvas:
    def __init__(self, tracker):
        for k in list(plt.rcParams):           # free the keys we use from matplotlib's shortcuts
            if k.startswith("keymap."):
                plt.rcParams[k] = []
        self.t = tracker
        self.label = LABEL
        self.recordings = []                   # finished letters: dict(label, t, acc, gyr, x, y)
        self.rec = None                        # the recording in progress, or None
        self.message = ""
        self.quit = False
        self.t0 = time.time()
        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(7, 7))
        self.ax.set_xlim(-VIEW, VIEW)
        self.ax.set_ylim(-VIEW, VIEW)
        self.ax.set_aspect("equal")
        self.ax.grid(True, alpha=0.3)
        self.ax.set_xlabel("left / right (deg)")
        self.ax.set_ylabel("down / up (deg)")
        self.line, = self.ax.plot([], [], "-", lw=3, color="tab:blue")
        self.start_dot, = self.ax.plot([], [], "o", ms=7, color="tab:green")
        self.cursor, = self.ax.plot([0], [0], "o", ms=10, color="tab:gray")
        self.title = self.ax.set_title(tracker.status, fontsize=9)
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.fig.canvas.mpl_connect("close_event", lambda e: setattr(self, "quit", True))
        plt.show(block=False)

    # ---------- keys ----------
    def on_key(self, event):
        key = event.key or ""
        if len(key) == 1 and "A" <= key <= "Z":           # Shift+letter = new label
            self.label = key
            self.message = f"Label set to '{key}'."
            return
        k = key.lower()
        if k == " ":
            self.stop_recording() if self.rec is not None else self.start_recording()
        elif k == "p":
            self.plot_last()
        elif k == "e":
            self.export()
        elif k == "backspace":
            if self.rec is None and self.recordings:
                gone = self.recordings.pop()
                self.message = f"Deleted recording '{gone['label']}' ({len(self.recordings)} left)."
                self.clear_canvas()
        elif k == "c":
            self.clear_canvas()
        elif k == "r":
            if self.rec is None:
                self.t.recenter()
        elif k == "b":
            self.rec = None
            self.t.start_calibration()
        elif k == "x":
            self.t.flip_x *= -1
        elif k == "y":
            self.t.flip_y *= -1
        elif k == "q":
            self.quit = True

    def start_recording(self):
        if not self.t.calibrated:
            self.message = "Wait for calibration to finish first."
            return
        self.t.recenter()                      # every letter starts in the centre of the wall
        self.rec = {"label": self.label, "t": [], "acc": [], "gyr": [], "x": [], "y": []}
        self.clear_canvas()
        self.start_dot.set_data([0], [0])
        self.message = f"RECORDING '{self.label}'... press SPACE to stop."

    def stop_recording(self):
        rec, self.rec = self.rec, None
        dur = rec["t"][-1] if rec["t"] else 0.0
        if dur < MIN_RECORD_S:
            self.message = f"Too short ({dur:.2f} s), not kept. SPACE to try again."
            return
        self.recordings.append(rec)
        self.message = (f"Recorded '{rec['label']}' #{len(self.recordings)}: {dur:.2f} s, {len(rec['t'])} samples. "
                        "P = plot, E = export, SPACE = next")

    def add_sample(self, dt, acc, gyr):
        """Called for every sample after tracker.update()."""
        if self.rec is None or not self.t.calibrated:
            return
        r = self.rec
        r["t"].append((r["t"][-1] + dt) if r["t"] else 0.0)
        r["acc"].append(list(acc))
        r["gyr"].append(list(gyr))
        r["x"].append(self.t.x)
        r["y"].append(self.t.y)

    def clear_canvas(self):
        self.line.set_data([], [])
        self.start_dot.set_data([], [])

    # ---------- plot / export ----------
    def plot_last(self):
        if not self.recordings:
            self.message = "Nothing recorded yet: SPACE, write, SPACE."
            return
        r = self.recordings[-1]
        t = np.array(r["t"])
        acc, gyr = np.array(r["acc"]), np.array(r["gyr"]) - self.t.bias
        fig = plt.figure(figsize=(11, 5))
        ax0 = fig.add_subplot(1, 2, 1)
        ax0.plot(r["x"], r["y"], "-", lw=3, color="tab:blue")
        ax0.plot(r["x"][0], r["y"][0], "o", color="tab:green", label="start")
        ax0.plot(r["x"][-1], r["y"][-1], "s", color="tab:red", label="end")
        ax0.set_aspect("equal", adjustable="datalim")
        ax0.grid(True, alpha=0.3)
        ax0.legend(loc="best")
        ax0.set_title(f"Pen-pointing path: '{r['label']}' ({t[-1]:.2f} s)")
        ax0.set_xlabel("left / right (deg)")
        ax0.set_ylabel("down / up (deg)")
        for i, (data, name, unit) in enumerate([(acc, "Accelerometer", "g"), (gyr, "Gyro (bias removed)", "deg/s")]):
            ax = fig.add_subplot(2, 2, 2 * (i + 1))
            for j, c in enumerate(("tab:red", "tab:green", "tab:blue")):
                ax.plot(t, data[:, j], color=c, label="xyz"[j])
            ax.set_title(name, fontsize=9)
            ax.set_ylabel(unit)
            ax.grid(True, alpha=0.3)
            ax.legend(loc="upper right", ncol=3, fontsize=8)
        ax.set_xlabel("time (s)")
        fig.tight_layout()
        plt.show(block=False)
        self.message = f"Plotted recording #{len(self.recordings)}."

    def export(self):
        if not self.recordings:
            self.message = "Nothing to export yet."
            return
        strokes = [{"index": i, "label": r["label"], "writer": "live_draw",
                    "strokePoints": [{"x": round(float(a), 3), "y": round(float(b), 3)}
                                     for a, b in zip(r["x"], r["y"])]}
                   for i, r in enumerate(self.recordings)]
        folder = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(folder, f"strokes_{time.strftime('%Y%m%d_%H%M%S')}.json")
        with open(path, "w") as f:
            json.dump(strokes, f)
        print(f"Exported {len(strokes)} recordings to {path}")
        self.message = f"Exported {len(strokes)} recordings to {os.path.basename(path)}"

    # ---------- screen ----------
    def redraw(self):
        if self.rec is not None and self.rec["x"]:   # after SPACE-stop the finished letter stays on screen
            self.line.set_data(self.rec["x"], self.rec["y"])
        self.cursor.set_data([self.t.x], [self.t.y])
        self.cursor.set_color("tab:red" if self.rec is not None else "tab:gray")
        lim = max(VIEW, abs(self.t.x) + 5, abs(self.t.y) + 5)   # grow the view if you go off the edge
        if lim > self.ax.get_xlim()[1]:
            self.ax.set_xlim(-lim, lim)
            self.ax.set_ylim(-lim, lim)
        if self.t.samples == 0 and time.time() - self.t0 > 2:
            self.t.status = ("No data from the Nano yet. Is another program (Initial_setup.py, Serial Monitor) "
                             "using it? Restart the kernel with Ctrl+.")
        warn = ""
        if self.t.calibrated and abs(self.t.pitch) > 70:
            warn = "  |  pen points almost straight up/down: hold it like a laser pointer (or change PEN_AXIS)"
        line2 = self.message or ("SPACE = start recording" if self.t.calibrated else "")
        line1 = self.t.status if not self.t.calibrated else f"Label '{self.label}', {len(self.recordings)} recorded"
        self.title.set_text(f"{line1}{warn}\n{line2}")
        plt.pause(0.001)


def run_usb(port):
    ser = open_port(port)
    tracker = PenTracker()
    canvas = Canvas(tracker)
    last_ms = None
    last_draw = 0.0
    try:
        ser.reset_input_buffer()                   # drop stale data from before this run
        print(f"Connected over USB on {port}. Keep the Nano still for calibration...")
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
                dt = 0.01 if last_ms is None else (ms - last_ms) / 1000.0
                last_ms = ms
                if not 0 < dt < 0.2:               # skip gaps / board reset
                    continue
                tracker.update(dt, v[1:4], v[4:7])
                canvas.add_sample(dt, v[1:4], v[4:7])
            now = time.time()
            if now - last_draw > 1 / FPS:
                canvas.redraw()
                last_draw = now
            else:
                time.sleep(0.002)
    finally:                                       # always free the port, however the run ends
        ser.close()
        builtins._magic_wand_serial = None
        plt.close(canvas.fig)
        print("Stopped. COM port released, you can run again.")


async def run_ble():
    from bleak import BleakClient, BleakScanner
    print(f"No Nano on USB. Scanning Bluetooth for '{DEVICE_NAME}'...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=15)
    if device is None:
        print("Device not found. Is the board plugged in, or powered and advertising?")
        return
    samples = deque()

    def on_data(_, data: bytearray):
        seq, flags, ax, ay, az, gx, gy, gz, *_m = struct.unpack(PACKET_FMT, data[:PACKET_LEN])
        samples.append((seq, (ax / 1000, ay / 1000, az / 1000), (gx / 10, gy / 10, gz / 10)))

    tracker = PenTracker()
    canvas = Canvas(tracker)
    last_seq = None
    async with BleakClient(device) as client:
        await client.start_notify(CHAR_UUID, on_data)
        print("Connected over Bluetooth. Keep the Nano still for calibration...")
        while client.is_connected and not canvas.quit and plt.fignum_exists(canvas.fig.number):
            while samples:
                seq, acc, gyr = samples.popleft()
                steps = 1 if last_seq is None else (seq - last_seq) % 256   # seq counts at the output rate (100 Hz)
                last_seq = seq
                if not 0 < steps < 20:
                    continue
                tracker.update(0.01 * steps, acc, gyr)
                canvas.add_sample(0.01 * steps, acc, gyr)
            canvas.redraw()
            await asyncio.sleep(1 / FPS)
    print("Disconnected.")


async def main():
    plt.close("all")                               # close windows left over from an earlier run
    port = find_usb_port()
    if port is not None:
        try:
            run_usb(port)
        except KeyboardInterrupt:
            pass
        except serial.SerialException as e:
            print(f"Found the Nano on {port} but couldn't open it ({e}).\n"
                  "Something else still has the port: stop Initial_setup.py / close its plot window, "
                  "close the Arduino Serial Monitor/Plotter, or restart the Spyder kernel (Ctrl+.).")
        return
    await run_ble()


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
