#!/usr/bin/env python3
"""
pen_recorder.py - record labeled air-writing samples from the MagicWandPen
(Arduino Nano 33 BLE Sense Rev2, firmware/MagicWandPen).

Commands
  python pen_recorder.py ports                       list serial ports, mark the pen
  python pen_recorder.py live                        print live sensor values (sanity check)
  python pen_recorder.py record --writer nikolas     guided A-Z recording session
  python pen_recorder.py plot data/raw/nikolas/A/A_....csv   show one sample + pen-tip path
  python pen_recorder.py export                      build training CSVs from all samples

Connection (all commands that talk to the pen)
  default            USB serial, port auto-detected (Arduino VID 0x2341)
  --port COM5        a specific serial port
  --ble              Bluetooth LE instead of USB (needs `pip install bleak`)

Triggers for `record` (how a letter's start/end is detected)
  --trigger button   hold the button on D2 while writing (default, most reliable)
  --trigger key      press SPACE to start a letter, SPACE again to stop
  --trigger motion   starts when the pen moves, stops after it is still for 0.4 s

Each sample is saved as data/raw/<writer>/<LETTER>/<LETTER>_<time>.csv with columns
  t_s, ax_g, ay_g, az_g, gx_dps, gy_dps, gz_dps, mx_uT, my_uT, mz_uT, btn
and listed in data/index.csv.
"""

import argparse
import csv
import datetime as dt
import math
import os
import queue
import random
import string
import struct
import sys
import threading
import time
from pathlib import Path

import numpy as np

COLUMNS = ["t_s", "ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps",
           "mx_uT", "my_uT", "mz_uT", "btn"]
G = 9.80665

BLE_NAME = "MagicWandPen"
BLE_DATA_UUID = "6e400001-b5a3-f393-e0a9-e50e24dc4179"
BLE_CMD_UUID = "6e400002-b5a3-f393-e0a9-e50e24dc4179"
BLE_STRUCT = struct.Struct("<BB9h")          # 20 bytes, see the sketch header

ARDUINO_VIDS = {0x2341, 0x2A03}


# --------------------------------------------------------------------------
# Sources: produce rows [t_s, ax, ay, az, gx, gy, gz, mx, my, mz, btn]
# --------------------------------------------------------------------------
class Source:
    def __init__(self, rate):
        self.rate = rate
        self.q = queue.Queue(maxsize=20000)
        self.stop_flag = threading.Event()
        self.status = ""
        self.dropped = 0

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def close(self):
        self.stop_flag.set()

    def _put(self, row):
        try:
            self.q.put_nowait(row)
        except queue.Full:
            pass

    def read(self, timeout=0.1):
        """Return all rows received since the last call."""
        rows = []
        try:
            rows.append(self.q.get(timeout=timeout))
            while True:
                rows.append(self.q.get_nowait())
        except queue.Empty:
            pass
        return rows


def find_pen_port():
    from serial.tools import list_ports
    ports = list(list_ports.comports())
    for p in ports:
        if p.vid in ARDUINO_VIDS:
            return p.device
    return None


class SerialSource(Source):
    def __init__(self, port, rate):
        super().__init__(rate)
        import serial
        self.port = port or find_pen_port()
        if not self.port:
            sys.exit("Could not find the pen on USB. Plug it in, or pass --port COMx "
                     "(see `python pen_recorder.py ports`).")
        try:
            self.ser = serial.Serial(self.port, 115200, timeout=0.5)
        except Exception as e:
            sys.exit(f"Could not open {self.port}: {e}\n"
                     "Close the Arduino Serial Monitor/Plotter if it is open.")
        time.sleep(0.3)
        self.ser.reset_input_buffer()
        self.ser.write(f"r,{rate}\n".encode())

    def _run(self):
        t0_ms = None
        last_ms = None
        while not self.stop_flag.is_set():
            try:
                line = self.ser.readline().decode("ascii", "ignore").strip()
            except Exception as e:
                self.status = f"serial error: {e}"
                break
            if not line:
                continue
            if line.startswith("#"):
                self.status = line
                continue
            parts = line.split(",")
            if len(parts) != 11:
                continue
            try:
                vals = [float(x) for x in parts]
            except ValueError:
                continue
            ms = vals[0]
            if last_ms is not None and ms - last_ms > 1.5 * 1000.0 / self.rate:
                self.dropped += int(round((ms - last_ms) * self.rate / 1000.0)) - 1
            last_ms = ms
            if t0_ms is None:
                t0_ms = ms
            vals[0] = (ms - t0_ms) / 1000.0
            self._put(vals)
        self.ser.close()


