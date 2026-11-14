

import asyncio
import csv
import struct
import sys

from bleak import BleakClient, BleakScanner

DEVICE_NAME = "Nano33-IMU"
CHAR_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"
PACKET_FMT = "<Ifff"   # uint32 t_ms, float ax, ay, az (matches the Arduino struct)

# COLUMNS = ["t_ms", "ax", "ay", "az", "gx", "gy", "gz", "mx", "my", "mz", "pen"]

async def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "imu_log.csv"

    print(f"Scanning for '{DEVICE_NAME}'...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=15)
    if device is None:
        print("Device not found. Is the board powered and advertising?")
        return

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        # writer.writerow(COLUMNS)
        writer.writerow(["t_ms", "ax", "ay", "az"])

        def on_data(_, data: bytearray):
            t_ms, ax, ay, az = struct.unpack(PACKET_FMT, data)
            writer.writerow([t_ms, ax, ay, az])
            print(f"{t_ms}\t{ax:.3f}\t{ay:.3f}\t{az:.3f}")

        async with BleakClient(device) as client:
            await client.start_notify(CHAR_UUID, on_data)
            print(f"Connected. Logging to {out_path}. Ctrl+C to stop.")
            while client.is_connected:
                await asyncio.sleep(0.5)

    print("Disconnected.")

import nest_asyncio
nest_asyncio.apply()
asyncio.run(main())