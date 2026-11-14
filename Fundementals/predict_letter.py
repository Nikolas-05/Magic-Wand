"""
predict_letter.py  -  write an uppercase letter with the Nano 33 BLE, watch the filtered
motion signals live, and get a prediction learned from the OnHW "Raw data set".
 
NO INTEGRATION: nothing is integrated (no gyro -> angle, no accel -> position), so
nothing drifts. The window shows the accelerometer and gyro themselves, turned into the
raw data's pen axes and low-pass filtered. The prediction uses the same signals, filtered
with the same 5-sample moving average as the raw data.
 
Same connection and keys as live_draw.py (USB cable first, Bluetooth if no cable), works
with firmware/MagicWandPen/MagicWandPen.ino. Only needs numpy, matplotlib, pyserial
(+ bleak and nest_asyncio for Bluetooth), no torch or scikit-learn.
 
THE RAW DATA (Raw data set/onhw2_upper_indep_0, the OnHW-chars dataset)
  15,650 uppercase letters (A-Z) from 100+ writers, written ON PAPER with a STABILO
  DigiPen at 100 Hz (same rate as the Nano). Each sample is 13 raw, uncalibrated sensor
  columns:
      0-2  front accelerometer   16384 counts per g
      3-5  rear accelerometer    (not used here, the Nano has one accelerometer)
      6-8  gyroscope             ~28.6 counts per deg/s, sign reversed vs the accelerometer
      9-11 magnetometer          (not used, depends on the room)
      12   tip force             (not used, the Nano has no tip sensor)
  Pen axes, worked out from gravity in the data: +y runs along the pen from the tip to the
  back, +z is the underside of the pen (the side facing the paper), +x points to the
  writer's right.
  There is no calibration step in the data: every letter simply starts with the pen in
  the normal writing pose, back end up about 60 deg above horizontal, rolled ~17 deg
  (its right side a little lower than its left).
 
  The model: each letter (accelerometer + gyro in the pen's axes) is stretched to 32
  time steps, each channel normalised, and a small neural net (one hidden layer, numpy)
  is trained on it. It is trained on the first run (~20 s) and saved to
  letter_model.npz next to this script; delete that file to retrain.
  Writer-independent accuracy on the raw data's own test writers is printed when it
  trains (about 75%). Your Nano in the air is a different pen and a different motion,
  so expect less until you write the way the data was written (see TIPS).
 
CALIBRATION (rest position = you holding the pen)
  Hold the pen still in your normal writing grip for about 1 s when the window opens.
  That one step measures the gyro bias (from your steady hand) and takes your grip as
  the rest position. Your grip is then lined up with the raw data's starting pose, so
  the letters you write are seen from the same angle as the raw letters.
    - long edge of the board along your fingers (the board's Y axis = the pen),
    - chip side up, facing away from the paper, tip toward the table.
  The raw data's own grip is back end up ~60 deg, right edge ~17 deg low. The title
  shows how far your grip is from that. Any steady grip is accepted (set
  REQUIRE_POSE_MATCH = True to insist on a close match); the closer it is, the better
  the raw data fits. Which end is the "tip" is detected from how you hold it.
  Every recording checks that it starts near your rest grip and warns if not.
 
KEYS (click on the plot window first)
  SPACE      start / stop writing a letter. Prediction updates while you write and the
             final answer appears when you stop.
  Shift+A-Z  (optional) tell it which letter you are about to write: it keeps score
  P          plot the last letter: its signals, what the model sees vs the closest
             raw-data letter, top-5 probabilities
  E          export recordings + predictions to predictions_<time>.json
  BACKSPACE  delete the last recording
  C          clear the finished letter (back to the scrolling view)
  B          recalibrate (hold the pen still in your grip)
  K          during calibration with REQUIRE_POSE_MATCH = True: accept your grip anyway
  Q          quit (or close the window)
 
TIPS
  - The raw data is handwriting on paper: small letters, ~0.5 s each, wrist and fingers.
    Writing on the table with the Nano held like a pen matches it best. Writing just
    above the table also works. Big arm-sized letters in the air match it worst.
  - Write each letter in one go and press SPACE right before and right after. Still
    time at the start and end is cut off automatically.
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
 
# ---------------- connection settings (same as live_draw.py) ----------------
DEVICE_NAME = "MagicWandPen"
CHAR_UUID = "6e400001-b5a3-f393-e0a9-e50e24dc4179"
PACKET_FMT = "<BB9h"
PACKET_LEN = struct.calcsize(PACKET_FMT)
ARDUINO_VID = 0x2341
BAUD = 115200
 
# ---------------- raw data / model ----------------
HERE = os.path.dirname(os.path.abspath(__file__))
RAW_FOLDER = "onhw2_upper_indep_0"         # any upper_indep_N fold has all the letters
MODEL_FILE = os.path.join(HERE, "letter_model.npz")
MODEL_VERSION = 4
T_STEPS = 32                               # every letter is stretched to this many steps
HIDDEN = 256
EPOCHS = 30
ACC_COUNTS_PER_G = 16384.0                 # DigiPen front accelerometer
GYRO_COUNTS_PER_DPS = 28.57                # DigiPen gyro, best guess (+-1000 deg/s range). Only used
                                           # for the exported counts: prediction is scale-free
GYRO_RAW_SIGN = -1.0                       # DigiPen gyro sign vs its accelerometer axes
 
# ---------------- calibration ----------------
HOLD_SECONDS = 1.0           # s: hold the pen still in your grip this long (gyro bias + rest pose)
CALIB_TIMEOUT = 4.0          # s: then take the steadiest window so far (if under 2 x HAND_LIMIT)
HAND_LIMIT = 8.0             # deg/s: steady hand
REQUIRE_POSE_MATCH = False   # True = only accept a grip within POSE_TOL of the raw data's start pose
POSE_TOL = 20.0              # deg: how close to the raw data's starting pose (80% of raw letters start within 20)
START_WARN = 30.0            # deg: warn if a recording starts further than this from your rest grip
 
# ---------------- noise filtering / recording ----------------
SMOOTH_SAMPLES = 5           # moving average for the model, 50 ms (raw data gets the same filter;
                             # 5 scored best: 75.9% vs 74.7% with none and 75.2% with 9)
LIVE_SMOOTH = 0.25           # 0..1 low-pass for the live traces (~5 Hz at 100 Hz; smaller = smoother)
GYRO_NOISE_DPS = 1.5         # live gyro traces: slower than this shows as 0 (display only)
WINDOW_S = 3.0               # seconds of signal shown while not recording
MIN_RECORD_S = 0.15
MIN_MOTION_DPS = 20.0        # trimming: slower than this (or 15% of the peak) counts as still
LIVE_PREDICT_EVERY = 0.25    # s between predictions while writing
FPS = 30
 
 
# =====================================================================================
#  Features (shared by the raw data and the Nano, so both go through the same steps)
# =====================================================================================
def resample(sig, n=T_STEPS):
    """(len, ch) -> (n, ch) by linear interpolation over the whole letter."""
    sig = np.asarray(sig, float)
    if len(sig) == 1:
        return np.repeat(sig, n, 0)
    src = np.arange(len(sig))
    dst = np.linspace(0, len(sig) - 1, n)
    return np.stack([np.interp(dst, src, sig[:, c]) for c in range(sig.shape[1])], 1)
 
 
def normalise(res):
    """Per-channel zero mean / unit spread. Removes gravity, gyro bias and the units, so
    the DigiPen's counts and the Nano's g and deg/s compare directly. (..., T, 6)"""
    res = res - res.mean(-2, keepdims=True)
    return res / (res.std(-2, keepdims=True) + 1e-6)
 
 
def raw_to_pen(raw):
    """One raw OnHW sample (len, 13) -> accel (g) and gyro (deg/s) in the pen's axes."""
    raw = np.asarray(raw, float)
    return raw[:, 0:3] / ACC_COUNTS_PER_G, GYRO_RAW_SIGN * raw[:, 6:9] / GYRO_COUNTS_PER_DPS
 
 
