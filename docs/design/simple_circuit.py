#!/usr/bin/env python3
"""Simple power circuit: Spektrum 1S 800 mAh LiPo -> protection board -> switch -> 5 V boost -> Nano 33 BLE VIN."""
import sys, os
OUT = sys.argv[1] if len(sys.argv) > 1 else "."
F = "font-family='Helvetica, Arial, sans-serif'"
INK, NOTE, RED, BLK, BLUE, GREY = "#1d2430", "#5a6473", "#d62828", "#222", "#1f6fd1", "#888"
el = []
def t(x, y, s, size=12, fill=INK, a="start", w="normal"):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    el.append(f"<text x='{x}' y='{y}' {F} font-size='{size}' fill='{fill}' text-anchor='{a}' font-weight='{w}'>{s}</text>")
def ln(pts, col, wd=3, dash=None):
    d = " ".join(("M" if i == 0 else "L") + f"{x},{y}" for i, (x, y) in enumerate(pts))
    ds = f" stroke-dasharray='{dash}'" if dash else ""
    el.append(f"<path d='{d}' fill='none' stroke='{col}' stroke-width='{wd}' stroke-linejoin='round'{ds}/>")
def box(x, y, w, h, fill, title, sub=None, pins_l=(), pins_r=(), dash=None):
    ds = f" stroke-dasharray='{dash}'" if dash else ""
    el.append(f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='8' fill='{fill}' stroke='{INK}' stroke-width='1.2'{ds}/>")
    t(x + w / 2, y + 22, title, 13, "white" if fill not in ("white", "#f4f6f9") else INK, "middle", "bold")
    if sub: t(x + w / 2, y + 38, sub, 10.5, "#e8eef5" if fill not in ("white", "#f4f6f9") else NOTE, "middle")
    P = {}
    for i, p in enumerate(pins_l):
        yy = y + 62 + i * 30; P[p] = (x, yy); t(x + 8, yy + 4, p, 11, "white" if fill not in ("white", "#f4f6f9") else INK)
    for i, p in enumerate(pins_r):
        yy = y + 62 + i * 30; P[p + ">"] = (x + w, yy); t(x + w - 8, yy + 4, p, 11, "white" if fill not in ("white", "#f4f6f9") else INK, "end")
    return P
def dot(x, y): el.append(f"<circle cx='{x}' cy='{y}' r='4' fill='{INK}'/>")

W, H = 1180, 760
t(24, 34, "Magic Wand pen: simple battery-to-Nano circuit", 22, w="bold")
t(24, 56, "Power only. No force sensor, no charger port: the battery unplugs and charges on a 1S LiPo charger.", 13, NOTE)

# battery
bat = box(40, 140, 170, 130, "#7aa6d8", "LiPo 1S 3.7 V", "Spektrum 800 mAh, 51x24x8", pins_r=("+ (red)", "− (black)"))
t(125, 300, "JST-RCY plug", 11, NOTE, "middle")
# RCY connector pair
for (x, y), col in ((bat["+ (red)>"], RED), (bat["− (black)>"], BLK)):
    ln([(x, y), (x + 40, y)], col)
el.append(f"<rect x='{250}' y='{186}' width='22' height='54' rx='3' fill='#e33' stroke='{INK}'/>")
t(261, 178, "J1", 11, INK, "middle", "bold")
t(261, 262, "RCY", 10, NOTE, "middle")
# protection board
pcm = box(330, 140, 170, 130, "#6b4fa3", "1S protection board", "DW01A + FS8205 (≈ 3 x 20 mm)", pins_l=("B+", "B−"), pins_r=("P+", "P−"))
ln([(272, bat["+ (red)>"][1]), pcm["B+"]], RED); ln([(272, bat["− (black)>"][1]), pcm["B−"]], BLK)
t(415, 300, "cuts off below ≈ 2.4–3.0 V", 11, NOTE, "middle")
t(415, 316, "and on a short circuit", 11, NOTE, "middle")
# switch
sx, sy = 560, pcm["P+>"][1]
ln([pcm["P+>"], (sx, sy)], RED)
el.append(f"<circle cx='{sx+3}' cy='{sy}' r='4' fill='white' stroke='{INK}' stroke-width='1.5'/>")
el.append(f"<circle cx='{sx+43}' cy='{sy}' r='4' fill='white' stroke='{INK}' stroke-width='1.5'/>")
ln([(sx + 6, sy), (sx + 40, sy - 16)], INK, 2)
t(sx + 23, sy - 26, "SW1 slide switch", 11, INK, "middle", "bold")
ln([(sx + 47, sy), (640, sy)], RED)
# boost
bst = box(640, 140, 170, 130, "#3b8d3e", "5 V boost", "Pololu U1V11F5 (or similar)", pins_l=("VIN", "GND"), pins_r=("VOUT", "GND "))
ln([(sx + 47, sy), bst["VIN"]], RED)
ln([pcm["P−>"], bst["GND"]], BLK)
# Nano
nano = box(900, 120, 240, 260, "#0f7b8a", "Arduino Nano 33 BLE", "Sense Rev2", pins_l=("VIN", "GND", "A1 (optional)", "", "D2"))
ln([bst["VOUT>"], (860, bst["VOUT>"][1]), (860, nano["VIN"][1]), nano["VIN"]], RED)
ln([bst["GND >"], (880, bst["GND >"][1]), (880, nano["GND"][1]), nano["GND"]], BLK)
t(850, nano["VIN"][1] - 8, "5 V", 11, RED, "end", "bold")
# optional battery monitor divider
mx = 600
ln([(mx, sy), (mx, 360)], RED, 2, "6,4"); dot(mx, sy)
el.append(f"<rect x='{mx-7}' y='360' width='14' height='36' fill='#c9b38a' stroke='{INK}' stroke-dasharray='4,3'/>")
t(mx + 14, 382, "R1 100 kΩ", 11, INK)
ln([(mx, 396), (mx, 430)], "#e0c000", 2, "6,4"); dot(mx, 430)
el.append(f"<rect x='{mx-7}' y='450' width='14' height='36' fill='#c9b38a' stroke='{INK}' stroke-dasharray='4,3'/>")
t(mx + 14, 472, "R2 100 kΩ", 11, INK)
ln([(mx, 430), (mx, 450)], "#e0c000", 2, "6,4")
ln([(mx, 486), (mx, 520), (575, 520), (575, pcm["P−>"][1])], BLK, 2, "6,4"); dot(575, pcm["P−>"][1])
ln([(mx, 430), (870, 430), (870, nano["A1 (optional)"][1]), nano["A1 (optional)"]], "#e0c000", 2, "6,4")
t(640, 450, "optional: battery level on A1 (reads half the cell voltage)", 11, NOTE)
# pen-down button kept
ln([nano["D2"], (850, nano["D2"][1]), (850, 476)], BLUE, 2)
el.append(f"<circle cx='850' cy='480' r='4' fill='white' stroke='{INK}' stroke-width='1.5'/>")
el.append(f"<circle cx='850' cy='520' r='4' fill='white' stroke='{INK}' stroke-width='1.5'/>")
ln([(850, 484), (836, 514)], INK, 2)
ln([(850, 524), (850, 540), (890, 540), (890, nano["GND"][1])], BLK, 2)
t(830, 505, "SW2 pen-down button (optional)", 11, INK, "end", "bold")
# notes
notes = [
    ("How it works", True),
    ("Battery (3.7–4.2 V) → protection board → power switch → boost to 5 V → Nano VIN. The Nano's own regulator makes the 3.3 V.", False),
    ("Wire it", True),
    ("1. Solder a JST-RCY female pigtail to the protection board's B+ / B− so the battery stays removable.", False),
    ("2. P+ goes through SW1 to the boost VIN; P− goes straight to the boost GND. Boost VOUT → Nano VIN, boost GND → Nano GND.", False),
    ("3. Use 26 AWG for the power wires. Check your board revision's VIN range on the Arduino page before powering up.", False),
    ("Safety", True),
    ("• The Spektrum pack has no protection circuit; the small 1S board stops it being drained flat. Without it, switch off as soon as the pen dies.", False),
    ("• Never connect the battery to the Nano's 3V3 pin, and switch SW1 off when the USB cable is plugged in.", False),
    ("• Charge only out of the pen, on a 1S LiPo charger set to ≤ 0.8 A.", False),
]
y = 570
for txt, head in notes:
    t(40, y, txt, 12.5 if head else 11.5, INK, "start", "bold" if head else "normal"); y += 20 if head else 18
t(W - 24, H - 14, "Magic Wand pen, simple power circuit, 2026-11-10", 10, NOTE, "end")
svg = f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' viewBox='0 0 {W} {H}'><rect width='100%' height='100%' fill='white'/>{''.join(el)}</svg>"
open(os.path.join(OUT, "07_simple_power_circuit.svg"), "w").write(svg)
print("ok")
