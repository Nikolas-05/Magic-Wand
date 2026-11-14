#!/usr/bin/env python3
"""
integration.py - record labeled air-writing letters from the "Nano33-IMU" board
(Arduino Nano 33 BLE Rev2) over Bluetooth, using:

  * "test data.py"          for the connection settings (board name, characteristic
                            UUID, packet format "<Ifff" = t_ms, ax, ay, az)
  * recorder/pen_recorder.py for the recording session, letter segmentation,
                            saving (data/raw/<writer>/<LETTER>/...csv + data/index.csv),
                            export and plotting

Neither file is changed. "test data.py" is read as text (its settings are pulled out
without running it, because running it would start its own logger), and
pen_recorder.py is imported and handed a Bluetooth source that speaks this board's
packets instead of the MagicWandPen firmware's.

Usage (from the Magic-Wand folder, in Anaconda Prompt)
  python integration.py live                          check values are arriving
  python integration.py view                          live plot of the pen moving
  python integration.py record --writer nikolas       guided A-Z session
  python integration.py record --writer nikolas --letters ABC --reps 5
  python integration.py export                        build training CSV/JSON
  python integration.py plot data/raw/nikolas/A/A_....csv

Triggers for `record` (how the start/end of a letter is found)
  --trigger key      press SPACE to start a letter, SPACE again to stop (default)
  --trigger motion   starts when the pen moves, stops after it is still for 0.4 s
(The `button` trigger from pen_recorder.py is not available: this board has no button.)

If the board runs compare_letter/imu_ble_stream_gyro.ino instead of imu_ble_stream.ino,
the gyro characteristic is used automatically, so files also get gyro columns.
"""

import argparse
import ast
import asyncio
import math
# import string   # only used by the recording commands
import struct
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "recorder"))
import pen_recorder as pr  # noqa: E402  (recorder/pen_recorder.py, unchanged)

# Settings used when the script is run with no arguments (e.g. the green Run button
# in Spyder). Change these to taste.
# DEFAULT_ARGS = ["record", "--writer", "nikolas", "--trigger", "key"]
DEFAULT_ARGS = ["view"]   # live view only, for now

RATE_HZ = 100   # the BMI270 accel runs at ~100 Hz with the Arduino_BMI270_BMM150 library

# Optional second characteristic from compare_letter/imu_ble_stream_gyro.ino:
# uint32 t_ms, int16 ax, ay, az (milli-g), int16 gx, gy, gz (0.1 deg/s)
IMU6_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214"
IMU6_STRUCT = struct.Struct("<I6h")


# --------------------------------------------------------------------------
# Connection settings, read from "test data.py" without running it
# --------------------------------------------------------------------------
def load_test_data_settings(path=HERE / "test data.py"):
    settings = {"DEVICE_NAME": "Nano33-IMU",
                "CHAR_UUID": "19b10001-e8f2-537e-4f6c-d104768a1214",
                "PACKET_FMT": "<Ifff"}
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as e:
        print(f"Note: could not read {path.name} ({e}); using the default settings.")
        return settings
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in settings:
                    settings[t.id] = node.value.value
    return settings


SETTINGS = load_test_data_settings()
PACKET = struct.Struct(SETTINGS["PACKET_FMT"])