def pen_to_raw(acc_g, gyr_dps):
    """Nano data already in pen axes -> the same counts the raw data uses (for plots)."""
    return (np.asarray(acc_g) * ACC_COUNTS_PER_G,
            np.asarray(gyr_dps) * GYRO_COUNTS_PER_DPS * GYRO_RAW_SIGN)
 
 
def trim_still(acc, gyr):
    """Cut the still time before and after the letter (gyro must be bias-free)."""
    n = len(gyr)
    if n < 10:
        return acc, gyr
    mag = np.convolve(np.linalg.norm(gyr, axis=1), np.ones(5) / 5, "same")
    thr = max(MIN_MOTION_DPS, 0.15 * mag.max())
    idx = np.where(mag > thr)[0]
    if len(idx) == 0 or idx[-1] - idx[0] < 8:
        return acc, gyr
    a, b = max(0, idx[0] - 3), min(n, idx[-1] + 4)
    return acc[a:b], gyr[a:b]
 
 
def smooth(sig, n=SMOOTH_SAMPLES):
    """Centred moving average over n samples (edges padded), removes sensor jitter."""
    sig = np.asarray(sig, float)
    if n <= 1 or len(sig) < 3:
        return sig
    p = n // 2
    pad = np.r_[np.repeat(sig[:1], p, 0), sig, np.repeat(sig[-1:], n - 1 - p, 0)]
    c = np.cumsum(np.r_[np.zeros((1, sig.shape[1])), pad], 0)
    return (c[n:] - c[:-n]) / n
 
 
def letter_features(acc_pen, gyr_pen):
    """Accel (g) + gyro (deg/s) in pen axes -> smoothed, (T_STEPS, 6) un-normalised."""
    return resample(np.c_[smooth(acc_pen), smooth(gyr_pen)])
 
 
# =====================================================================================
#  Model: small numpy MLP + nearest raw letters for comparison
# =====================================================================================
def find_raw_folder():
    for base in (HERE, os.path.dirname(HERE), os.getcwd(), os.path.dirname(os.getcwd())):
        p = os.path.join(base, "Raw data set", RAW_FOLDER)
        if os.path.isfile(os.path.join(p, "X_train.npy")):
            return p
    raise FileNotFoundError(f"Couldn't find 'Raw data set/{RAW_FOLDER}' next to or above {HERE}")
 
 
