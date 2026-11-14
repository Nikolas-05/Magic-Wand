"""
compare_letter.py: draw a letter in the air with the Nano 33 BLE and compare it
to open-source air-writing data.

It works with the sketch you already have (imu_ble_stream.ino, accel only) and
with the included accel+gyro sketch (imu_ble_stream_gyro/), and it picks the
right one automatically.

    python compare_letter.py                  # record one A and compare it (does everything)
    python compare_letter.py download         # fetch the Kaggle A-Z dataset (once)
    python compare_letter.py record A         # record one A over Bluetooth
    python compare_letter.py compare          # compare your newest recording
    python compare_letter.py compare --file my_letters\\A_20261108-101500.csv
    python compare_letter.py compare --file imu_log.csv   # a log from ArduinoDAQ.py works too

What "compare" does:
  1. Trims the still parts before/after the letter.
  2. Converts units (g -> m/s^2, deg/s -> rad/s) to match the Kaggle data.
  3. Resamples the letter to 100 steps (Kaggle's fixed length; 50 Hz x 2 s).
  4. Removes the mean of each channel (gravity) and scales to unit RMS, so
     slow/fast and small/big letters can be compared.
  5. Finds the axis mapping between your board and the dataset's sensor
     (24 possible rotations). Every letter gets the same freedom, so the
     nearest-letter check stays fair.
  6. DTW (dynamic time warping) distance to every letter, a 5-nearest-neighbour
     vote, and overlay plots. With gyro data it also compares the pen-pointing
     path to the virtual-notepad strokes (MIT, Nano 33 BLE).

Data sources:
  Kaggle "Air-Writing Gestures A-Z & 0-9 (ESP32 + MPU-6050)", 100 steps x
  [ax ay az gx gy gz] at 50 Hz:
  https://www.kaggle.com/datasets/dinesh9890/air-writing-gestures-a-z-and-0-9-esp32-mpu-6050
  virtual-notepad by SoC Refugees (MIT): https://github.com/va2465/virtual-notepad
"""
import argparse
import csv
import datetime as dt
import glob
import io
import json
import math
import os
import queue
import struct
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REF_DIR = HERE / "reference_data"
KAGGLE_DIR = REF_DIR / "kaggle"
VN_FILE = REF_DIR / "virtual_notepad_strokes.json"
MY_DIR = HERE / "my_letters"
CACHE_FILE = KAGGLE_DIR / "kaggle_cache.npz"

KAGGLE_SLUG = "dinesh9890/air-writing-gestures-a-z-and-0-9-esp32-mpu-6050"
KAGGLE_PAGE = f"https://www.kaggle.com/datasets/{KAGGLE_SLUG}"
KAGGLE_API = f"https://www.kaggle.com/api/v1/datasets/download/{KAGGLE_SLUG}"

DEVICE_NAME = "Nano33-IMU"
ACCEL_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"      # <Ifff  t_ms, ax, ay, az (g)
IMU6_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214"       # <I6h   t_ms, a (mg), g (0.1 dps)

G = 9.80665
N_STEPS = 100          # Kaggle fixed length
BAND = 15              # DTW warping window (steps)
K_NN = 5