# --------------------------------------------------------------------------
# A pen_recorder Source for the Nano33-IMU board
# --------------------------------------------------------------------------
class Nano33Source(pr.Source):
    """
    Connects like "test data.py" (scan by name, subscribe to CHAR_UUID, unpack <Ifff)
    and turns each packet into the 12-value row pen_recorder.py expects:
      [t_s, ax, ay, az, gx, gy, gz, mx, my, mz, btn, force]
    Values the board doesn't send (gyro unless the gyro sketch is running,
    magnetometer, button, force) are 0.
    """

    def __init__(self, rate=RATE_HZ, address=None):
        super().__init__(rate)
        try:
            import bleak  # noqa: F401
        except ImportError:
            sys.exit("Bluetooth needs the bleak package:  pip install bleak")
        self.address = address
        self.ready = threading.Event()
        self.has_gyro = False

    def start(self):
        super().start()                       # runs _run in a background thread
        if not self.ready.wait(30):
            sys.exit(f"Could not connect over Bluetooth. {self.status}")
        print(self.status)

    def _run(self):
        # A fresh event loop in this thread, so this also works inside Spyder/IPython
        # (whose own loop is already running) without nest_asyncio.
        try:
            asyncio.run(self._main())
        except Exception as e:
            self.status = f"Bluetooth error: {e}"

    async def _main(self):
        from bleak import BleakClient, BleakScanner
        name = SETTINGS["DEVICE_NAME"]
        dev = self.address
        if dev is None:
            print(f"Scanning for '{name}' ...")
            dev = await BleakScanner.find_device_by_name(name, timeout=15)
            if dev is None:
                self.status = ("Device not found. Is the board powered and advertising, "
                               "and not connected to another program?")
                return

        state = {"t0": None, "last": None}

        def emit(t_ms, ax, ay, az, gx=0.0, gy=0.0, gz=0.0):
            if state["t0"] is None:
                state["t0"] = t_ms
            last = state["last"]
            if last is not None and t_ms - last > 1.5 * 1000.0 / self.rate:
                self.dropped += int(round((t_ms - last) * self.rate / 1000.0)) - 1
            state["last"] = t_ms
            self._put([(t_ms - state["t0"]) / 1000.0, ax, ay, az, gx, gy, gz,
                       0.0, 0.0, 0.0, 0.0, 0.0])

        def on_accel(_, data: bytearray):
            if len(data) >= PACKET.size:
                t_ms, ax, ay, az = PACKET.unpack(bytes(data[:PACKET.size]))[:4]
                emit(t_ms, ax, ay, az)

        def on_imu6(_, data: bytearray):
            if len(data) >= IMU6_STRUCT.size:
                t_ms, ax, ay, az, gx, gy, gz = IMU6_STRUCT.unpack(bytes(data[:IMU6_STRUCT.size]))
                emit(t_ms, ax / 1000.0, ay / 1000.0, az / 1000.0, gx / 10.0, gy / 10.0, gz / 10.0)

        async with BleakClient(dev) as client:
            uuids = {c.uuid.lower() for s in client.services for c in s.characteristics}
            if IMU6_UUID in uuids:
                self.has_gyro = True
                await client.start_notify(IMU6_UUID, on_imu6)
                what = "accel + gyro"
            else:
                await client.start_notify(SETTINGS["CHAR_UUID"], on_accel)
                what = "accel only"
            self.status = f"Connected to {name} ({getattr(dev, 'address', dev)}), {what}."
            self.ready.set()
            while not self.stop_flag.is_set() and client.is_connected:
                await asyncio.sleep(0.1)
            if not client.is_connected:
                self.status = "Bluetooth error: board disconnected"


# # --------------------------------------------------------------------------
# # Motion trigger that also works with accel only
# # --------------------------------------------------------------------------
# class AccelMotionSegmenter(pr.Segmenter):
#     """
#     Starts a letter when the pen moves and ends it after the pen is still for still_s.
#     "Movement" is how far the acceleration is from its recent average (a 0.2 s
#     low-pass), so holding the pen tilted counts as still. Uses the gyro as well when
#     the board sends it.
#     """

#     def __init__(self, rate, start_g=0.12, still_g=0.04, start_dps=60.0, still_dps=25.0,
#                  still_s=0.4, **kw):
#         super().__init__(rate, pre_s=0.2, **kw)
#         self.start_g, self.still_g = start_g, still_g
#         self.start_dps, self.still_dps = start_dps, still_dps
#         self.still_n = int(still_s * rate)
#         self.alpha = 1.0 / (0.2 * rate)
#         self.avg = None
#         self.quiet = 0