def _random_rotations(n, deg, rng):
    """n random rotation matrices, angle ~ N(0, deg) about random axes."""
    ax = rng.normal(size=(n, 3))
    ax /= np.linalg.norm(ax, axis=1, keepdims=True)
    th = np.radians(rng.normal(0, deg, n))[:, None, None]
    K = np.zeros((n, 3, 3))
    K[:, 0, 1], K[:, 0, 2], K[:, 1, 2] = -ax[:, 2], ax[:, 1], -ax[:, 0]
    K = K - K.transpose(0, 2, 1)
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K
 
 
def _augment(F, rng):
    """Random small change of pen pose (same rotation on accel and gyro) and speed."""
    R = _random_rotations(len(F), 12.0, rng)
    acc = np.einsum("nij,ntj->nti", R, F[:, :, :3])
    gyr = np.einsum("nij,ntj->nti", R, F[:, :, 3:])
    out = np.concatenate([acc, gyr], 2)
    return out * (1 + 0.1 * rng.normal(size=(len(F), 1, 6)))
 
 
class LetterModel:
    def __init__(self, d):
        self.W1, self.b1, self.W2, self.b2 = d["W1"], d["b1"], d["W2"], d["b2"]
        self.classes = [str(c) for c in d["classes"]]
        self.ref_up = d["ref_up"]
        self.test_acc = float(d["test_acc"])
        self.knn_x = d["knn_x"].astype(np.float32)          # normalised raw letters, flattened
        self.knn_y = d["knn_y"]                             # class index of each
        self.knn_raw = d["knn_raw"]                         # un-normalised (N, T, 6), for plots
 
    def probs(self, feats):
        x = normalise(feats).reshape(-1)
        h = np.maximum(x @ self.W1 + self.b1, 0)
        z = h @ self.W2 + self.b2
        p = np.exp(z - z.max())
        return p / p.sum()
 
    def nearest(self, feats, k=5):
        x = normalise(feats).reshape(-1).astype(np.float32)
        d = ((self.knn_x - x) ** 2).sum(1)
        idx = np.argsort(d)[:k]
        return idx, d[idx] / x.size
 
    @staticmethod
    def train_and_save(path=MODEL_FILE):
        folder = find_raw_folder()
        print(f"Training the letter model from {folder} (first run only, ~20 s)...")
        load = lambda f: np.load(os.path.join(folder, f), allow_pickle=True)
        Xtr, ytr, Xte, yte = load("X_train.npy"), load("y_train.npy"), load("X_test.npy"), load("y_test.npy")
        classes = np.array(sorted(set(ytr)))
 
        def build(X):
            F, ups = [], []
            for s in X:
                acc, gyr = raw_to_pen(s)
                up = acc[:5].mean(0)
                ups.append(up / np.linalg.norm(up))
                acc, gyr = trim_still(acc, gyr)          # raw gyro bias (~3 deg/s) is far below the trim threshold
                F.append(letter_features(acc, gyr))
            return np.array(F), np.array(ups)
 
        Ftr, up_tr = build(Xtr)
        Fte, up_te = build(Xte)
        itr, ite = np.searchsorted(classes, ytr), np.searchsorted(classes, yte)
        ref_up = np.r_[up_tr, up_te].mean(0)
        ref_up /= np.linalg.norm(ref_up)
 
        rng = np.random.default_rng(0)
        d_in, n_cls = T_STEPS * 6, len(classes)
        P = [rng.normal(0, math.sqrt(2 / d_in), (d_in, HIDDEN)), np.zeros(HIDDEN),
             rng.normal(0, math.sqrt(1 / HIDDEN), (HIDDEN, n_cls)), np.zeros(n_cls)]
        M = [np.zeros_like(p) for p in P]
        V = [np.zeros_like(p) for p in P]
        step, lr, wd = 0, 1e-3, 1e-4
        Xte_n = normalise(Fte).reshape(len(Fte), -1)
        for ep in range(EPOCHS):
            A = normalise(_augment(Ftr, rng)).reshape(len(Ftr), -1)
            perm = rng.permutation(len(A))
            for s in range(0, len(A), 128):
                ix = perm[s:s + 128]
                x, yy = A[ix], itr[ix]
                mask = (rng.random((len(ix), HIDDEN)) > 0.3) / 0.7        # dropout
                h = np.maximum(x @ P[0] + P[1], 0) * mask
                z = h @ P[2] + P[3]
                z -= z.max(1, keepdims=True)
                g = np.exp(z)
                g /= g.sum(1, keepdims=True)
                g[np.arange(len(yy)), yy] -= 1
                g /= len(yy)
                gh = (g @ P[2].T) * (h > 0) * mask
                grads = [x.T @ gh + wd * P[0], gh.sum(0), h.T @ g + wd * P[2], g.sum(0)]
                step += 1
                for i, gr in enumerate(grads):                          # Adam
                    M[i] = 0.9 * M[i] + 0.1 * gr
                    V[i] = 0.999 * V[i] + 0.001 * gr * gr
                    P[i] -= lr * (M[i] / (1 - 0.9 ** step)) / (np.sqrt(V[i] / (1 - 0.999 ** step)) + 1e-8)
            if ep % 10 == 9 or ep == EPOCHS - 1:
                acc = np.mean((np.maximum(Xte_n @ P[0] + P[1], 0) @ P[2] + P[3]).argmax(1) == ite)
                print(f"  epoch {ep + 1}/{EPOCHS}: {acc:.1%} right on writers it never saw")
        F_all = np.r_[Ftr, Fte]
        np.savez_compressed(path, version=MODEL_VERSION, T=T_STEPS, W1=P[0], b1=P[1], W2=P[2], b2=P[3],
                            classes=classes, ref_up=ref_up, test_acc=acc,
                            knn_x=normalise(F_all).reshape(len(F_all), -1).astype(np.float32),
                            knn_y=np.r_[itr, ite], knn_raw=F_all.astype(np.float16))
        print(f"Saved {path}")
 
    @classmethod
    def load(cls, path=MODEL_FILE):
        if os.path.isfile(path):
            d = np.load(path, allow_pickle=False)
            if int(d["version"]) == MODEL_VERSION and int(d["T"]) == T_STEPS:
                return cls(d)
            print("Model file is from an older version, retraining.")
        cls.train_and_save(path)
        return cls(np.load(path, allow_pickle=False))
 
 