# ==========================================================================
# Recording over Bluetooth
# ==========================================================================
class BleStream:
    """Runs bleak in its own thread, so it also works inside Spyder/Jupyter."""

    def __init__(self, name=DEVICE_NAME):
        self.name = name
        self.q = queue.Queue()
        self.status = queue.Queue()
        self.has_gyro = False
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def start(self, timeout=25):
        self._t.start()
        while True:
            try:
                kind, msg = self.status.get(timeout=timeout)
            except queue.Empty:
                raise SystemExit("Timed out waiting for Bluetooth.")
            if kind == "info":
                print(msg)
            elif kind == "error":
                raise SystemExit(msg)
            elif kind == "ready":
                return

    def stop(self):
        self._stop.set()
        self._t.join(timeout=5)

    def _run(self):
        import asyncio
        try:
            asyncio.run(self._main())
        except Exception as e:                         # report, don't die silently
            self.status.put(("error", f"Bluetooth error: {e}"))

    async def _main(self):
        import asyncio
        try:
            from bleak import BleakClient, BleakScanner
        except ImportError:
            self.status.put(("error", "bleak is not installed. Run: pip install -r requirements.txt"))
            return
        self.status.put(("info", f"Scanning for '{self.name}' (up to 15 s)..."))
        dev = await BleakScanner.find_device_by_name(self.name, timeout=15)
        if dev is None:
            self.status.put(("error", f"'{self.name}' not found. Is the board powered, and is "
                                      "no other program (ArduinoDAQ.py, phone app) connected to it?"))
            return
        async with BleakClient(dev) as client:
            uuids = {c.uuid.lower() for s in client.services for c in s.characteristics}

            def on_imu6(_, data):
                t, *v = struct.unpack("<I6h", bytes(data[:16]))
                self.q.put((t, v[0] / 1000, v[1] / 1000, v[2] / 1000,
                            v[3] / 10, v[4] / 10, v[5] / 10))

            def on_accel(_, data):
                self.q.put(struct.unpack("<Ifff", bytes(data[:16])))

            if IMU6_UUID in uuids:
                self.has_gyro = True
                await client.start_notify(IMU6_UUID, on_imu6)
                self.status.put(("info", "Connected: accel + gyro."))
            elif ACCEL_UUID in uuids:
                await client.start_notify(ACCEL_UUID, on_accel)
                self.status.put(("info", "Connected: accel only (flash imu_ble_stream_gyro to add gyro)."))
            else:
                self.status.put(("error", "Connected, but the board has no known data characteristic."))
                return
            self.status.put(("ready", None))
            while client.is_connected and not self._stop.is_set():
                await asyncio.sleep(0.05)

    def drain(self):
        rows = []
        while True:
            try:
                rows.append(self.q.get_nowait())
            except queue.Empty:
                return rows


def cmd_record(args, letter=None):
    letter = (letter or args.letter or "A").upper()
    MY_DIR.mkdir(exist_ok=True)
    ble = BleStream(args.name)
    ble.start()
    try:
        time.sleep(0.5)
        ble.drain()
        print(f"\nHold the board the way you hold the pen. Keep it still.")
        input(f"Press ENTER, then draw a big '{letter}' in the air (about 1-2 s)... ")
        ble.drain()
        print("  Recording. Draw now, then hold still and press ENTER.")
        input()
        rows = ble.drain()
    finally:
        ble.stop()
    if len(rows) < 20:
        raise SystemExit(f"Only {len(rows)} samples arrived. Check the connection and try again.")
    t = np.array([r[0] for r in rows], float)
    rate = (len(t) - 1) / max(1e-3, (t[-1] - t[0]) / 1000)
    path = MY_DIR / f"{letter}_{dt.datetime.now():%Y%m%d-%H%M%S}.csv"
    cols = ["t_ms", "ax", "ay", "az"] + (["gx", "gy", "gz"] if ble.has_gyro else [])
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([int(r[0])] + [f"{x:.5f}" for x in r[1:len(cols)]])
    print(f"Saved {len(rows)} samples ({rate:.0f} Hz) to {path}")
    return path


# ==========================================================================
# Loading recordings
# ==========================================================================
def load_recording(path):
    """
    Returns (t_seconds, acc_g [n,3], gyro_dps [n,3] or None).
    Reads this tool's CSVs, ArduinoDAQ.py logs (t_ms,ax,ay,az) and
    recorder/pen_recorder.py raw samples (t_s, ax_g.. gz_dps, ...).
    """
    with open(path, newline="") as f:
        header = [h.strip().lower() for h in next(csv.reader(f))]
    d = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    t = d[:, 0] / (1000.0 if header[0] in ("t_ms", "millis", "ms") else 1.0)
    acc = d[:, 1:4]
    gyr = None
    if len(header) >= 7 and header[4].startswith("g"):
        gyr = d[:, 4:7]
    return t, acc, gyr


def newest_recording(letter=None):
    files = sorted(MY_DIR.glob(f"{letter or ''}*.csv"), key=os.path.getmtime)
    files = [f for f in files if not f.name.endswith("_compare.csv")]
    return files[-1] if files else None