class BLESource(Source):
    def __init__(self, rate, address=None):
        super().__init__(rate)
        try:
            import bleak  # noqa: F401
        except ImportError:
            sys.exit("BLE needs the bleak package:  pip install bleak")
        self.address = address
        self.ready = threading.Event()

    def start(self):
        super().start()
        if not self.ready.wait(20):
            sys.exit(f"Could not connect over BLE. {self.status}")

    def _run(self):
        import asyncio
        asyncio.run(self._main())

    async def _main(self):
        from bleak import BleakClient, BleakScanner
        dev = self.address
        if dev is None:
            print(f"Scanning for '{BLE_NAME}' ...")
            dev = await BleakScanner.find_device_by_name(BLE_NAME, timeout=10.0)
            if dev is None:
                self.status = "Pen not found. Is it powered (green LED) and not connected elsewhere?"
                return
        state = {"n": 0, "last_seq": None}
        period = 1.0 / self.rate

        def on_data(_, data: bytearray):
            if len(data) < BLE_STRUCT.size:
                return
            seq, flags, *v = BLE_STRUCT.unpack(bytes(data[:BLE_STRUCT.size]))
            if state["last_seq"] is not None:
                gap = (seq - state["last_seq"]) % 256
                if gap > 1:
                    self.dropped += gap - 1
                state["n"] += max(gap, 1)
            state["last_seq"] = seq
            row = [state["n"] * period,
                   v[0] / 1000.0, v[1] / 1000.0, v[2] / 1000.0,
                   v[3] / 10.0, v[4] / 10.0, v[5] / 10.0,
                   v[6] / 10.0, v[7] / 10.0, v[8] / 10.0,
                   float(flags & 1)]
            self._put(row)

        async with BleakClient(dev) as client:
            await client.write_gatt_char(BLE_CMD_UUID, f"r,{self.rate}".encode(), response=False)
            await client.start_notify(BLE_DATA_UUID, on_data)
            self.status = f"# BLE connected to {getattr(dev, 'address', dev)}"
            self.ready.set()
            while not self.stop_flag.is_set() and client.is_connected:
                await asyncio.sleep(0.1)
            if not client.is_connected:
                self.status = "BLE disconnected"


def open_source(args):
    src = BLESource(args.rate, args.address) if args.ble else SerialSource(args.port, args.rate)
    src.start()
    return src


# --------------------------------------------------------------------------
# Non-blocking single key press (Windows + macOS/Linux)
# --------------------------------------------------------------------------
class Keys:
    def __init__(self):
        self.win = os.name == "nt"
        self.tty = sys.stdin.isatty()
        if not self.win and self.tty:
            import termios
            import tty
            self.fd = sys.stdin.fileno()
            self.old = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)

    def get(self):
        if self.win:
            import msvcrt
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                return ch
            return None
        if not self.tty:
            return None
        import select
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None

    def restore(self):
        if not self.win and self.tty:
            import termios
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)