# =====================================================================================
#  Orientation helpers (as in live_draw.py)
# =====================================================================================
def find_usb_port():
    for port in list_ports.comports():
        if port.vid == ARDUINO_VID or "Nano 33 BLE" in (port.description or ""):
            return port.device
    return None
 
 
def open_port(port, tries=5):
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
            builtins._magic_wand_serial = ser
            return ser
        except serial.SerialException:
            if attempt == tries - 1:
                raise
            print(f"{port} is busy, retrying ({attempt + 1}/{tries - 1})...")
            time.sleep(1)
 
 
def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v
 
 
def rotation_between(a, b):
    """Smallest rotation matrix that turns unit vector a onto unit vector b."""
    a, b = _unit(np.asarray(a, float)), _unit(np.asarray(b, float))
    v, c = np.cross(a, b), float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K / (1 + c)
 
 
def board_to_pen_matrix(s):
    """Nano board axes -> raw-data pen axes, Nano held like a pen with the chip side up.
    s = +1 if the board's +Y points to the back of the pen (up, toward your hand), -1 if
    it points to the tip.  pen y = s*Y (tip->back), pen z = -Z (underside),
    pen x = y cross z = -s*X (to the right).  A proper rotation (det +1)."""
    return np.array([[-s, 0, 0], [0, s, 0], [0, 0, -1.0]])
 
 
def pose_angles(up_pen):
    """Elevation of the pen's back end above horizontal, and roll, in degrees."""
    u = _unit(up_pen)
    return math.degrees(math.asin(max(-1, min(1, u[1])))), math.degrees(math.atan2(u[0], -u[2]))
 
 