def trim_motion(t, acc, gyr, pad_s=0.10):
    """Cut the still parts at the start and end, keeping the biggest movement."""
    if gyr is not None:
        e = np.linalg.norm(gyr, axis=1) / 100.0                 # ~1 at 100 deg/s
    else:
        e = np.abs(np.linalg.norm(acc, axis=1) - 1.0) * 4       # ~1 at 0.25 g off gravity
        e = e + np.linalg.norm(np.diff(acc, axis=0, prepend=acc[:1]), axis=1) * 8
    k = max(1, int(round(0.1 / max(1e-3, np.median(np.diff(t))))))
    e = np.convolve(e, np.ones(k) / k, mode="same")
    thr = max(0.25 * np.percentile(e, 95), np.percentile(e, 20) * 2, 0.05)
    on = e > thr
    if not on.any():
        return slice(0, len(t))
    # group "on" stretches separated by < 0.35 s, keep the one with most energy
    idx = np.flatnonzero(on)
    gap = int(0.35 / max(1e-3, np.median(np.diff(t))))
    groups, start = [], idx[0]
    for a, b in zip(idx[:-1], idx[1:]):
        if b - a > gap:
            groups.append((start, a))
            start = b
    groups.append((start, idx[-1]))
    s, e_ = max(groups, key=lambda g: e[g[0]:g[1] + 1].sum())
    p = int(pad_s / max(1e-3, np.median(np.diff(t))))
    return slice(max(0, s - p), min(len(t), e_ + p + 1))