#     def update(self, row, key_toggle):
#         a = row[1:4]
#         if self.avg is None:
#             self.avg = list(a)
#         dev = math.sqrt(sum((a[k] - self.avg[k]) ** 2 for k in range(3)))
#         self.avg = [self.avg[k] + self.alpha * (a[k] - self.avg[k]) for k in range(3)]
#         w = math.sqrt(row[4] ** 2 + row[5] ** 2 + row[6] ** 2)
#         if not self.active:
#             if dev > self.start_g or w > self.start_dps:
#                 self._begin()
#                 self.quiet = 0
#             return None
#         self.quiet = self.quiet + 1 if (dev < self.still_g and w < self.still_dps) else 0
#         if self.quiet >= self.still_n:
#             seg = self._end()
#             return seg[:-self.still_n] if seg and len(seg) - self.still_n >= self.min_n else []
#         return None


# --------------------------------------------------------------------------
# Live view: a dot on a plain white plot that follows the pen as you move it
# --------------------------------------------------------------------------
CAL_FILE = HERE / "calibration.json"

# The six movement signals the board gives us (all in degrees, relative to a zero point):
#   tilt_x/y/z: how the direction of gravity has changed (accelerometer; sees tilting)
#   gyro_x/y/z: rotation angle since the zero point (gyro; 0 without the gyro sketch)
SIGNALS = ["tilt_x", "tilt_y", "tilt_z", "gyro_x", "gyro_y", "gyro_z"]

# Used until you calibrate: left/right = tilt_y, up/down = -tilt_x
DEFAULT_CAL = {"horizontal": {"signal": "tilt_y", "sign": 1, "gain": 1.0},
               "vertical": {"signal": "tilt_x", "sign": -1, "gain": 1.0}}


def load_calibration():
    import json
    try:
        cal = json.loads(CAL_FILE.read_text())
        for k in ("horizontal", "vertical"):
            assert cal[k]["signal"] in SIGNALS
        return cal
    except Exception:
        return None


def save_calibration(cal):
    import json
    CAL_FILE.write_text(json.dumps(cal, indent=2))


def pick_axis(samples, exclude=()):
    """
    samples: list of 6-value signal rows recorded while the person moved in one
    direction pair (e.g. UP then DOWN, starting with UP). Returns the signal that moved
    the most, the sign that makes the first movement positive, a gain, and the ranges.
    """
    ranges = [max(s[i] for s in samples) - min(s[i] for s in samples) for i in range(6)]
    order = sorted((i for i in range(6) if SIGNALS[i] not in exclude), key=lambda i: -ranges[i])
    best = order[0]
    series = [s[best] for s in samples]
    peak = max(abs(v) for v in series) or 1.0
    first = next((v for v in series if abs(v) > 0.3 * peak), series[-1])
    sign = 1 if first >= 0 else -1
    # gain: scale so a typical stroke of this size spans about half the plot
    gain = 1.0 if ranges[best] < 1e-6 else max(0.25, min(8.0, 40.0 / ranges[best]))
    return SIGNALS[best], sign, gain, ranges