# --------------------------------------------------------------------------
# Segmenters: feed rows, get back finished letter windows
# --------------------------------------------------------------------------
class Segmenter:
    def __init__(self, rate, pre_s=0.1, min_s=0.25, max_s=6.0):
        self.rate = rate
        self.pre = max(1, int(pre_s * rate))
        self.min_n = int(min_s * rate)
        self.max_n = int(max_s * rate)
        self.history = []
        self.cur = None

    @property
    def active(self):
        return self.cur is not None

    def _begin(self):
        self.cur = list(self.history[-self.pre:])

    def _end(self):
        seg, self.cur = self.cur, None
        return seg if seg and len(seg) >= self.min_n else []

    def feed(self, row, key_toggle=False):
        """Return a finished segment (list of rows), [] for a too-short one, or None."""
        done = self.update(row, key_toggle)
        self.history.append(row)
        self.history = self.history[-self.pre:]
        if self.cur is not None:
            self.cur.append(row)
            if len(self.cur) >= self.max_n:
                return self._end()
        return done


class ButtonSegmenter(Segmenter):
    def update(self, row, key_toggle):
        if row[10] >= 0.5 and not self.active:
            self._begin()
        elif row[10] < 0.5 and self.active:
            return self._end()
        return None


class KeySegmenter(Segmenter):
    def update(self, row, key_toggle):
        return None          # start/stop is driven by toggle() from the keyboard

    def toggle(self):
        if self.active:
            return self._end()
        self._begin()
        return None


class MotionSegmenter(Segmenter):
    def __init__(self, rate, start_dps=60.0, still_dps=25.0, still_s=0.4, **kw):
        super().__init__(rate, pre_s=0.2, **kw)
        self.start_dps, self.still_dps = start_dps, still_dps
        self.still_n = int(still_s * rate)
        self.quiet = 0

    def update(self, row, key_toggle):
        w = math.sqrt(row[4] ** 2 + row[5] ** 2 + row[6] ** 2)
        if not self.active:
            if w > self.start_dps:
                self._begin()
                self.quiet = 0
            return None
        self.quiet = self.quiet + 1 if w < self.still_dps else 0
        if self.quiet >= self.still_n:
            seg = self._end()
            return seg[:-self.still_n] if seg and len(seg) - self.still_n >= self.min_n else []
        return None


# --------------------------------------------------------------------------
# Saving
# --------------------------------------------------------------------------
def save_sample(out_dir, writer, label, rows):
    t0 = rows[0][0]
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    d = Path(out_dir) / "raw" / writer / label
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{label}_{stamp}.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([f"{r[0] - t0:.3f}"] + [f"{x:.4f}" for x in r[1:10]] + [int(r[10])])
    index = Path(out_dir) / "index.csv"
    new = not index.exists()
    with open(index, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["path", "label", "writer", "n_samples", "duration_s", "recorded_at"])
        w.writerow([path.relative_to(out_dir).as_posix(), label, writer, len(rows),
                    f"{rows[-1][0] - t0:.3f}", stamp])
    return path


def remove_sample(out_dir, path):
    try:
        os.remove(path)
    except OSError:
        pass
    index = Path(out_dir) / "index.csv"
    if index.exists():
        rel = Path(path).relative_to(out_dir).as_posix()
        lines = index.read_text().splitlines(keepends=True)
        index.write_text("".join(l for l in lines if not l.startswith(rel + ",")))


def count_existing(out_dir, writer, label):
    d = Path(out_dir) / "raw" / writer / label
    return len(list(d.glob("*.csv"))) if d.exists() else 0


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
def cmd_ports(args):
    from serial.tools import list_ports
    pen = find_pen_port()
    for p in list_ports.comports():
        mark = "  <-- pen (Arduino)" if p.device == pen else ""
        print(f"{p.device:12s} {p.description}{mark}")
    if not pen:
        print("No Arduino found. Check the cable is a data cable, then double-tap reset "
              "if the board doesn't show up.")


def cmd_live(args):
    src = open_source(args)
    print("Live values (Ctrl+C to stop). Hold the pen still: |a| should be ~1.00 g, gyro ~0.")
    try:
        last = 0
        while True:
            rows = src.read()
            if rows and time.time() - last > 0.1:
                r = rows[-1]
                amag = math.sqrt(r[1] ** 2 + r[2] ** 2 + r[3] ** 2)
                print(f"\ra=({r[1]:+.2f},{r[2]:+.2f},{r[3]:+.2f})g |a|={amag:.2f}  "
                      f"g=({r[4]:+7.1f},{r[5]:+7.1f},{r[6]:+7.1f})dps  "
                      f"m=({r[7]:+6.1f},{r[8]:+6.1f},{r[9]:+6.1f})uT  btn={int(r[10])}  "
                      f"dropped={src.dropped}   ", end="", flush=True)
                last = time.time()
    except KeyboardInterrupt:
        print()
    finally:
        src.close()


