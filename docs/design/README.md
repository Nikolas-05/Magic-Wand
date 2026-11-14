# Pen enclosure design (rev D sketch)

Dimensioned drawings of a handheld wand/pen that holds the Arduino Nano 33 BLE Sense Rev2, an FSR squeeze sensor, the D2 pen-down button and a rechargeable battery. Wiring follows [`../FORCE_SENSOR.md`](../FORCE_SENSOR.md) and the pins in `firmware/MagicWandPen/MagicWandPen.ino`.

| Sheet | What it shows |
|---|---|
| [`01_side_and_top.svg`](01_side_and_top.svg) | Long section through the centre with every part in place, plus the outside top view and all lengths |
| [`02_cross_sections.svg`](02_cross_sections.svg) | Cuts through the grip, the Nano, the battery and the power bay, and the rear cap with both USB ports |
| [`03_exploded_and_parts.svg`](03_exploded_and_parts.svg) | Exploded view and parts list with sizes |
| [`04_wiring.svg`](04_wiring.svg) | Where each wire runs inside the pen, and the schematic |
| [`05_inner_grip_and_nano.svg`](05_inner_grip_and_nano.svg) | Inner details 1–4: FSR pocket and tail path, thumb-button mount, Nano rail and shell joint, screw bosses |
| [`06_inner_power_and_cap.svg`](06_inner_power_and_cap.svg) | Inner details 5–7: power bay and rear cap, battery cradle, power switch, plus the print clearances |
| [`07_simple_power_circuit.svg`](07_simple_power_circuit.svg) | Simple battery-to-Nano power circuit (no FSR, no charger) |

Each sheet also has a `.png` copy in the `Sketches` folder at the top of the repo. To change a dimension, edit the numbers at the top of `make_drawings.py` and run `python make_drawings.py .` (writes the SVGs into the folder you pass).

## Layout at a glance (rev D)

Body **Ø30 mm** (Ø26 mm bore), **166 mm** long. From the tip:

| From the tip (mm) | Part | Size (mm) |
|---|---|---|
| 0–18 | Solid printed tip cone | |
| 18.6–69.6 | **Spektrum SPMX8001S30 1S 800 mAh, standing on edge** under the grip, held by guide ribs | 51 x 24 x 8 |
| 22–44 | Grip flat (11 mm wide, 1.6 mm wall under the FSR) on top, FSR 400 + puck at **31 mm**; thumb button at 36 mm in the side gap | FSR Ø7.6 x 0.3 |
| 40–48.5 | FSR connector + 10 kΩ / 0.1 µF in the side gap opposite the button | |
| 74–119 | Nano 33 BLE Sense Rev2 on side rail blocks, USB facing the rear; 4 mm wire gaps each side | 45 x 18 |
| 120–164 | Micro-USB FPC extension from the Nano's port to the rear cap | ≈ 50 long |
| 131–140 | Slide switch in the side wall | 8.6 x 3.6 x 3.5 |
| 138–164 | TP4056 USB-C charger in grooves, 5 V boost on foam above it; USB-C mouth against the cap wall | 26 x 17, 15.2 x 11.4 |
| 154–166 | Rear cap, lapping 4 mm over the shell (stepped to Ø28): DATA (micro-USB) and CHARGE (USB-C), Ø2 charge LED window | |

Detail 5 on sheet 06 is drawn in rev B coordinates; subtract 30 mm from its x positions. Screws are M2 x 10 at x = 26, 71.25 and 129.25, z = ±8.

## Design choices