def cmd_view(args):
    """
    Live plot of the pen's movement, with a guided calibration so the plot moves the
    same way your hand does.

    Calibration (runs on the first start, or with --calibrate, or press K before SPACE):
      1/3  hold the pen still in your writing position, press SPACE
      2/3  move UP then DOWN a few times (start with UP), press SPACE
      3/3  move RIGHT then LEFT a few times (start with RIGHT), press SPACE
    The result is saved to calibration.json and used every time after that.

    Then, in the plot window:
      SPACE (1st) = zero everything at the current position and start drawing
      SPACE (2nd) = stop and close      c = clear trail      k = calibrate again
    """
    import collections
    import matplotlib
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    if "inline" in matplotlib.get_backend().lower():      # Spyder's inline plots can't animate
        for b in ("QtAgg", "TkAgg"):
            try:
                plt.switch_backend(b)
                break
            except Exception:
                pass

    # src = pr.open_source(args)
    src = Nano33Source(RATE_HZ, args.address)
    src.start()

    cal = None if args.calibrate else load_calibration()
    n_trail = int(args.trail * RATE_HZ)
    xs, ys = collections.deque(maxlen=n_trail), collections.deque(maxlen=n_trail)
    st = {"phase": "cal_still" if cal is None else "wait", "cal": cal or dict(DEFAULT_CAL),
          "lp": None, "ang": [0.0, 0.0, 0.0], "last_t": None, "sig": None,
          "zero": None, "x": 0.0, "y": 0.0, "rec": [], "note": ""}

    PROMPTS = {
        "cal_still": "Calibration 1/3: hold the pen still where you start writing,\nthen press SPACE",
        "cal_ud": "Calibration 2/3: move UP, then DOWN, 3-4 times\n(start with UP), then press SPACE",
        "cal_lr": "Calibration 3/3: move RIGHT, then LEFT, 3-4 times\n(start with RIGHT), then press SPACE",
        "wait": "Hold the pen at its starting position, then press SPACE\n(k = calibrate again)",
        "run": "Drawing... press SPACE to stop",
    }

    fig, ax = plt.subplots(figsize=(7, 7), facecolor="white")
    ax.set_facecolor("white")
    ax.set_xlim(-args.range, args.range)
    ax.set_ylim(-args.range, args.range)
    ax.set_aspect("equal")
    ax.set_xlabel("left / right")
    ax.set_ylabel("down / up")
    title = ax.set_title(PROMPTS[st["phase"]])
    trail, = ax.plot([], [], "-", color="tab:blue", lw=2)
    dot, = ax.plot([], [], "o", color="tab:red", ms=10)
    info = ax.text(0.02, 0.98, "", transform=ax.transAxes, va="top", fontsize=9, family="monospace")

    def update_signals(r):
        """Update the 6 movement signals from one row of sensor data."""
        a = r[1:4]
        if st["lp"] is None:
            st["lp"] = list(a)
        for k in range(3):                     # low-pass accel: keep gravity, drop hand jerks
            st["lp"][k] += 0.1 * (a[k] - st["lp"][k])
        n = math.sqrt(sum(v * v for v in st["lp"])) or 1.0
        tilt = [math.degrees(math.asin(max(-1.0, min(1.0, v / n)))) for v in st["lp"]]
        dt_ = 0.0 if st["last_t"] is None else max(0.0, r[0] - st["last_t"])
        st["last_t"] = r[0]
        for k in range(3):                     # gyro angle (deg); dead band stops drift at rest
            g = r[4 + k]
            if abs(g) < args.gyro_deadband:
                g = 0.0
            st["ang"][k] += g * dt_
        st["sig"] = tilt + list(st["ang"])

    def rel():
        return [st["sig"][i] - st["zero"][i] for i in range(6)]

    def set_zero():
        st["zero"] = list(st["sig"])
        st["x"] = st["y"] = 0.0
        xs.clear()
        ys.clear()

    def mapped(s):
        h, v = st["cal"]["horizontal"], st["cal"]["vertical"]
        return (h["sign"] * h["gain"] * s[SIGNALS.index(h["signal"])],
                v["sign"] * v["gain"] * s[SIGNALS.index(v["signal"])])

    def go(phase):
        st["phase"] = phase
        title.set_text(PROMPTS.get(phase, ""))

    def on_space():
        ph = st["phase"]
        if st["sig"] is None:
            print("No data from the board yet, wait a moment and press SPACE again.")
            return
        if ph == "cal_still":
            set_zero()
            st["rec"] = []
            go("cal_ud")
        elif ph == "cal_ud":
            if len(st["rec"]) < 20:
                return
            sig, sign, gain, rng = pick_axis(st["rec"])
            st["cal"] = {"vertical": {"signal": sig, "sign": sign, "gain": gain}}
            st["ud_ranges"] = rng
            st["note"] = f"up/down -> {'+' if sign > 0 else '-'}{sig} (moved {max(rng):.0f} deg)"
            print("Calibration:", st["note"])
            set_zero()
            st["rec"] = []
            go("cal_lr")
        elif ph == "cal_lr":
            if len(st["rec"]) < 20:
                return
            vsig = st["cal"]["vertical"]["signal"]
            # don't reuse the up/down signal, or anything that moved a lot during up/down
            ud = st["ud_ranges"]
            busy = [SIGNALS[i] for i in range(6) if ud[i] > 0.5 * max(ud)]
            sig, sign, gain, rng = pick_axis(st["rec"], exclude=set(busy) | {vsig})
            st["cal"]["horizontal"] = {"signal": sig, "sign": sign, "gain": gain}
            lr = f"left/right -> {'+' if sign > 0 else '-'}{sig} (moved {max(rng[SIGNALS.index(sig)], 0):.0f} deg)"
            print("Calibration:", lr)
            st["note"] += "\n" + lr
            if rng[SIGNALS.index(sig)] < 5:
                st["note"] += ("\n!! left/right barely registered. Try twisting/tilting the pen"
                               "\n   sideways, or flash imu_ble_stream_gyro.ino for the gyro.")
            save_calibration(st["cal"])
            print(f"Saved {CAL_FILE.name}")
            go("wait")
        elif ph == "wait":
            set_zero()
            go("run")
            print("Started: position zeroed.")
        elif ph == "run":
            st["phase"] = "done"
            ani.event_source.stop()
            src.close()
            print("Stopped.")
            plt.close(fig)

    def on_key(ev):
        if ev.key == " ":
            on_space()
        elif ev.key == "c":
            xs.clear()
            ys.clear()
        elif ev.key == "k" and st["phase"] == "wait":
            st["cal"] = dict(DEFAULT_CAL)
            st["note"] = ""
            go("cal_still")
    fig.canvas.mpl_connect("key_press_event", on_key)

    def update(_):
        for r in src.read(timeout=0):
            update_signals(r)
            ph = st["phase"]
            if ph in ("cal_ud", "cal_lr"):
                s = rel()
                st["rec"].append(s)
                # show the raw movement while calibrating (biggest two signals)
                xs.append(s[SIGNALS.index("tilt_y")] + s[SIGNALS.index("gyro_z")])
                ys.append(s[SIGNALS.index("tilt_x")] + s[SIGNALS.index("gyro_y")])
            elif ph == "run":
                tx, ty = mapped(rel())
                # Smoothing, step 1: low-pass filter (exponential moving average).
                # Lower --smooth = smoother but a bit more lag.
                k = args.smooth
                st["x"] += k * (tx - st["x"])
                st["y"] += k * (ty - st["y"])
                # Smoothing, step 2: dead band. The dot only moves once the filtered
                # position is more than --deadband from where it was drawn,
                # so tiny hand tremor and sensor noise don't make it wiggle.
                if xs and math.hypot(st["x"] - xs[-1], st["y"] - ys[-1]) < args.deadband:
                    continue
                xs.append(st["x"])
                ys.append(st["y"])
        trail.set_data(xs, ys)
        if xs:
            dot.set_data([xs[-1]], [ys[-1]])
        lines = [f"{'accel+gyro' if src.has_gyro else 'accel only'}  dropped={src.dropped}"]
        c = st["cal"]
        if "horizontal" in c:
            lines.append(f"mapping: right = {'+' if c['horizontal']['sign'] > 0 else '-'}"
                         f"{c['horizontal']['signal']}   up = {'+' if c['vertical']['sign'] > 0 else '-'}"
                         f"{c['vertical']['signal']}")
        if st["note"]:
            lines.append(st["note"])
        if st["phase"] in ("cal_ud", "cal_lr") and st["rec"]:
            last = st["rec"][-1]
            lines.append("moved: " + " ".join(f"{n}={v:+.0f}" for n, v in zip(SIGNALS, last)))
        if "error" in src.status.lower():
            lines.append(src.status)
        info.set_text("\n".join(lines))
        return trail, dot, info

    ani = FuncAnimation(fig, update, interval=30, blit=False, cache_frame_data=False)
    fig._integration_ani = ani                               # keep the animation alive
    print("Click the plot window and follow the instructions in its title (SPACE to continue).")
    try:
        plt.show(block=True)
    finally:
        src.close()


