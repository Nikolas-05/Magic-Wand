"""
live_predict.py - record a letter with live_draw's UI, classify it with the OnHW CNN.

Usage: python live_predict.py   (train_onhw_cv.py, live_draw.py and the .pt file in same folder)
Keys are the same as live_draw.py: Shift+letter sets the TRUE label, SPACE start/stop
recording. On stop, the model predicts and the title shows the top 3 + running accuracy.
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
import numpy as np
import torch
import itertools

import live_draw
from model import CNN, resample

CKPT = "onhw_both_merged_acc2_gyro.pt"

# ---- live-sensor -> dataset-sensor mapping (the part you will have to tune) ----
ACC_SCALE = 4096.0                 # multiply live accel (g) to match the dataset's units
GYRO_SCALE = 57.0                # multiply live gyro (deg/s, bias removed) likewise
PERM = [2, 0, 1, 5, 3, 4]
SIGN = np.array([-1, 1, -1, -1, 1, -1], dtype=np.float32)   # same rotation for accel and gyro

ck = torch.load(CKPT, map_location="cpu", weights_only=False)
CLASSES, MEAN, STD = ck["classes"], np.asarray(ck["mean"]), np.asarray(ck["std"])
STEPS, MERGE = ck["steps"], ck.get("merge", {})
model = CNN(len(ck["cols"]), len(CLASSES), width=ck["width"])
model.load_state_dict(ck["model"])
model.eval()
print(f"Loaded {CKPT}: {len(CLASSES)} classes, merges: {MERGE}")


def classify(acc, gyr):
    """acc (N,3) in g, gyr (N,3) in deg/s with bias removed -> (top3 list, raw feature std)."""
    x = np.concatenate([acc * ACC_SCALE, gyr * GYRO_SCALE], axis=1)[:, PERM] * SIGN
    x_raw_mean = x.mean(0)
    x = resample(x, STEPS)                              # same 64-step resample as training
    raw_std = x.std(0)
    x = ((x - MEAN) / STD).astype(np.float32)
    with torch.no_grad():
        p = torch.softmax(model(torch.from_numpy(x)[None]), 1)[0].numpy()
    top = np.argsort(p)[::-1][:3]
    return [(CLASSES[i], float(p[i])) for i in top], raw_std, x_raw_mean

SP = [(p, s) for p in itertools.permutations(range(3))
      for s in itertools.product([1, -1], repeat=3)]       # 48 signed axis orders


def _rotations():
    out = []
    for p in itertools.permutations(range(3)):
        for s in itertools.product([1, -1], repeat=3):
            M = np.zeros((3, 3))
            for i in range(3):
                M[i, p[i]] = s[i]
            if round(np.linalg.det(M)) == 1:        # proper rotations only
                out.append((list(p), list(s)))
    return out

ROTS = _rotations()                                  # 24 of them


def sweep(recordings, bias):
    X, truths = [], []
    for r in recordings:
        acc = np.array(r["acc"]) * ACC_SCALE
        gyr = (np.array(r["gyr"]) - bias) * GYRO_SCALE
        X.append(resample(np.concatenate([acc, gyr], 1), STEPS))
        truths.append(CLASSES.index(MERGE.get(r["label"], r["label"])))
    X, truths = np.stack(X), np.array(truths)
    rows = np.arange(len(truths))
    results = []
    for p, s in ROTS:
        sg = np.array(s, dtype=np.float32)
        a = X[:, :, :3][:, :, p] * sg
        g = X[:, :, 3:][:, :, p] * sg
        x = ((np.concatenate([a, g], 2) - MEAN) / STD).astype(np.float32)
        with torch.no_grad():
            pr = torch.softmax(model(torch.from_numpy(x)), 1).numpy()
        results.append((float(np.log(pr[rows, truths] + 1e-9).mean()),
                        float((pr.argmax(1) == truths).mean()),
                        p + [3 + i for i in p], s + s))
    results.sort(key=lambda t: -t[0])
    print(f"\nSweep over {len(truths)} recordings, {len(results)} rotations:")
    for score, acc, perm, sign in results[:5]:
        print(f"  logp {score:6.2f}  acc {acc:.2f}   PERM = {perm}   SIGN = {sign}")


class PredictCanvas(live_draw.Canvas):
    def __init__(self, tracker):
        super().__init__(tracker)
        self.hits = self.total = 0

    def stop_recording(self):
        n = len(self.recordings)
        super().stop_recording()                        # saves the recording (or discards if too short)
        if len(self.recordings) == n:
            return
        r = self.recordings[-1]
        top, raw_std, x_raw_mean = classify(np.array(r["acc"]), np.array(r["gyr"]) - self.t.bias)        
        truth = MERGE.get(r["label"], r["label"])       # true label mapped through the merge list
        self.total += 1
        self.hits += top[0][0] == truth
        guess = ", ".join(f"{c} {100*p:.0f}%" for c, p in top)
        self.message = (f"true '{r['label']}' -> predicted: {guess}   "
                        f"[{self.hits}/{self.total} correct]")
        print(self.message)
        print("   live feature std :", np.round(raw_std, 3))
        print("   training std     :", np.round(STD, 3), "  <- compare scales")
        print("   training mean    :", np.round(MEAN, 1))
        print("   live mean (scaled):", np.round(x_raw_mean, 1))
        
    def on_key(self, event):
        if (event.key or "") == "g":
            if len(self.recordings) < 6:
                self.message = "Record at least 6 letters first (2-3 different letters)."
            else:
                sweep(self.recordings, self.t.bias)
                self.message = "Sweep done, see console."
        else:
            super().on_key(event)
        


if __name__ == "__main__":
    import matplotlib.pyplot as plt
    live_draw.Canvas = PredictCanvas          # run_usb now builds our canvas
    plt.close("all")
    port = live_draw.find_usb_port()
    if port is None:
        print("No Nano found on USB. For Bluetooth, run from a terminal instead.")
    else:
        live_draw.run_usb(port)