# Pen enclosure design (rev A sketch)

Dimensioned drawings of a handheld wand/pen that holds the Arduino Nano 33 BLE Sense Rev2, an FSR squeeze sensor, the D2 pen-down button and a rechargeable battery. Wiring follows [`../FORCE_SENSOR.md`](../FORCE_SENSOR.md) and the pins in `firmware/MagicWandPen/MagicWandPen.ino`.

| Sheet | What it shows |
|---|---|
| [`01_side_and_top.svg`](01_side_and_top.svg) | Long section through the centre with every part in place, plus the outside top view and all lengths |
| [`02_cross_sections.svg`](02_cross_sections.svg) | Cuts through the grip, the Nano, the battery and the power bay, and the rear cap with both USB ports |
| [`03_exploded_and_parts.svg`](03_exploded_and_parts.svg) | Exploded view and parts list with sizes |
| [`04_wiring.svg`](04_wiring.svg) | Where each wire runs inside the pen, and the schematic |

Each sheet also has a `.png` copy. To change a dimension, edit the numbers at the top of `make_drawings.py` and run `python make_drawings.py .` (writes the SVGs into the folder you pass).

## Layout at a glance

Body Ø24 mm (Ø20 mm bore), 196 mm long, about the size of a thick whiteboard marker. From the tip:

| From the tip (mm) | Part | Size (mm) |
|---|---|---|
| 0–20 | Solid printed tip cone | |
| 22–44 | Grip flat (10 mm wide) with FSR 400 + puck at **31 mm**; thumb button at 36 mm | FSR Ø7.6 x 0.3 |
| 50–95 | Nano 33 BLE Sense Rev2 on side rails, USB facing the rear | 45 x 18 |
| 96–182 | Micro-USB FPC extension from the Nano's port to the rear cap | ≈ 100 long |
| 108–158 | LiPo 701750 (3.7 V, ≈ 450 mAh, with protection PCB) | 7 x 17 x 50 |
| 161–187 | TP4056 USB-C charger, with the 5 V boost stacked on foam above it; slide switch in the side wall | 26 x 17, 15.2 x 11.4 |
| 188–196 | Rear cap: DATA (micro-USB) and CHARGE (USB-C) ports, charge LED window | |

## Design choices

- **IMU close to the fingers.** The Nano sits right behind the grip, so the BMI270/BMM150 are about 45 mm behind the FSR and the board moves with the tip. Battery and charger go at the back.
- **Squeezing doesn't shake the IMU.** The FSR sits on a rigid flat in the top shell; the Nano is clamped on its own ledges and ribs further back, so grip force doesn't flex the board (FORCE_SENSOR.md section 3).
- **USB access without opening the pen.** The Nano's micro-USB is carried to the rear cap by a thin FPC extension cable, next to the charger's USB-C. Both ports are reachable with the pen closed.
- **Switch after the charger.** SW1 sits between the TP4056 output and the boost, so the pen still charges when switched off. (FORCE_SENSOR.md puts it between the battery and the module; this placement works the same and also lets you charge while off.)
- **No pin headers.** Wires solder straight to the underside of the Nano's pads and run in a channel below the board and battery, which keeps the pen at Ø24.
- **Two-part shell** split along the top of the PCB (y = −1 mm), held by M2 screws from below, with a press-fit rear cap.

## Check before you print

These sizes come from datasheets and typical modules. Measure your actual parts, because clone modules vary:

1. **TP4056 module width.** Many are 17 mm, some are 18–19 mm. Over 18 mm, widen the bore to Ø21.
2. **Battery.** Any 1-cell LiPo up to 7 x 17 x 50 mm with a protection PCB fits. A thinner one leaves more room for wires.
3. **Nano pad order.** The wiring sheet uses the classic Nano layout (3V3/A0 near the USB end, VIN/GND and D2 toward the tip). Check it against your board's silkscreen.
4. **VIN range** for your board revision on the Arduino product page, before feeding 5 V from the boost.
5. **Charge current.** Most TP4056 modules ship set to 1 A, too much for a 450 mAh cell. Change RPROG to about 3.3 kΩ (≈ 360 mA).
6. **USB + battery together.** Turn SW1 off while the DATA cable is plugged in, so the board isn't powered from USB and the boost at the same time.

## Shorter alternative

If 196 mm is too long, stack the battery under the Nano instead of behind it. That brings the pen down to about 150 mm, but it grows to about Ø30 and moves weight toward the tip.
