"""
OnHW-chars writer-independent 5-fold training (Acc2 + Gyro only; magnetometer,
front accelerometer and force are ignored), with a MERGE LIST that collapses
upper/lowercase pairs the pen can't tell apart (and I/l) into one class.

Merged letters are predicted as the lowercase form; restore case afterwards in
post-processing (sentence starts, standalone "I", dictionary / language model).

Run:  python train_onhw_cv.py
"""
import csv
import os
from collections import Counter

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader

# ------------------------------------------------------------------ config
ROOT = r'C:\Users\lando\Magic-Wand\onhw-chars_2021-06-30\onhw-chars_2021-06-30'
MODE = "both"                      # keep "both": the merge list is built for the combined letters
FOLDS = [0, 1, 2, 3, 4]            # writer-independent folds (use [0] for a quick test)
EPOCHS, BATCH, LR = 60, 64, 1e-3
WIDTH = 128                        # conv filters per layer (paper used 64)
STEPS = 64                         # every sample is resampled to this length

# Assumed column order: Acc1(0-2) Acc2(3-5) Gyro(6-8) Mag(9-11) Force(12)
COLS = list(range(3, 9))           # Acc2 + Gyro only

# ---- merge list --------------------------------------------------------
# "default": the pairs from your own results (top mistakes) plus U from the paper
# "auto"   : rebuild the list from confusion_both.csv (your earlier run's output)
# "none"   : no merging (all 52 classes)
MERGE_SOURCE = "default"
AUTO_THRESHOLD = 0.15              # auto mode: merge a pair if either direction is confused > 15%
CONFUSION_CSV = "confusion_both.csv"

# merged classes are labeled with the lowercase letter
DEFAULT_MERGE = {c.upper(): c for c in "ckopsuvwxyz"}
DEFAULT_MERGE["I"] = "l"           # capital i vs lowercase L: written almost identically

SEED = 0
device = "cuda" if torch.cuda.is_available() else "cpu"


def build_merge():
    if MERGE_SOURCE == "none":
        return {}
    if MERGE_SOURCE == "auto":
        if not os.path.exists(CONFUSION_CSV):
            print(f"[merge] {CONFUSION_CSV} not found, falling back to the default list")
            return dict(DEFAULT_MERGE)
        with open(CONFUSION_CSV) as f:
            rows = list(csv.reader(f))
        labels = rows[0][1:]
        cm = np.array([[int(v) for v in r[1:]] for r in rows[1:]], dtype=float)
        rate = cm / np.maximum(cm.sum(1, keepdims=True), 1)
        idx = {c: i for i, c in enumerate(labels)}
        merge = {}
        for c in labels:
            if c.isupper() and c.lower() in idx:
                a, b = idx[c], idx[c.lower()]
                if max(rate[a, b], rate[b, a]) > AUTO_THRESHOLD:
                    merge[c] = c.lower()
        if "I" in idx and "l" in idx:
            if max(rate[idx["I"], idx["l"]], rate[idx["l"], idx["I"]]) > AUTO_THRESHOLD:
                merge["I"] = "l"
        return merge
    return dict(DEFAULT_MERGE)


MERGE = build_merge()


# ------------------------------------------------------------------ data
def resample(x, n=STEPS):
    x = np.asarray(x, dtype=np.float32)
    t_old = np.linspace(0, 1, len(x))
    t_new = np.linspace(0, 1, n)
    out = np.stack([np.interp(t_new, t_old, x[:, c]) for c in range(x.shape[1])], axis=1)
    return out.astype(np.float32)          # np.interp returns float64; the model needs float32


def load(fold, part, cols):
    folder = rf"{ROOT}\onhw2_{MODE}_indep_{fold}"
    X = np.load(rf"{folder}\X_{part}.npy", allow_pickle=True)
    y = np.load(rf"{folder}\y_{part}.npy", allow_pickle=True)
    Xs, ys, skipped = [], [], 0
    for x, label in zip(X, y):
        x = np.asarray(x, dtype=np.float32)
        if x.ndim != 2 or len(x) < 2:      # empty or malformed recording
            skipped += 1
            continue
        Xs.append(resample(x[:, cols]))
        label = str(label)
        ys.append(MERGE.get(label, label))  # apply the merge list
    if skipped:
        print(f"    [{part} fold {fold}] skipped {skipped} empty/malformed samples")
    return np.stack(Xs), ys                # X: (N, 64, C), y: list of letters


# ------------------------------------------------------------------ model
class CNN(nn.Module):
    def __init__(self, n_in, n_cls, width=WIDTH):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(n_in, width, 4), nn.ReLU(), nn.BatchNorm1d(width), nn.MaxPool1d(2), nn.Dropout(0.4),
            nn.Conv1d(width, width, 4), nn.ReLU(), nn.BatchNorm1d(width), nn.MaxPool1d(2), nn.Dropout(0.4),
            nn.Flatten(),                                  # width ch * 13 steps for STEPS=64
            nn.Linear(width * 13, 100), nn.ReLU(), nn.Dropout(0.4),
            nn.Linear(100, n_cls),
        )

    def forward(self, x):                                  # x: (B, 64, C)
        return self.net(x.transpose(1, 2))


def predict(model, dl):
    model.eval()
    preds = []
    with torch.no_grad():
        for xb, _ in dl:
            preds.append(model(xb.to(device)).argmax(1).cpu())
    return torch.cat(preds).numpy()