# # --------------------------------------------------------------------------
# # Hook the pieces into pen_recorder (in memory only; the file is not changed)
# # --------------------------------------------------------------------------
# def install(args):
#     def open_source(_args):
#         src = Nano33Source(RATE_HZ, getattr(args, "address", None))
#         src.start()
#         return src

#     pr.open_source = open_source
#     start_g, still_g = getattr(args, "start_g", 0.12), getattr(args, "still_g", 0.04)
#     pr.MotionSegmenter = lambda rate: AccelMotionSegmenter(rate, start_g=start_g, still_g=still_g)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
#     data_dir = str(HERE / "data")

    def conn(p):
        p.add_argument("--address", help="board's Bluetooth address (default: scan by name)")

#     p = sub.add_parser("live", help="print live values")
#     conn(p)
#     p.set_defaults(func=pr.cmd_live)

    p = sub.add_parser("view", help="live plot of the pen's movement on a white plot")
    conn(p)
    p.add_argument("--trail", type=float, default=3.0, help="seconds of trail to keep")
    p.add_argument("--range", type=float, default=40.0, help="plot half-width")
    p.add_argument("--smooth", type=float, default=0.15, help="0-1, lower = smoother (more lag)")
    p.add_argument("--deadband", type=float, default=0.8,
                   help="degrees the pen must move before the dot moves (hides small jitter)")
    p.add_argument("--gyro-deadband", type=float, default=2.0,
                   help="gyro readings below this (deg/s) count as 0, so the angles don't drift")
    p.add_argument("--calibrate", action="store_true",
                   help="redo the up/down + left/right calibration before starting")
    p.set_defaults(func=cmd_view)