- **Weight at the front.** The battery stands on edge under the grip, so the heaviest part sits in your fingers. The Nano follows; its IMU is about 71 mm behind the FSR.
- **Squeezing doesn't shake the IMU.** The FSR sits on a rigid flat in the top shell; the Nano is clamped on its own ledges and ribs further back, so grip force doesn't flex the board (FORCE_SENSOR.md section 3).
- **USB access without opening the pen.** The Nano's micro-USB is carried to the rear cap by a thin FPC extension cable, next to the charger's USB-C. Both ports are reachable with the pen closed.
- **Switch after the charger.** SW1 sits between the TP4056 output and the boost, so the pen still charges when switched off. (FORCE_SENSOR.md puts it between the battery and the module; this placement works the same and also lets you charge while off.)
- **No pin headers.** Wires solder straight to the underside of the Nano's pads and run in a channel below the board and battery, which keeps the pen at Ø30.
- **Two-part shell** split along the top of the PCB (y = −1 mm), held by M2 screws from below, with a press-fit rear cap.

## Check before you print

These sizes come from datasheets and typical modules. Measure your actual parts, because clone modules vary:

1. **TP4056 module width.** Many are 17 mm, some are 18–19 mm. The Ø26 bore takes up to about 20 mm.
2. **Battery.** Drawn for the Spektrum SPMX8001S30 (51 x 24 x 8, JST-RCY). It has **no protection circuit**, so add a 1S DW01 + FS8205 board between the pack and the TP4056 (see sheet 07). Any 1-cell pack up to 52 x 24.5 x 8.5 fits the cradle.
3. **Nano pad order.** The wiring sheet uses the classic Nano layout (3V3/A0 near the USB end, VIN/GND and D2 toward the tip). Check it against your board's silkscreen.
4. **VIN range** for your board revision on the Arduino product page, before feeding 5 V from the boost.
5. **Charge current.** Most TP4056 modules ship set to 1 A, too much for this 800 mAh pack. Change RPROG to 2.4 kΩ (≈ 500 mA), or 1.5 kΩ (≈ 800 mA) at most.
6. **USB + battery together.** Turn SW1 off while the DATA cable is plugged in, so the board isn't powered from USB and the boost at the same time.

## Rev B changes (2026-11-09)

- The charger moved to the very back (x = 168–194) so its USB-C mouth touches the inside of the cap. In rev A it sat 6 mm behind the cap wall, too deep for a plug to reach.
- The port walls are thinned to 0.8 mm by an outside spot-face so plugs seat fully.
- The rear cap now laps 4 mm over a stepped end of the shell, so the inside stays a full Ø20.
- The power switch moved to x = 165, in front of the charger.
- The Nano is clamped by hold-down fingers on its edges instead of a centre rib, so nothing presses on the radio module.
- New detail sheets 05 and 06 show the printed features and the clearances used.

## Rev C changes (2026-11-09)

- Battery changed to the 601750 (5.4 x 16.5 x 51.4 mm, 500 mAh) and moved to the front, standing on edge under the grip. The 3–4 mm gaps beside it hold the thumb button, the FSR connector and the wires.
- The Nano moved back to x = 74–119 and the power bay to x = 131–166. The pen is now 166 mm instead of 196 mm.
- Screw bosses are at x = 26, 71.25 and 129.25.
- Because the IMU moved, collect training data with the finished pen. Recordings from a different layout won't match.

## Rev D changes (2026-11-10)

- The whole body grew from Ø24 to **Ø30** (bore Ø20 to Ø26) so the Spektrum 800 mAh pack (51 x 24 x 8) fits on edge under the grip. Length stays 166 mm.
- Battery cradle: guide ribs 8.4 apart, end pads with 0.3 foam top and bottom; the cell runs from x = 18.6 to 69.6.
- The grip flat is 1 mm deep on the bigger body (11 mm wide), with a 1.6 mm wall under the FSR.
- The Nano now sits on 4 mm wide rail blocks in the bottom shell, leaving 4 mm wire gaps on each side. Hold-down fingers are taller to reach it.
- Thumb button and power switch moved out with the wall. Screw bosses moved to z = ±8; screws are now M2 x 10.
- The shell end steps to Ø28 under the rear cap.
- Charge current set to about 500 mA (RPROG 2.4 kΩ), and a 1S protection board is added, because this pack has none.