def accuracy(model, dl, y_true):
    return float((predict(model, dl) == y_true).mean())


# ------------------------------------------------------------------ one fold
def run_fold(fold, cols):
    Xtr, ytr = load(fold, "train", cols)
    Xte, yte = load(fold, "test", cols)

    # normalize with TRAIN statistics only
    mean = Xtr.reshape(-1, Xtr.shape[-1]).mean(0)
    std = Xtr.reshape(-1, Xtr.shape[-1]).std(0) + 1e-8
    Xtr, Xte = (Xtr - mean) / std, (Xte - mean) / std

    classes = sorted(set(ytr))
    cid = {c: i for i, c in enumerate(classes)}
    assert set(yte) <= set(classes), "test set has letters missing from train"
    ytr_i = np.array([cid[c] for c in ytr])
    yte_i = np.array([cid[c] for c in yte])

    train_dl = DataLoader(TensorDataset(torch.from_numpy(Xtr), torch.from_numpy(ytr_i)), BATCH, shuffle=True)
    train_eval_dl = DataLoader(TensorDataset(torch.from_numpy(Xtr), torch.from_numpy(ytr_i)), 512)
    test_dl = DataLoader(TensorDataset(torch.from_numpy(Xte), torch.from_numpy(yte_i)), 512)

    torch.manual_seed(SEED + fold)
    model = CNN(Xtr.shape[-1], len(classes)).to(device)
    opt = torch.optim.Adam(model.parameters(), LR)
    loss_fn = nn.CrossEntropyLoss()

    for epoch in range(EPOCHS):
        model.train()
        for xb, yb in train_dl:
            opt.zero_grad()
            loss_fn(model(xb.to(device)), yb.to(device)).backward()
            opt.step()
        if (epoch + 1) % 10 == 0:
            print(f"    fold {fold} epoch {epoch+1:03d}  "
                  f"train {accuracy(model, train_eval_dl, ytr_i):.3f}  "
                  f"test {accuracy(model, test_dl, yte_i):.3f}")

    # Report the FINAL epoch (don't pick the best epoch on the test set).
    pred_i = predict(model, test_dl)
    true_letters = [classes[i] for i in yte_i]
    pred_letters = [classes[i] for i in pred_i]
    acc = float((pred_i == yte_i).mean())
    acc_nocase = float(np.mean([t.lower() == p.lower() for t, p in zip(true_letters, pred_letters)]))
    return acc, acc_nocase, true_letters, pred_letters, model, classes, mean, std


# ------------------------------------------------------------------ main
if __name__ == "__main__":
    print("device:", device, "| mode:", MODE, "| channels:", COLS, "| epochs:", EPOCHS, "| width:", WIDTH)
    print(f"merge source: {MERGE_SOURCE} | {len(MERGE)} merges:")
    print("  " + ", ".join(f"{k}->{v}" for k, v in sorted(MERGE.items())))

    accs, accs_nocase = [], []
    all_true, all_pred = [], []

    for fold in FOLDS:
        acc, acc_nc, t, p, model, classes, mean, std = run_fold(fold, COLS)
        accs.append(acc)
        accs_nocase.append(acc_nc)
        all_true += t
        all_pred += p
        print(f"  fold {fold}: test acc {acc:.4f}  (fully case-insensitive: {acc_nc:.4f})")

    print(f"\n=== 5-fold writer-independent summary (acc2+gyro, {len(classes)} classes after merging) ===")
    print(f"merged-class accuracy : {100*np.mean(accs):5.2f}% +/- {100*np.std(accs):4.2f}")
    print(f"fully case-insensitive: {100*np.mean(accs_nocase):5.2f}% +/- {100*np.std(accs_nocase):4.2f}")
    print("Reference: unmerged run was 65.99% exact / 78.58% case-insensitive")

    # ---- most common mistakes, pooled over all folds
    class_totals = Counter(all_true)
    errors = Counter((t, p) for t, p in zip(all_true, all_pred) if t != p)
    print("\nMost common mistakes (true -> predicted):")
    for (t, p), n in errors.most_common(15):
        print(f"  {t} -> {p}: {n:4d}  ({100*n/class_totals[t]:4.1f}% of all '{t}')")

    # ---- full confusion matrix to CSV (separate file, doesn't overwrite the unmerged one)
    labels = sorted(set(all_true) | set(all_pred))
    idx = {c: i for i, c in enumerate(labels)}
    cm = np.zeros((len(labels), len(labels)), dtype=int)
    for t, p in zip(all_true, all_pred):
        cm[idx[t], idx[p]] += 1
    cm_path = f"confusion_{MODE}_merged.csv"
    with open(cm_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["true\\pred"] + labels)
        for c, row in zip(labels, cm):
            w.writerow([c] + list(row))
    print(f"\nSaved confusion matrix (rows = true letter) to {cm_path}")

    # ---- save the last fold's model + preprocessing + merge map
    torch.save({"model": model.state_dict(), "classes": classes, "mean": mean, "std": std,
                "cols": COLS, "steps": STEPS, "width": WIDTH, "merge": MERGE},
               f"onhw_{MODE}_merged_acc2_gyro.pt")
    print(f"Saved model to onhw_{MODE}_merged_acc2_gyro.pt")