#     p = sub.add_parser("record", help="guided recording session")
#     conn(p)
#     p.add_argument("--writer", required=True, help="name/ID of the person writing")
#     p.add_argument("--letters", default=string.ascii_uppercase, help="letters to record (default A-Z)")
#     p.add_argument("--reps", type=int, default=10, help="repetitions per letter")
#     p.add_argument("--trigger", choices=["key", "motion"], default="key")
#     p.add_argument("--start-g", type=float, default=0.12, help="motion trigger: start threshold (g)")
#     p.add_argument("--still-g", type=float, default=0.04, help="motion trigger: still threshold (g)")
#     p.add_argument("--no-shuffle", dest="shuffle", action="store_false")
#     p.add_argument("--no-resume", dest="resume", action="store_false")
#     p.add_argument("--out", default=data_dir, help="output folder (default: Magic-Wand/data)")
#     p.set_defaults(func=pr.cmd_record)

#     p = sub.add_parser("export", help="build training CSV/JSON from all samples")
#     p.add_argument("--out", default=data_dir)
#     p.add_argument("--steps", type=int, default=100)
#     p.add_argument("--pen-axis", default="x", choices=["x", "y", "z", "-x", "-y", "-z"])
#     p.set_defaults(func=pr.cmd_export)

#     p = sub.add_parser("plot", help="plot one sample")
#     p.add_argument("file")
#     p.add_argument("--pen-axis", default="x", choices=["x", "y", "z", "-x", "-y", "-z"])
#     p.add_argument("--flip-x", action="store_true")
#     p.add_argument("--flip-y", action="store_true")
#     p.set_defaults(func=pr.cmd_plot)

    if argv is None:
        argv = sys.argv[1:] or DEFAULT_ARGS
    args = ap.parse_args(argv)
    args.rate = RATE_HZ
#     install(args)   # (recording only, not needed for the live view)
    args.func(args)


if __name__ == "__main__":
    main()