def cmd_record(args):
    letters = [c for c in args.letters.upper() if c in string.ascii_uppercase]
    plan = []
    for c in letters:
        need = max(0, args.reps - count_existing(args.out, args.writer, c)) if args.resume else args.reps
        plan += [c] * need
    if args.shuffle:
        random.shuffle(plan)
    if not plan:
        print("Nothing to record: all letters already have enough samples.")
        return

    src = open_source(args)
    seg_cls = {"button": ButtonSegmenter, "key": KeySegmenter, "motion": MotionSegmenter}[args.trigger]
    seg = seg_cls(args.rate)
    how = {"button": "hold the pen button while writing, release when done",
           "key": "press SPACE, write, press SPACE again",
           "motion": "write the letter, then hold still for half a second"}[args.trigger]

    print(f"\nRecording {len(plan)} samples for writer '{args.writer}' ({how}).")
    print("Keys:  r = redo last   s = skip this letter   q = quit\n")
    keys = Keys()
    last_path = None
    i = 0
    prompted = -1

    def finish(done):
        nonlocal i, last_path
        if not done:
            print("     too short, try again")
            return
        last_path = save_sample(args.out, args.writer, plan[i], done)
        print(f"     saved {len(done)} samples ({done[-1][0] - done[0][0]:.2f} s)"
              f"{'  [dropped so far: %d]' % src.dropped if src.dropped else ''}")
        i += 1

    try:
        while i < len(plan):
            if prompted != i:
                print(f"[{i + 1}/{len(plan)}]  Write:  {plan[i]}", flush=True)
                prompted = i
            k = (keys.get() or "").lower()
            if k == "q":
                break
            if k == "s":
                print("     skipped")
                seg.cur = None
                i += 1
                continue
            if k == "r" and last_path is not None:
                remove_sample(args.out, last_path)
                print(f"     deleted {Path(last_path).name}, redo it")
                seg.cur = None
                last_path = None
                i -= 1
                prompted = -1
                continue
            if k == " " and args.trigger == "key":
                was_active = seg.active
                done = seg.toggle()
                print("     stopped" if was_active else "     ...recording")
                if was_active:
                    finish(done)
                    continue
            for row in src.read(timeout=0.02):
                done = seg.feed(row)
                if done is not None:
                    finish(done)
                    break
            if src.status and "error" in src.status.lower():
                print(src.status)
                break
    except KeyboardInterrupt:
        pass
    finally:
        keys.restore()
        src.close()
    print(f"\nDone. Samples are in {Path(args.out).resolve() / 'raw' / args.writer}")


# --------------------------------------------------------------------------
# Pen-tip path from orientation (gyro integration + gravity from accel)
# --------------------------------------------------------------------------
def _quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _rotate(q, v):
    qv = np.array([0.0, *v])
    qc = q * np.array([1, -1, -1, -1])
    return _quat_mul(_quat_mul(q, qv), qc)[1:]