# =====================================================================================
#  Tracker: gyro bias + rest grip -> pen-axis signals matched to the raw data (no integration)
# =====================================================================================
class PenTracker:
    def __init__(self, ref_up):
        self.ref_up = _unit(np.asarray(ref_up, float))
        self.ref_elev, self.ref_roll = pose_angles(self.ref_up)
        self.bias = np.zeros(3)
        self.acc_s = self.ref_up.copy()        # smoothed accel, pen axes (for the live traces)
        self.gyr_s = np.zeros(3)               # smoothed gyro, pen axes, bias removed
        self.samples = 0
        self.acc_lp = None
        self.gyro_sign = 1.0                   # self-checked against the accelerometer below
        self._gs = np.zeros(3)                 # num, den, nn for that check
        self._u_prev = None
        self.to_pen = np.eye(3)                # board -> pen axes (incl. small pose alignment)
        self.rest_up = np.array([0, 0, 1.0])   # gravity direction in your rest grip (board axes)
        self.accept_any_pose = False
        self.start_calibration()
 
    # ---------- calibration ----------
    def start_calibration(self):
        """Rest position = you holding the pen in your writing grip. One step: hold still
        for HOLD_SECONDS and the gyro bias AND the starting pose are taken from that."""
        self.stage = "hold"
        self.calibrated = False
        self._calib_time = 0.0
        self._best = None
        self._reset_window()
        self.status = "Calibrating: hold the pen still in your writing grip..."
 
    def _reset_window(self):
        self._n, self._t = 0, 0.0
        self._sum = np.zeros(6)
        self._sq = np.zeros(6)
 
    def pose_error(self, acc_board):
        """Angle to the raw data's start pose, plus elevation/roll, for an accel reading."""
        a = _unit(np.asarray(acc_board, float))
        s = 1.0 if a[1] >= 0 else -1.0       # the end that's up is the back of the pen
        up = board_to_pen_matrix(s) @ a
        ang = math.degrees(math.acos(max(-1, min(1, float(up @ self.ref_up)))))
        return ang, s, up
 
    def _pose_hints(self, up):
        elev, roll = pose_angles(up)
        hints = []
        if elev < self.ref_elev - 8:
            hints.append("raise the back end")
        elif elev > self.ref_elev + 8:
            hints.append("lower the back end")
        if roll < self.ref_roll - 12:
            hints.append("lift the right edge a bit")
        elif roll > self.ref_roll + 12:
            hints.append("lower the right edge a bit")
        return elev, roll, hints
 
    def _hold_step(self, dt, acc, gyr):
        row = np.concatenate([acc, gyr])
        self._n += 1
        self._t += dt
        self._sum += row
        self._sq += row * row
        self._calib_time += dt
        mean = self._sum / self._n
        spread = float(np.sqrt(np.maximum(self._sq[3:] / self._n - mean[3:] ** 2, 0)).max())
        ang, _s, up = self.pose_error(mean[:3])
        elev, roll, hints = self._pose_hints(up)
        pose_ok = ang <= POSE_TOL or not REQUIRE_POSE_MATCH or self.accept_any_pose
        if self._n > 5 and (spread > HAND_LIMIT or not pose_ok):     # moving or wrong grip: start over
            if pose_ok and (self._best is None or spread < self._best[0]):
                self._best = (spread, mean)
            self._reset_window()
        elif self._t >= HOLD_SECONDS:
            self._finish_hold(mean, spread)
            return
        if self._calib_time >= CALIB_TIMEOUT and self._best is not None and self._best[0] < 2 * HAND_LIMIT:
            self._finish_hold(self._best[1], self._best[0])
            return
        pose = (f"Grip is {ang:.0f} deg from the raw data's start (angle {elev:.0f}/{self.ref_elev:.0f}, "
                f"roll {roll:.0f}/{self.ref_roll:.0f})"
                + (f": {', '.join(hints)}" if hints and ang > POSE_TOL else ""))
        self.status = (f"Calibrating: hold the pen still in your writing grip... hand shake {spread:.1f} deg/s "
                       f"(want < {HAND_LIMIT:.0f}). {pose}" + ("  K = accept this grip" if REQUIRE_POSE_MATCH else ""))
 
    def _finish_hold(self, mean, spread):
        self.bias = mean[3:]
        self.acc_lp = mean[:3].copy()
        ang, s, up = self.pose_error(mean[:3])
        M = board_to_pen_matrix(s)
        self.to_pen = rotation_between(up, self.ref_up) @ M     # your grip becomes the raw data's start pose
        self.rest_up = _unit(mean[:3])
        self.acc_s = self.to_pen @ mean[:3]
        self.gyr_s = np.zeros(3)
        self.stage = "ready"
        self.calibrated = True
        end = "+Y" if s < 0 else "-Y"
        far = "" if ang <= POSE_TOL else " (quite different from the raw data's grip, see TIPS)"
        self.status = (f"Ready. Your grip = rest position, {ang:.0f} deg from the raw data's start{far}. "
                       f"Tip = board {end} end, gyro bias {np.round(self.bias, 1)} deg/s. SPACE = write")
 
    def rest_error(self, acc_board):
        """Angle between an accel reading and your calibrated rest grip."""
        a = _unit(np.asarray(acc_board, float))
        return math.degrees(math.acos(max(-1, min(1, float(a @ self.rest_up)))))
 
    # ---------- every sample ----------
    def update(self, dt, acc, gyr):
        acc = np.asarray(acc, float)
        gyr = np.asarray(gyr, float)
        self.samples += 1
        self.acc_lp = acc.copy() if self.acc_lp is None else self.acc_lp + 0.1 * (acc - self.acc_lp)
        if self.stage == "hold":
            self._hold_step(dt, acc, gyr)
            return
        self._check_gyro_sign(dt, gyr)
        # no integration: just low-pass the signals for display (the model filters separately)
        a_pen, g_pen = self.to_pen_axes(acc, gyr)
        g_pen = np.where(np.abs(g_pen) < GYRO_NOISE_DPS, 0.0, g_pen)
        self.acc_s = self.acc_s + LIVE_SMOOTH * (a_pen - self.acc_s)
        self.gyr_s = self.gyr_s + LIVE_SMOOTH * (g_pen - self.gyr_s)
 
    def _check_gyro_sign(self, dt, gyr):
        """Gravity seen by the accelerometer must turn the way the gyro says. If it turns the
        other way (gyro axes flipped in the library), flip the gyro. Decided once, from the
        first few seconds of slow, real rotation."""
        u = _unit(self.acc_lp)
        if self._u_prev is not None and self._gs[1] < 400 and dt > 0:
            w = np.radians(gyr - self.bias)
            if np.linalg.norm(w) > 0.3:
                du = (u - self._u_prev) / dt
                pred = -np.cross(w, u)
                self._gs += [du @ pred, pred @ pred, du @ du]
                if self._gs[1] >= 400:
                    corr = self._gs[0] / math.sqrt(self._gs[1] * self._gs[2] + 1e-12)
                    if corr < -0.2:
                        self.gyro_sign = -1.0
                        print(f"Gyro turns opposite to the accelerometer (corr {corr:.2f}): flipping the gyro sign.")
                    else:
                        print(f"Gyro and accelerometer agree (corr {corr:.2f}).")
        self._u_prev = u
 
    def to_pen_axes(self, acc, gyr):
        """Board accel (g) and raw gyro (deg/s) -> pen axes as in the raw data, bias removed."""
        acc = np.asarray(acc, float) @ self.to_pen.T
        gyr = ((np.asarray(gyr, float) - self.bias) * self.gyro_sign) @ self.to_pen.T
        return acc, gyr
 
 
# =====================================================================================
#  Prediction of one recording
# =====================================================================================
def predict_recording(model, acc_pen, gyr_pen):
    acc_t, gyr_t = trim_still(np.asarray(acc_pen), np.asarray(gyr_pen))
    feats = letter_features(acc_t, gyr_t)
    p = model.probs(feats)
    order = np.argsort(p)[::-1]
    nn_idx, nn_dist = model.nearest(feats)
    return {"top": [(model.classes[i], float(p[i])) for i in order[:5]],
            "nearest": [model.classes[model.knn_y[i]] for i in nn_idx],
            "nearest_idx": [int(i) for i in nn_idx],
            "feats": feats, "trimmed_len": len(gyr_t)}
 
 