# ==========================================================================
# Kaggle dataset
# ==========================================================================
def cmd_download(args=None):
    KAGGLE_DIR.mkdir(parents=True, exist_ok=True)
    if find_kaggle_csv():
        print(f"Kaggle data already in {KAGGLE_DIR}")
        return True
    print(f"Downloading the Kaggle dataset (~37 MB) from\n  {KAGGLE_API}")
    try:
        req = urllib.request.Request(KAGGLE_API, headers={"User-Agent": "magic-wand-compare/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            blob = r.read()
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            z.extractall(KAGGLE_DIR)
        print(f"Saved to {KAGGLE_DIR}")
        return True
    except Exception as e:
        print(f"\nAutomatic download failed ({e}).")
        print("Download it by hand instead (free Kaggle account needed):")
        print(f"  1. Open {KAGGLE_PAGE}")
        print("  2. Click Download, and unzip it.")
        print(f"  3. Put the .csv file (or the .zip) in:  {KAGGLE_DIR}")
        return False


def find_kaggle_csv():
    for z in KAGGLE_DIR.glob("*.zip"):
        with zipfile.ZipFile(z) as zf:
            zf.extractall(KAGGLE_DIR)
        z.rename(z.with_suffix(".zip.done"))
    files = [Path(p) for p in glob.glob(str(KAGGLE_DIR / "**" / "*.csv"), recursive=True)]
    return max(files, key=os.path.getsize) if files else None


def load_kaggle(layout="auto", letters_only=True):
    """
    Returns labels [N] (str), X [N, 100, 6] in the CSV's own units, info dict.
    The column order of the 600 values is detected from the data: either
    step-major (t0_ax, t0_ay, ... t0_gz, t1_ax ...) or channel-major
    (ax_0..ax_99, ay_0..ay_99, ...).
    """
    path = find_kaggle_csv()
    if path is None:
        if not cmd_download():
            raise SystemExit("No Kaggle data yet; see the steps above.")
        path = find_kaggle_csv()
    if CACHE_FILE.exists() and CACHE_FILE.stat().st_mtime > path.stat().st_mtime and layout == "auto":
        c = np.load(CACHE_FILE, allow_pickle=False)
        labels, X, info = c["labels"], c["X"], json.loads(str(c["info"]))
    else:
        print(f"Reading {path.name} (first time only)...")
        with open(path, newline="") as f:
            rd = csv.reader(f)
            header = next(rd)
            rows = list(rd)
        hl = [h.strip().lower() for h in header]
        lab_col = next((i for i, h in enumerate(hl) if h in ("label", "class", "letter", "target", "y")), None)
        if lab_col is None:   # first column that isn't numeric
            lab_col = next(i for i, v in enumerate(rows[0]) if not _isnum(v))
        num_cols = [i for i in range(len(header)) if i != lab_col and _isnum(rows[0][i])]
        if len(num_cols) > 600:     # drop id/index-like columns, keep the last 600
            num_cols = num_cols[-600:]
        if len(num_cols) != 600:
            raise SystemExit(f"Expected 600 numeric columns in {path.name}, found {len(num_cols)}.")
        labels = np.array([r[lab_col].strip().upper() for r in rows])
        flat = np.array([[float(r[i]) for i in num_cols] for r in rows], dtype=np.float32)
        if layout == "auto":
            # neighbouring time steps of one channel are similar; pick the layout that agrees
            lag1 = np.mean(np.abs(np.diff(flat[:, :300], axis=1)))
            lag6 = np.mean(np.abs(flat[:, 6:306] - flat[:, :300]))
            layout = "step" if lag6 < lag1 else "channel"
        X = flat.reshape(-1, 100, 6) if layout == "step" else flat.reshape(-1, 6, 100).transpose(0, 2, 1)
        # units
        grav = np.median(np.linalg.norm(X[:, :, :3].mean(axis=1), axis=1))
        acc_unit = "m/s^2" if grav > 3 else ("g" if grav > 0.3 else "unknown (gravity removed?)")
        g95 = np.percentile(np.abs(X[:, :, 3:]), 95)
        gyr_unit = "deg/s" if g95 > 20 else "rad/s"
        info = {"file": path.name, "layout": layout, "acc_unit": acc_unit, "gyr_unit": gyr_unit,
                "gravity_norm": float(grav)}
        np.savez_compressed(CACHE_FILE, labels=labels, X=X, info=json.dumps(info))
    if letters_only:
        keep = np.array([len(l) == 1 and "A" <= l <= "Z" for l in labels])
        labels, X = labels[keep], X[keep]
    return labels, X, info


def _isnum(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


# ==========================================================================
# Preprocessing
# ==========================================================================
def resample(t, x, n=N_STEPS):
    tn = np.linspace(t[0], t[-1], n)
    return np.column_stack([np.interp(tn, t, x[:, i]) for i in range(x.shape[1])])


def normalize(x, n_acc=3):
    """x [steps, ch] -> remove each channel's mean (gravity/bias), scale accel and
    gyro groups to unit RMS separately. Works on [N, steps, ch] too."""
    x = x - x.mean(axis=-2, keepdims=True)
    out = []
    for sl in (slice(0, n_acc), slice(n_acc, None)):
        part = x[..., sl]
        if part.shape[-1] == 0:
            continue
        rms = np.sqrt((part ** 2).mean(axis=(-2, -1), keepdims=True)) + 1e-9
        out.append(part / rms)
    return np.concatenate(out, axis=-1)


def rotations24():
    """All 24 proper rotations that only swap/flip axes, as (perm, signs)."""
    import itertools
    out = []
    for p in itertools.permutations(range(3)):
        for s in itertools.product((1, -1), repeat=3):
            m = np.zeros((3, 3))
            for i in range(3):
                m[i, p[i]] = s[i]
            if np.linalg.det(m) > 0:
                out.append((p, s))
    return out


def apply_rot(x, rot):
    """Apply an axis mapping to every 3-channel group of x [.., steps, 3k]."""
    p, s = rot
    y = x.copy()
    for g0 in range(0, x.shape[-1], 3):
        for i in range(3):
            y[..., g0 + i] = s[i] * x[..., g0 + p[i]]
    return y


def rot_name(rot):
    p, s = rot
    return ",".join(("-" if s[i] < 0 else "") + "xyz"[p[i]] for i in range(3))


def parse_rot(text):
    parts = [q.strip().lower() for q in text.split(",")]
    p = tuple("xyz".index(q[-1]) for q in parts)
    s = tuple(-1 if q.startswith("-") else 1 for q in parts)
    return p, s


# ==========================================================================
# DTW
# ==========================================================================
def dtw_batch(q, refs, band=BAND):
    """DTW distance between one sequence q [n, c] and many refs [N, m, c].
    Sakoe-Chiba band, squared-Euclidean cost. Returns [N]: sqrt(total cost / max(n, m)),
    roughly the RMS mismatch per aligned step."""
    refs = np.asarray(refs, float)
    N, m, _ = refs.shape
    n = len(q)
    band = max(band, abs(n - m))
    prev = np.full((N, m + 1), np.inf)
    prev[:, 0] = 0
    for i in range(1, n + 1):
        cur = np.full((N, m + 1), np.inf)
        lo, hi = max(1, i - band), min(m, i + band)
        cost = ((refs[:, lo - 1:hi, :] - q[i - 1]) ** 2).sum(-1)       # [N, hi-lo+1]
        diag = np.minimum(prev[:, lo - 1:hi], prev[:, lo:hi + 1])      # from (i-1, j-1) or (i-1, j)
        for k, j in enumerate(range(lo, hi + 1)):
            cur[:, j] = cost[:, k] + np.minimum(diag[:, k], cur[:, j - 1])
        prev = cur
    return np.sqrt(prev[:, m] / max(n, m))


def dtw_path(q, r, band=BAND):
    """Warping path for plotting: returns index pairs (i, j)."""
    n, m = len(q), len(r)
    band = max(band, abs(n - m))
    D = np.full((n + 1, m + 1), np.inf)
    D[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(max(1, i - band), min(m, i + band) + 1):
            D[i, j] = ((q[i - 1] - r[j - 1]) ** 2).sum() + min(D[i - 1, j - 1], D[i - 1, j], D[i, j - 1])
    i, j, path = n, m, []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        k = np.argmin([D[i - 1, j - 1], D[i - 1, j], D[i, j - 1]])
        i, j = (i - 1, j - 1) if k == 0 else ((i - 1, j) if k == 1 else (i, j - 1))
    return path[::-1]


# ==========================================================================
# Comparison against Kaggle (raw motion)
# ==========================================================================
def compare_kaggle(query, labels, Xn, target, fixed_rot=None):
    """
    query [100, c] normalized; Xn [N, 100, c] normalized dataset (same channels).
    For each letter, picks the axis mapping that fits that letter's average best,
    then measures DTW to every sample of that letter.
    """
    classes = sorted(set(labels))
    templates = np.stack([Xn[labels == c].mean(axis=0) for c in classes])
    rots = [fixed_rot] if fixed_rot else rotations24()
    D = np.stack([dtw_batch(apply_rot(query, r), templates) for r in rots])   # [R, C]
    best_r = D.argmin(axis=0)
    res = {"classes": classes, "template_dist": D[best_r, range(len(classes))],
           "rot": {c: rots[best_r[k]] for k, c in enumerate(classes)}, "templates": templates}
    nn = []
    for r in set(res["rot"].values()):                       # one DTW call per distinct mapping
        cls_r = [c for c in classes if res["rot"][c] == r]
        idx = np.flatnonzero(np.isin(labels, cls_r))
        d = dtw_batch(apply_rot(query, r), Xn[idx])
        nn += [(float(v), labels[i], int(i)) for v, i in zip(d, idx)]
        if target in cls_r:
            res["target_sample_dist"] = d[labels[idx] == target]
    k = classes.index(target)
    res["target_self_dist"] = dtw_batch(templates[k], Xn[labels == target])
    nn.sort()
    res["knn"] = nn[:K_NN]
    return res


# ==========================================================================
# Pen-pointing path (needs gyro) vs virtual-notepad strokes
# ==========================================================================
def _qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _qrot(q, v):
    return _qmul(_qmul(q, np.array([0.0, *v])), q * np.array([1, -1, -1, -1]))[1:]


def pen_path(t, acc_g, gyr_dps, pen_axis, kp=0.5):
    """Direction the pen points (yaw, pitch in degrees) from gyro + accel tilt correction.
    Same method as recorder/pen_recorder.py."""
    gyr = np.radians(gyr_dps)
    axis = np.zeros(3)
    axis["xyz".index(pen_axis[-1])] = -1.0 if pen_axis.startswith("-") else 1.0
    a0 = acc_g[: min(10, len(acc_g))].mean(axis=0)
    a0 /= np.linalg.norm(a0) + 1e-9
    v = np.cross(a0, [0, 0, 1.0])
    s, c = np.linalg.norm(v), float(np.dot(a0, [0, 0, 1.0]))
    q = (np.array([1.0, 0, 0, 0]) if c > 0 else np.array([0.0, 1, 0, 0])) if s < 1e-6 else \
        np.array([math.cos(math.atan2(s, c) / 2), *(math.sin(math.atan2(s, c) / 2) * v / s)])
    dirs = []
    for k in range(len(t)):
        dt_ = t[k] - t[k - 1] if k else (t[1] - t[0])
        w = gyr[k].copy()
        an = np.linalg.norm(acc_g[k])
        if 0.8 < an < 1.2:
            w += kp * np.cross(acc_g[k] / an, _qrot(q * np.array([1, -1, -1, -1]), [0, 0, 1.0]))
        q = _qmul(q, np.array([1.0, *(0.5 * w * dt_)]))
        q /= np.linalg.norm(q)
        dirs.append(_qrot(q, axis))
    d = np.array(dirs)
    yaw = np.degrees(np.unwrap(np.arctan2(d[:, 1], d[:, 0])))
    pitch = np.degrees(np.arcsin(np.clip(d[:, 2], -1, 1)))
    return np.column_stack([-(yaw - yaw[0]), pitch - pitch[0]])


def norm_path(p, n=64):
    """Resample a 2D path to n points evenly spaced along its length, center, scale to 1."""
    p = np.asarray(p, float)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] < 1e-9:
        return np.zeros((n, 2))
    u = np.linspace(0, s[-1], n)
    r = np.column_stack([np.interp(u, s, p[:, 0]), np.interp(u, s, p[:, 1])])
    r -= r.mean(axis=0)
    return r / (np.abs(r).max() + 1e-9)


FLIPS = [(1, 1), (-1, 1), (1, -1), (-1, -1)]


def compare_strokes(t, acc, gyr, target):
    """Each letter may pick its best pen axis and mirror flip (same freedom for all letters)."""
    vn = json.loads(VN_FILE.read_text())["letters"]
    refs = {c: np.stack([norm_path(s) for s in v]) for c, v in vn.items()}
    all_refs = np.concatenate([refs[c] for c in sorted(refs)])
    all_lab = np.concatenate([[c] * len(refs[c]) for c in sorted(refs)])
    per_class = {}
    for ax in ("x", "-x", "y", "-y", "z", "-z"):
        p = pen_path(t, acc, gyr, ax)
        if np.ptp(p, axis=0).max() < 3:          # pointing barely moved: not the pen axis
            continue
        base = norm_path(p)
        for f in FLIPS:
            d = dtw_batch(base * np.array(f), all_refs, band=12)
            for c in refs:
                dc = d[all_lab == c]
                score = float(np.sort(dc)[:3].mean())       # mean of the 3 closest samples
                if c not in per_class or score < per_class[c]["score"]:
                    per_class[c] = {"score": score, "flip": f, "axis": ax, "d": dc,
                                    "path": base * np.array(f)}
    if not per_class:
        return None
    return {"per_class": per_class, "refs": refs}


# ==========================================================================
# Report + plots
# ==========================================================================
def cmd_compare(args, path=None):
    target = (args.letter or "A").upper()
    path = Path(path or args.file or newest_recording() or "")
    if not path.is_file():
        raise SystemExit("No recording found. Run:  python compare_letter.py record A")
    t, acc, gyr = load_recording(path)
    sl = trim_motion(t, acc, gyr) if not args.no_trim else slice(0, len(t))
    t, acc = t[sl], acc[sl]
    gyr = gyr[sl] if gyr is not None else None
    dur = t[-1] - t[0]
    rate = (len(t) - 1) / max(dur, 1e-6)
    print(f"\nYour recording: {path.name}")
    print(f"  letter segment: {dur:.2f} s, {len(t)} samples, {rate:.0f} Hz, "
          f"{'accel + gyro' if gyr is not None else 'accel only'}")
    if dur < 0.4:
        print("  Warning: very short movement. Draw bigger and slower (1-2 s).")

    labels, X, info = load_kaggle(args.layout)
    print(f"Open data: Kaggle air-writing, {len(labels)} letter samples, "
          f"{(labels == target).sum()} of them '{target}'")
    print(f"  detected: {info['layout']}-major columns, accel in {info['acc_unit']}, gyro in {info['gyr_unit']}")

    # --- units: ours g / deg/s -> dataset's units (shown in the plot) -----------
    acc_scale = G if info["acc_unit"] == "m/s^2" else 1.0
    gyr_scale = math.pi / 180 if info["gyr_unit"] == "rad/s" else 1.0
    mine = acc * acc_scale
    if gyr is not None and not args.accel_only:
        mine = np.column_stack([mine, gyr * gyr_scale])
        ch = slice(0, 6)
    else:
        ch = slice(0, 3)
    mine_rs = resample(t, mine)                     # length -> 100 steps
    q = normalize(mine_rs)
    Xn = normalize(X[:, :, ch].astype(float))

    fixed = parse_rot(args.axes) if args.axes else None
    res = compare_kaggle(q, labels, Xn, target, fixed)

    order = np.argsort(res["template_dist"])
    rank = int(np.flatnonzero(np.array(res["classes"])[order] == target)[0]) + 1
    tdist = res["template_dist"][res["classes"].index(target)]
    pct = 100 * np.mean(res["target_self_dist"] > tdist)
    votes = {}
    for d, c, _ in res["knn"]:
        votes[c] = votes.get(c, 0) + 1
    vote = max(votes, key=lambda c: (votes[c], -min(d for d, cc, _ in res["knn"] if cc == c)))
    rot = res["rot"][target]

    print(f"\n=== Raw-motion comparison ({'accel+gyro' if ch.stop == 6 else 'accel only'}, DTW) ===")
    print(f"Axis mapping used for '{target}' (dataset x,y,z = your ...): {rot_name(rot)}")
    print(f"  Re-use it with:  --axes={rot_name(rot)}")
    print(f"DTW distance to the average '{target}': {tdist:.3f}")
    print(f"  {pct:.0f}% of the dataset's own '{target}' samples are farther from that average than yours")
    print(f"  (dataset '{target}'s: median {np.median(res['target_self_dist']):.3f}, "
          f"90th pct {np.percentile(res['target_self_dist'], 90):.3f})")
    print(f"Closest single '{target}' sample: {res['target_sample_dist'].min():.3f}")
    print(f"\nNearest letters (distance to each letter's average):")
    for k in order[:6]:
        c = res["classes"][k]
        mark = "  <-- target" if c == target else ""
        print(f"  {c}  {res['template_dist'][k]:.3f}{mark}")
    print(f"'{target}' ranks #{rank} of {len(res['classes'])}.")
    print(f"{K_NN}-nearest-sample vote: {vote}  ({', '.join(f'{c}:{n}' for c, n in sorted(votes.items(), key=lambda z: -z[1]))})")

    strokes = None
    if gyr is not None:
        strokes = compare_strokes(t, acc, gyr, target)
        if strokes:
            pc = strokes["per_class"]
            so = sorted(pc, key=lambda c: pc[c]["score"])
            print(f"\n=== Pen-path comparison vs virtual-notepad strokes (gyro) ===")
            print(f"For '{target}': pen axis {pc[target]['axis']}, mirror flip {pc[target]['flip']}")
            print("Nearest letters: " + ", ".join(f"{c} {pc[c]['score']:.3f}" for c in so[:5]))
            print(f"'{target}' ranks #{so.index(target) + 1} of {len(so)}.")
    else:
        print("\n(Pen-path vs virtual-notepad comparison skipped: needs gyro."
              " Flash imu_ble_stream_gyro/imu_ble_stream_gyro.ino to enable it.)")

    out_png = path.with_name(path.stem + "_compare.png")
    make_plots(out_png, target, q, Xn, labels, res, mine_rs, X[:, :, ch] , strokes, ch.stop == 6,
               info, show=not args.no_show)
    print(f"\nPlot saved to {out_png}")


def make_plots(out_png, target, q, Xn, labels, res, mine_rs, Xraw, strokes, has_gyro, info, show=True):
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rot = res["rot"][target]
    qm = apply_rot(q, rot)
    mine_m = apply_rot(mine_rs, rot)
    idx = np.flatnonzero(labels == target)
    A = Xn[idx]
    k = res["classes"].index(target)
    tmpl = res["templates"][k]
    nch = q.shape[1]
    names = ["ax", "ay", "az", "gx", "gy", "gz"][:nch]
    acc_u, gyr_u = info["acc_unit"], info["gyr_unit"]

    ncols = 4 if strokes else 3
    fig = plt.figure(figsize=(4.2 * ncols, 2.0 * nch + 3.2))
    gs = fig.add_gridspec(nch + 2, ncols)
    steps = np.arange(N_STEPS)
    path = dtw_path(qm, tmpl)
    warped = np.zeros_like(tmpl)
    cnt = np.zeros(len(tmpl))
    for i, j in path:
        warped[j] += qm[i]
        cnt[j] += 1
    warped /= cnt[:, None]

    rng = np.random.default_rng(0)
    some = A[rng.choice(len(A), size=min(12, len(A)), replace=False)]
    for c in range(nch):
        # col 0: raw units, col 1: normalized overlay, col 2: after DTW alignment
        ax0 = fig.add_subplot(gs[c, 0])
        raw = Xraw[idx][:, :, c]
        ax0.fill_between(steps, np.percentile(raw, 10, axis=0), np.percentile(raw, 90, axis=0),
                         color="#9bb7d4", alpha=0.5, label=f"open-data {target} (10-90%)")
        ax0.plot(steps, np.median(raw, axis=0), color="#2b5d8a", lw=1.2, label="median")
        ax0.plot(steps, mine_m[:, c], color="#d1495b", lw=2, label="you")
        ax0.set_ylabel(f"{names[c]} [{acc_u if c < 3 else gyr_u}]", fontsize=8)
        ax1 = fig.add_subplot(gs[c, 1])
        for s in some:
            ax1.plot(steps, s[:, c], color="#9bb7d4", lw=0.6)
        ax1.plot(steps, tmpl[:, c], color="#2b5d8a", lw=1.5, label=f"average {target}")
        ax1.plot(steps, qm[:, c], color="#d1495b", lw=2, label="you")
        ax2 = fig.add_subplot(gs[c, 2])
        ax2.plot(steps, tmpl[:, c], color="#2b5d8a", lw=1.5)
        ax2.plot(steps, warped[:, c], color="#d1495b", lw=2)
        if c == 0:
            ax0.set_title("Units matched, 100 steps", fontsize=9)
            ax1.set_title("Normalized (gravity removed, RMS=1)", fontsize=9)
            ax2.set_title("Yours after DTW time-alignment", fontsize=9)
            ax0.legend(fontsize=6, loc="upper right")
            ax1.legend(fontsize=6, loc="upper right")
        for a in (ax0, ax1, ax2):
            a.tick_params(labelsize=7)
            if c < nch - 1:
                a.set_xticklabels([])
    # bar chart of distances per letter
    axb = fig.add_subplot(gs[nch:, 0:3])
    cls = res["classes"]
    d = res["template_dist"]
    colors = ["#d1495b" if c == target else "#9bb7d4" for c in cls]
    axb.bar(cls, d, color=colors)
    axb.set_ylabel("DTW distance to letter average", fontsize=8)
    axb.set_title(f"Which letter does your movement look like? (lower = closer)  "
                  f"{'accel+gyro' if has_gyro else 'accel only'}", fontsize=9)
    axb.set_ylim(min(d) * 0.9, max(d) * 1.02)
    axb.tick_params(labelsize=8)

    if strokes:
        pc = strokes["per_class"]
        ref = strokes["refs"][target]
        axs = fig.add_subplot(gs[0:nch, 3])
        for r in ref[:15]:
            axs.plot(r[:, 0], r[:, 1], color="#9bb7d4", lw=0.7)
        p = pc[target]["path"]
        axs.plot(p[:, 0], p[:, 1], color="#d1495b", lw=2.2, label="your pen path")
        axs.plot(p[0, 0], p[0, 1], "o", color="#d1495b")
        axs.set_aspect("equal")
        axs.set_title(f"Pen path vs virtual-notepad '{target}'", fontsize=9)
        axs.legend(fontsize=7, loc="lower right")
        axs.tick_params(labelsize=7)
        axv = fig.add_subplot(gs[nch:, 3])
        so = sorted(pc, key=lambda c: pc[c]["score"])[:8]
        axv.barh(so[::-1], [pc[c]["score"] for c in so[::-1]],
                 color=["#d1495b" if c == target else "#9bb7d4" for c in so[::-1]])
        axv.set_title("Pen-path DTW, 8 closest letters", fontsize=9)
        axv.tick_params(labelsize=8)

    fig.suptitle(f"Your '{target}' vs open-source air-writing data", fontsize=11)
    fig.tight_layout()
    fig.savefig(out_png, dpi=120)
    if show:
        plt.show()
    plt.close(fig)


# ==========================================================================
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("letter", nargs="?", default="A", help="letter to draw/compare (default A)")
        p.add_argument("--name", default=DEVICE_NAME, help="BLE name the board advertises")
        p.add_argument("--file", help="compare this CSV instead of the newest recording")
        p.add_argument("--axes", help="fix the axis mapping, e.g. --axes=y,-x,z (printed by a previous run)")
        p.add_argument("--accel-only", action="store_true", help="ignore gyro even if recorded")
        p.add_argument("--no-trim", action="store_true", help="don't cut still parts")
        p.add_argument("--no-show", action="store_true", help="save the plot without opening a window")
        p.add_argument("--layout", default="auto", choices=["auto", "step", "channel"],
                       help="Kaggle column order (auto-detected)")

    common(sub.add_parser("run", help="record one letter, then compare (default)"))
    sub.add_parser("download", help="download the Kaggle dataset")
    common(sub.add_parser("record", help="record one letter over Bluetooth"))
    common(sub.add_parser("compare", help="compare a recording with the open data"))

    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("run", "download", "record", "compare", "-h", "--help"):
        argv = ["run"] + argv
    args = ap.parse_args(argv)

    if args.cmd == "download":
        cmd_download(args)
    elif args.cmd == "record":
        cmd_record(args)
    elif args.cmd == "compare":
        cmd_compare(args)
    else:
        load_kaggle(args.layout)              # make sure the data is there before recording
        p = cmd_record(args)
        cmd_compare(args, p)


if __name__ == "__main__":
    main()