def pen_path(data, pen_axis="x", kp=0.5):
    """
    Estimate where the pen points over time, as a 2D path (degrees).
    The board's `pen_axis` is treated as the pen's long axis. Orientation comes from
    integrating the gyro, with a light accelerometer correction (complementary filter)
    for tilt. Heading drift over a 1-3 s letter is small. Returns (x, y) arrays.

    This is *not* true position: an IMU cannot measure position without large drift.
    It is the direction the pen points, which traces the letter shape well when you
    write by moving your wrist/arm like a laser pointer.
    """
    t = data[:, 0]
    acc = data[:, 1:4]
    gyr = np.radians(data[:, 4:7])
    axis = {"x": np.array([1.0, 0, 0]), "y": np.array([0, 1.0, 0]), "z": np.array([0, 0, 1.0]),
            "-x": np.array([-1.0, 0, 0]), "-y": np.array([0, -1.0, 0]), "-z": np.array([0, 0, -1.0])}[pen_axis]

    # initial attitude: rotate measured gravity (board frame) onto world +Z
    a0 = acc[: max(1, min(10, len(acc)))].mean(axis=0)
    a0 = a0 / (np.linalg.norm(a0) + 1e-9)
    v = np.cross(a0, [0, 0, 1.0])
    s, c = np.linalg.norm(v), float(np.dot(a0, [0, 0, 1.0]))
    if s < 1e-6:
        q = np.array([1.0, 0, 0, 0]) if c > 0 else np.array([0.0, 1, 0, 0])
    else:
        ang = math.atan2(s, c)
        q = np.array([math.cos(ang / 2), *(math.sin(ang / 2) * v / s)])

    dirs = []
    for k in range(len(t)):
        dt_ = t[k] - t[k - 1] if k else (t[1] - t[0] if len(t) > 1 else 0.01)
        w = gyr[k]
        # tilt correction: nudge predicted gravity toward measured gravity
        an = np.linalg.norm(acc[k])
        if 0.8 < an < 1.2:                 # only trust accel when it's mostly gravity
            g_body = _rotate(q * np.array([1, -1, -1, -1]), [0, 0, 1.0])
            w = w + kp * np.cross(acc[k] / an, g_body)
        dq = np.array([1.0, *(0.5 * w * dt_)])
        q = _quat_mul(q, dq)
        q /= np.linalg.norm(q)
        dirs.append(_rotate(q, axis))
    d = np.array(dirs)
    yaw = np.degrees(np.unwrap(np.arctan2(d[:, 1], d[:, 0])))
    pitch = np.degrees(np.arcsin(np.clip(d[:, 2], -1, 1)))
    return -(yaw - yaw[0]), pitch - pitch[0]


def load_sample(path):
    return np.loadtxt(path, delimiter=",", skiprows=1)


def cmd_plot(args):
    import matplotlib.pyplot as plt
    data = load_sample(args.file)
    x, y = pen_path(data, args.pen_axis)
    if args.flip_x:
        x = -x
    if args.flip_y:
        y = -y
    fig, ax = plt.subplots(1, 3, figsize=(14, 4))
    t = data[:, 0]
    for k, n in zip(range(1, 4), "xyz"):
        ax[0].plot(t, data[:, k], label=f"a{n}")
    ax[0].set(title="Accelerometer (g)", xlabel="s")
    ax[0].legend()
    for k, n in zip(range(4, 7), "xyz"):
        ax[1].plot(t, data[:, k], label=f"g{n}")
    ax[1].set(title="Gyroscope (deg/s)", xlabel="s")
    ax[1].legend()
    sc = ax[2].scatter(x, y, c=t, s=8, cmap="viridis")
    ax[2].plot(x, y, lw=0.8, alpha=0.5)
    ax[2].set(title="Pen pointing path (deg)", aspect="equal")
    fig.colorbar(sc, ax=ax[2], label="s")
    fig.suptitle(Path(args.file).name)
    plt.tight_layout()
    plt.show()


# --------------------------------------------------------------------------
# Export to training-friendly formats
# --------------------------------------------------------------------------
def resample(data, n):
    t = data[:, 0]
    tn = np.linspace(t[0], t[-1], n)
    return np.column_stack([np.interp(tn, t, data[:, k]) for k in range(data.shape[1])])