# =====================================================================================
#  Window
# =====================================================================================
class Canvas:
    """Live window: smoothed accelerometer and gyro (pen axes) as scrolling traces, plus the
    predicted letter. Nothing is integrated: what you see is the filtered sensor signal."""
 
    def __init__(self, tracker, model):
        for k in list(plt.rcParams):
            if k.startswith("keymap."):
                plt.rcParams[k] = []
        self.t = tracker
        self.model = model
        self.label = None                      # letter the user says they're writing (optional)
        self.recordings = []
        self.rec = None
        self.frozen = None                     # last finished recording, shown until SPACE or C
        self.message = ""
        self.quit = False
        self.t0 = time.time()
        self._last_live = 0.0
        self.score = [0, 0]
        n = int(WINDOW_S * 100)
        self.hist_acc = deque(maxlen=n)        # smoothed, pen axes, rest gravity removed
        self.hist_gyr = deque(maxlen=n)
        plt.ion()
        self.fig, (self.ax_a, self.ax_g) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
        self.fig.subplots_adjust(top=0.80, right=0.80, hspace=0.12)
        colors = ("tab:red", "tab:green", "tab:blue")
        names = ("x (right)", "y (along pen)", "z (underside)")
        self.lines_a = [self.ax_a.plot([], [], color=c, lw=1.8, label=nm)[0] for c, nm in zip(colors, names)]
        self.lines_g = [self.ax_g.plot([], [], color=c, lw=1.8, label=nm)[0] for c, nm in zip(colors, names)]
        self.ax_a.set_ylabel("accel - rest gravity (g)")
        self.ax_g.set_ylabel("gyro (deg/s)")
        self.ax_g.set_xlabel("time (s)")
        for ax in (self.ax_a, self.ax_g):
            ax.grid(True, alpha=0.3)
            ax.axhline(0, color="0.5", lw=0.8)
        self.ax_a.legend(loc="upper left", fontsize=8, ncol=3)
        self.big = self.fig.text(0.90, 0.70, "", ha="center", va="center", fontsize=64,
                                 fontweight="bold", color="tab:purple")
        self.small = self.fig.text(0.90, 0.52, "", ha="center", va="top", fontsize=11, color="0.3")
        self.title = self.fig.suptitle(tracker.status, fontsize=9)
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.fig.canvas.mpl_connect("close_event", lambda e: setattr(self, "quit", True))
        plt.show(block=False)
 
    # ---------- keys ----------
    def on_key(self, event):
        key = event.key or ""
        if len(key) == 1 and "A" <= key <= "Z":
            self.label = key
            self.message = f"OK, next letters are '{key}' (for the score)."
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
                self.recordings.pop()
                self.message = f"Deleted the last recording ({len(self.recordings)} left)."
                self.clear_canvas()
        elif k == "c":
            self.clear_canvas()
        elif k == "b":
            self.rec = None
            self.clear_canvas()
            self.t.start_calibration()
            self.message = ""
        elif k == "k":
            if not self.t.calibrated:
                self.t.accept_any_pose = True
                self.message = "Taking your grip as it is."
        elif k == "q":
            self.quit = True
 
    def start_recording(self):
        if not self.t.calibrated:
            self.message = "Finish calibration first: hold the pen still in your grip."
            return
        self.rec = {"label": self.label, "t": [], "acc": [], "gyr": [], "acc_pen": [], "gyr_pen": [],
                    "acc_s": [], "gyr_s": []}
        self.clear_canvas()
        ang = self.t.rest_error(self.t.acc_lp)
        warn = f" Careful: you started {ang:.0f} deg away from your rest grip." if ang > START_WARN else ""
        self.message = f"WRITING... press SPACE when done.{warn}"
        self._last_live = time.time()
 
    def stop_recording(self):
        rec, self.rec = self.rec, None
        dur = rec["t"][-1] if rec["t"] else 0.0
        if dur < MIN_RECORD_S:
            self.message = f"Too short ({dur:.2f} s), not kept. SPACE to try again."
            return
        res = predict_recording(self.model, rec["acc_pen"], rec["gyr_pen"])
        rec["pred"] = res
        self.recordings.append(rec)
        self.frozen = rec
        (l1, p1), (l2, p2), (l3, p3) = res["top"][:3]
        self.show_prediction(res, final=True)
        score = ""
        if rec["label"]:
            self.score[0] += l1 == rec["label"]
            self.score[1] += 1
            score = f"  |  score {self.score[0]}/{self.score[1]}"
        self.message = (f"Predicted '{l1}' {p1:.0%}  (then {l2} {p2:.0%}, {l3} {p3:.0%}). "
                        f"Closest raw letters: {' '.join(res['nearest'])}{score}.  P = compare, SPACE = next")
        print(f"#{len(self.recordings)}: predicted {l1} ({p1:.0%}), {l2} ({p2:.0%}), {l3} ({p3:.0%})"
              + (f", you said {rec['label']}" if rec["label"] else ""))
 
    def show_prediction(self, res, final):
        (l1, p1), (l2, p2), (l3, p3) = res["top"][:3]
        self.big.set_text(l1)
        self.big.set_color("tab:purple" if final else "0.6")
        self.small.set_text(f"{p1:.0%}\n{l2} {p2:.0%}\n{l3} {p3:.0%}")
 
    def add_sample(self, dt, acc, gyr):
        """Called for every sample after tracker.update()."""
        if not self.t.calibrated:
            return
        a_s, g_s = self.t.acc_s - self.t.ref_up, self.t.gyr_s
        self.hist_acc.append(a_s)
        self.hist_gyr.append(g_s)
        if self.rec is None:
            return
        r = self.rec
        a_pen, g_pen = self.t.to_pen_axes(acc, gyr)
        r["t"].append((r["t"][-1] + dt) if r["t"] else 0.0)
        r["acc"].append(list(acc))
        r["gyr"].append(list(gyr))
        r["acc_pen"].append(a_pen)
        r["gyr_pen"].append(g_pen)
        r["acc_s"].append(a_s)
        r["gyr_s"].append(g_s)
 
    def live_predict(self):
        """While writing: guess from what's there so far."""
        r = self.rec
        if r is None or len(r["t"]) < 20 or time.time() - self._last_live < LIVE_PREDICT_EVERY:
            return
        self._last_live = time.time()
        self.show_prediction(predict_recording(self.model, r["acc_pen"], r["gyr_pen"]), final=False)
 
    def clear_canvas(self):
        self.frozen = None
        self.big.set_text("")
        self.small.set_text("")
 
    # ---------- plot / export ----------
    def plot_last(self):
        if not self.recordings:
            self.message = "Nothing recorded yet: SPACE, write, SPACE."
            return
        r = self.recordings[-1]
        res = r["pred"]
        best = res["top"][0][0]
        same = [i for i, l in zip(res["nearest_idx"], res["nearest"]) if l == best]
        if same:
            ref_i = same[0]
        else:
            cls = self.model.classes.index(best)
            cand = np.where(self.model.knn_y == cls)[0]
            x = normalise(res["feats"]).reshape(-1)
            ref_i = int(cand[np.argmin(((self.model.knn_x[cand] - x) ** 2).sum(1))])
        mine = normalise(res["feats"])
        ref = normalise(self.model.knn_raw[ref_i].astype(float))
        ref_lab = self.model.classes[self.model.knn_y[ref_i]]
        t = np.array(r["t"])
        fig = plt.figure(figsize=(14, 6))
        steps = np.arange(T_STEPS)
        colors = ("tab:red", "tab:green", "tab:blue")
        for k, (key, sl, name, unit) in enumerate([("acc_s", slice(0, 3), "Accelerometer", "g"),
                                                  ("gyr_s", slice(3, 6), "Gyro", "deg/s")]):
            ax = fig.add_subplot(2, 3, 1 + 3 * k)
            data = np.array(r[key])
            for j, c in enumerate(colors):
                ax.plot(t, data[:, j], color=c, lw=1.8, label="xyz"[j])
            ax.set_title(f"{name}, pen axes, smoothed ({unit})" + (" - rest gravity" if k == 0 else ""),
                         fontsize=8)
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=7, ncol=3, loc="upper right")
            ax = fig.add_subplot(2, 3, 2 + 3 * k)
            for j, c in enumerate(colors):
                ax.plot(steps, mine[:, sl][:, j], color=c, lw=2, label=f"you {'xyz'[j]}")
                ax.plot(steps, ref[:, sl][:, j], color=c, lw=1.2, ls="--", label=f"raw '{ref_lab}' {'xyz'[j]}")
            ax.set_title(f"{name}: what the model sees (solid = you, dashed = closest raw '{ref_lab}')",
                         fontsize=8)
            ax.grid(True, alpha=0.3)
            if k == 0:
                ax.legend(fontsize=6, ncol=2, loc="upper right")
        fig.axes[-2].set_xlabel("time (s)")
        fig.axes[-1].set_xlabel(f"time step (letter trimmed and stretched to {T_STEPS})")
        ax3 = fig.add_subplot(2, 3, (3, 6))
        labs = [l for l, _ in res["top"]][::-1]
        vals = [p for _, p in res["top"]][::-1]
        ax3.barh(labs, vals, color=["tab:purple" if l == best else "0.6" for l in labs])
        ax3.set_xlim(0, 1)
        ax3.set_title("Top 5 letters", fontsize=9)
        ax3.set_xlabel("probability")
        said = f"you said '{r['label']}', " if r["label"] else ""
        fig.suptitle(f"Recording #{len(self.recordings)}: {said}predicted '{best}'.  Closest raw letters: "
                     f"{' '.join(res['nearest'])}   (model: {self.model.test_acc:.0%} on unseen raw-data writers)",
                     fontsize=10)
        fig.tight_layout()
        plt.show(block=False)
        self.message = f"Plotted recording #{len(self.recordings)}."
 
    def export(self):
        if not self.recordings:
            self.message = "Nothing to export yet."
            return
        out = []
        for i, r in enumerate(self.recordings):
            acc_raw, gyr_raw = pen_to_raw(r["acc_pen"], r["gyr_pen"])
            out.append({"index": i, "label": r["label"], "predicted": r["pred"]["top"],
                        "nearest_raw": r["pred"]["nearest"], "t": r["t"],
                        "acc_g": r["acc"], "gyro_dps": r["gyr"],
                        "acc_pen_smoothed_g": np.round(r["acc_s"], 4).tolist(),
                        "gyro_pen_smoothed_dps": np.round(r["gyr_s"], 2).tolist(),
                        "raw_style_note": "acc_counts/gyro_counts are in the raw data's pen axes and counts",
                        "acc_counts": np.round(acc_raw).tolist(), "gyro_counts": np.round(gyr_raw).tolist()})
        path = os.path.join(HERE, f"predictions_{time.strftime('%Y%m%d_%H%M%S')}.json")
        with open(path, "w") as f:
            json.dump(out, f)
        print(f"Exported {len(out)} recordings to {path}")
        self.message = f"Exported {len(out)} recordings to {os.path.basename(path)}"
 
    # ---------- screen ----------
    def redraw(self):
        if self.rec is not None:
            self.live_predict()
            acc, gyr = self.rec["acc_s"], self.rec["gyr_s"]
        elif self.frozen is not None:
            acc, gyr = self.frozen["acc_s"], self.frozen["gyr_s"]
        else:
            acc, gyr = list(self.hist_acc), list(self.hist_gyr)
        if acc:
            acc, gyr = np.array(acc), np.array(gyr)
            tt = np.arange(len(acc)) * 0.01
            for j in range(3):
                self.lines_a[j].set_data(tt, acc[:, j])
                self.lines_g[j].set_data(tt, gyr[:, j])
            xmax = max(WINDOW_S, tt[-1]) if self.rec is None and self.frozen is None else max(1.0, tt[-1])
            for ax, d, floor in ((self.ax_a, acc, 0.2), (self.ax_g, gyr, 30.0)):
                lim = max(floor, float(np.abs(d).max()) * 1.1)
                ax.set_ylim(-lim, lim)
            self.ax_g.set_xlim(0, xmax)
        else:
            for ln in self.lines_a + self.lines_g:
                ln.set_data([], [])
        rec_color = "mistyrose" if self.rec is not None else "white"
        self.ax_a.set_facecolor(rec_color)
        self.ax_g.set_facecolor(rec_color)
        if self.t.samples == 0 and time.time() - self.t0 > 2:
            self.t.status = ("No data from the Nano yet. Is another program (live_draw.py, Serial Monitor) "
                             "using it? Restart the kernel with Ctrl+.")
        if self.t.calibrated:
            ang = self.t.rest_error(self.t.acc_lp) if self.t.acc_lp is not None else 0
            lab = f"writing '{self.label}'" if self.label else "Shift+letter = say what you'll write"
            line1 = f"{len(self.recordings)} letters, {lab}. Pen {ang:.0f} deg from your rest grip"
        else:
            line1 = self.t.status
        line2 = self.message or ("SPACE = write a letter" if self.t.calibrated else "")
        self.title.set_text(_wrap(line1, 120) + "\n" + _wrap(line2, 120))
        plt.pause(0.001)
 
 
