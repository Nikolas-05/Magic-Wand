
import asyncio
import struct
from collections import deque

import matplotlib.pyplot as plt
import serial                              # pip install pyserial
from serial.tools import list_ports
from bleak import BleakClient, BleakScanner

DEVICE_NAME = "MagicWandPen"   # flash firmware/MagicWandPen/MagicWandPen.ino
CHAR_UUID = "6e400001-b5a3-f393-e0a9-e50e24dc4179"
PACKET_FMT = "<BB9h"   # uint8 seq, uint8 flags, int16 ax,ay,az (milli-g), gx,gy,gz (0.1 deg/s), mx,my,mz (0.1 uT)
PACKET_LEN = struct.calcsize(PACKET_FMT)   # 20 bytes (the firmware may send 2 extra force bytes; ignored)

ARDUINO_VID = 0x2341   # USB vendor ID of every official Arduino board (incl. Nano 33 BLE)
BAUD = 115200

COLUMNS = ["seq", "ax", "ay", "az", "gx", "gy", "gz", "mx", "my", "mz"]   # over USB "seq" becomes "ms"


def find_usb_port():
    """Return the COM port of a Nano 33 BLE plugged into this laptop, or None."""
    for port in list_ports.comports():
        if port.vid == ARDUINO_VID or "Nano 33 BLE" in (port.description or ""):
            return port.device
    return None


PRINT_EVERY = 10   # print 1 of every 10 samples (~10 lines/s at 100 Hz) so the console keeps up
HEADER = f"{'time':>8} | {'ax':>7} {'ay':>7} {'az':>7} g | {'gx':>7} {'gy':>7} {'gz':>7} deg/s | {'mx':>7} {'my':>7} {'mz':>7} uT"


def show(t, ax, ay, az, gx, gy, gz, mx, my, mz):
    """Print one labeled line of all 9 axes in the console."""
    print(f"{t:>8} | {ax:+7.3f} {ay:+7.3f} {az:+7.3f}   | {gx:+7.1f} {gy:+7.1f} {gz:+7.1f}       | "
          f"{mx:+7.1f} {my:+7.1f} {mz:+7.1f}", flush=True)


# ---------------- live plot: 3 panels (accel, gyro, mag), x/y/z in each ----------------
WINDOW = 300        # samples on screen (~3 s at 100 Hz)
PLOT_EVERY = 5      # redraw every 5 samples (~20 frames/s)
PANELS = [("Acceleration (g)", "ax", "ay", "az"),
          ("Gyroscope (deg/s)", "gx", "gy", "gz"),
          ("Magnetometer (uT)", "mx", "my", "mz")]
data = {name: deque([0.0] * WINDOW, maxlen=WINDOW) for _, *names in PANELS for name in names}
lines = {}


def setup_plot():
    plt.ion()
    fig, axes = plt.subplots(3, 1, sharex=True, figsize=(9, 7))
    for ax, (title, *names) in zip(axes, PANELS):
        for name, color in zip(names, ("tab:red", "tab:green", "tab:blue")):
            lines[name], = ax.plot(range(WINDOW), list(data[name]), color=color, label=name[1])
        ax.set_title(title)
        ax.legend(loc="upper left", ncol=3)
        ax.grid(True, alpha=0.3)
    axes[-1].set_xlabel(f"last {WINDOW} samples (close this window to stop)")
    fig.tight_layout()
    plt.show(block=False)
    return fig, axes


def add_sample(ax, ay, az, gx, gy, gz, mx, my, mz):
    for name, v in zip(("ax", "ay", "az", "gx", "gy", "gz", "mx", "my", "mz"), (ax, ay, az, gx, gy, gz, mx, my, mz)):
        data[name].append(v)


def update_plot(fig, axes):
    for name, line in lines.items():
        line.set_ydata(data[name])
    for ax in axes:
        ax.relim()
        ax.autoscale_view(scalex=False)
    plt.pause(0.001)                      # lets the window redraw


def stream_usb(port):
    """Read the firmware's USB serial lines: ms,ax,ay,az,gx,gy,gz,mx,my,mz,btn,force (already in g, deg/s, uT).
    Nothing is saved to disk: values are only printed and plotted."""
    with serial.Serial(port, BAUD, timeout=1) as ser:
        print(f"Connected over USB on {port}. Close the plot window (or press Ctrl+C) to stop.")
        fig, axes = setup_plot()
        n = 0
        warned = False
        while plt.fignum_exists(fig.number):    # closing the plot window stops logging
            line = ser.readline().decode(errors="ignore").strip()
            if not line or line.startswith("#"):      # skip blank and status lines
                continue
            try:
                values = [float(v) for v in line.split(",")[:10]]
            except ValueError:                        # header line, or half a line right after connecting
                continue
            if len(values) < 4:
                continue
            if len(values) < 10:                      # older sketch: accel only (or accel + gyro)
                if not warned:
                    print(f"Only {len(values) - 1} axes are coming in. Flash firmware/MagicWandPen to get all 9.")
                    warned = True
                values += [0.0] * (10 - len(values))
            ms, ax, ay, az, gx, gy, gz, mx, my, mz = values
            if n % (PRINT_EVERY * 20) == 0:
                print(HEADER)                         # repeat the column names every ~20 lines
            if n % PRINT_EVERY == 0:
                show(int(ms), ax, ay, az, gx, gy, gz, mx, my, mz)
            add_sample(ax, ay, az, gx, gy, gz, mx, my, mz)
            if n % PLOT_EVERY == 0:
                update_plot(fig, axes)
            n += 1
        print("Plot closed.")


async def main():
    # 1) USB cable first: if the Nano is plugged into the laptop, read it over serial
    port = find_usb_port()
    if port is not None:
        try:
            stream_usb(port)
        except KeyboardInterrupt:
            print("Stopped.")
        except serial.SerialException as e:
            print(f"Found the Nano on {port} but couldn't open it ({e}). "
                  "Close the Arduino Serial Monitor/Plotter and try again.")
        return

    # 2) Otherwise, Bluetooth
    print(f"No Nano on USB. Scanning Bluetooth for '{DEVICE_NAME}'...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=15)
    if device is None:
        print("Device not found. Is the board plugged in, or powered and advertising?")
        return

    def on_data(_, data: bytearray):
        seq, flags, ax, ay, az, gx, gy, gz, mx, my, mz = struct.unpack(PACKET_FMT, data[:PACKET_LEN])
        ax, ay, az = ax / 1000, ay / 1000, az / 1000   # g
        gx, gy, gz = gx / 10, gy / 10, gz / 10         # deg/s
        mx, my, mz = mx / 10, my / 10, mz / 10         # microtesla
        if seq % PRINT_EVERY == 0:
            show(seq, ax, ay, az, gx, gy, gz, mx, my, mz)
        add_sample(ax, ay, az, gx, gy, gz, mx, my, mz)

    async with BleakClient(device) as client:
        await client.start_notify(CHAR_UUID, on_data)
        print("Connected over Bluetooth. Close the plot window (or Ctrl+C) to stop.")
        print(HEADER)
        fig, axes = setup_plot()
        while client.is_connected and plt.fignum_exists(fig.number):
            update_plot(fig, axes)
            await asyncio.sleep(0.05)         # lets Bluetooth data come in between redraws

    print("Disconnected.")

import nest_asyncio
nest_asyncio.apply()
asyncio.run(main())