def cmd_export(args):
    raw = Path(args.out) / "raw"
    files = sorted(raw.glob("*/*/*.csv"))
    if not files:
        sys.exit(f"No samples found under {raw}")
    n = args.steps
    out = Path(args.out)

    # 1) Kaggle-style: label + n steps x [ax ay az gx gy gz] in m/s^2 and rad/s, interleaved
    kag = out / f"export_kaggle_{n}x6.csv"
    with open(kag, "w", newline="") as f:
        w = csv.writer(f)
        hdr = ["label"] + [f"{c}_{i}" for i in range(n) for c in ("ax", "ay", "az", "gx", "gy", "gz")]
        w.writerow(hdr + ["writer", "source_file"])
        for p in files:
            d = resample(load_sample(p), n)
            feat = np.column_stack([d[:, 1:4] * G, np.radians(d[:, 4:7])]).reshape(-1)
            w.writerow([p.parent.name] + [f"{v:.5f}" for v in feat]
                       + [p.parent.parent.name, p.relative_to(out).as_posix()])

    # 2) Same, plus magnetometer, in the recorder's native units (g, deg/s, uT)
    full = out / f"export_full_{n}x9.csv"
    with open(full, "w", newline="") as f:
        w = csv.writer(f)
        names = ("ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps", "mx_uT", "my_uT", "mz_uT")
        w.writerow(["label"] + [f"{c}_{i}" for i in range(n) for c in names] + ["writer", "source_file"])
        for p in files:
            d = resample(load_sample(p), n)
            w.writerow([p.parent.name] + [f"{v:.4f}" for v in d[:, 1:10].reshape(-1)]
                       + [p.parent.parent.name, p.relative_to(out).as_posix()])

    # 3) Stroke JSON (2D pen path), for stroke/raster models like TFLM magic_wand
    import json
    strokes = []
    for i, p in enumerate(files):
        x, y = pen_path(load_sample(p), args.pen_axis)
        strokes.append({"index": i, "label": p.parent.name, "writer": p.parent.parent.name,
                        "strokePoints": [{"x": round(float(a), 3), "y": round(float(b), 3)}
                                         for a, b in zip(x, y)]})
    js = out / "export_strokes.json"
    js.write_text(json.dumps(strokes))

    labels = sorted({p.parent.name for p in files})
    print(f"{len(files)} samples, {len(labels)} letters: {''.join(labels)}")
    print(f"  {kag}\n  {full}\n  {js}")


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def conn(p):
        p.add_argument("--port", help="serial port, e.g. COM5 (default: auto-detect)")
        p.add_argument("--ble", action="store_true", help="use Bluetooth LE instead of USB")
        p.add_argument("--address", help="BLE address (default: scan for MagicWandPen)")
        p.add_argument("--rate", type=int, default=100, choices=[100, 50, 25, 20, 10], help="Hz")

    p = sub.add_parser("ports", help="list serial ports")
    p.set_defaults(func=cmd_ports)

    p = sub.add_parser("live", help="print live values")
    conn(p)
    p.set_defaults(func=cmd_live)

    p = sub.add_parser("record", help="guided recording session")
    conn(p)
    p.add_argument("--writer", required=True, help="name/ID of the person writing")
    p.add_argument("--letters", default=string.ascii_uppercase, help="letters to record (default A-Z)")
    p.add_argument("--reps", type=int, default=10, help="repetitions per letter")
    p.add_argument("--trigger", choices=["button", "key", "motion"], default="button")
    p.add_argument("--no-shuffle", dest="shuffle", action="store_false",
                   help="record letters in order instead of random order")
    p.add_argument("--no-resume", dest="resume", action="store_false",
                   help="don't count samples already on disk toward --reps")
    p.add_argument("--out", default="data")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("plot", help="plot one sample and its pen path")
    p.add_argument("file")
    p.add_argument("--pen-axis", default="x", choices=["x", "y", "z", "-x", "-y", "-z"])
    p.add_argument("--flip-x", action="store_true")
    p.add_argument("--flip-y", action="store_true")
    p.set_defaults(func=cmd_plot)

    p = sub.add_parser("export", help="build training CSV/JSON from all samples")
    p.add_argument("--out", default="data")
    p.add_argument("--steps", type=int, default=100, help="timesteps per sample after resampling")
    p.add_argument("--pen-axis", default="x", choices=["x", "y", "z", "-x", "-y", "-z"])
    p.set_defaults(func=cmd_export)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