def _wrap(s, width=95):
    words, lines, cur = s.split(" "), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    return "\n".join(lines + [cur])
 
 
# =====================================================================================
#  Data loops (same as live_draw.py)
# =====================================================================================
def run_usb(port, model):
    ser = open_port(port)
    tracker = PenTracker(model.ref_up)
    canvas = Canvas(tracker, model)
    last_ms = None
    last_draw = 0.0
    try:
        ser.reset_input_buffer()
        print(f"Connected over USB on {port}. Hold the pen still in your writing grip...")
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
                if not 0 < dt < 0.2:
                    continue
                tracker.update(dt, v[1:4], v[4:7])
                canvas.add_sample(dt, v[1:4], v[4:7])
            now = time.time()
            if now - last_draw > 1 / FPS:
                canvas.redraw()
                last_draw = now
            else:
                time.sleep(0.002)
    finally:
        ser.close()
        builtins._magic_wand_serial = None
        plt.close(canvas.fig)
        print("Stopped. COM port released, you can run again.")
 
 
async def run_ble(model):
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
 
    tracker = PenTracker(model.ref_up)
    canvas = Canvas(tracker, model)
    last_seq = None
    async with BleakClient(device) as client:
        await client.start_notify(CHAR_UUID, on_data)
        print("Connected over Bluetooth. Hold the pen still in your writing grip...")
        while client.is_connected and not canvas.quit and plt.fignum_exists(canvas.fig.number):
            while samples:
                seq, acc, gyr = samples.popleft()
                steps = 1 if last_seq is None else (seq - last_seq) % 256
                last_seq = seq
                if not 0 < steps < 20:
                    continue
                tracker.update(0.01 * steps, acc, gyr)
                canvas.add_sample(0.01 * steps, acc, gyr)
            canvas.redraw()
            await asyncio.sleep(1 / FPS)
    print("Disconnected.")
 
 
async def main():
    plt.close("all")
    model = LetterModel.load()
    print(f"Letter model ready: {len(model.classes)} letters, {model.test_acc:.0%} on unseen raw-data writers.")
    port = find_usb_port()
    if port is not None:
        try:
            run_usb(port, model)
        except KeyboardInterrupt:
            pass
        except serial.SerialException as e:
            print(f"Found the Nano on {port} but couldn't open it ({e}).\n"
                  "Something else still has the port: stop live_draw.py / close its plot window, "
                  "close the Arduino Serial Monitor/Plotter, or restart the Spyder kernel (Ctrl+.).")
        return
    await run_ble(model)
 
 
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
 