#!/usr/bin/env python3
"""Generate dimensioned SVG drawings of the Magic Wand pen enclosure.
All geometry in mm. x = distance from the tip, y = up, z = across (page-down = thumb side in plan view)."""
import os, sys

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

FONT = "font-family='Helvetica, Arial, sans-serif'"
C = dict(
    ink="#1d2430", dim="#c0392b", shell="#dfe3ea", shellE="#6b7686", hatch="#9aa4b2",
    pcb="#0f7b8a", pcbE="#0a5560", comp="#2b2f36", bat="#7aa6d8", batE="#3e6a9c",
    tp="#2c4fa3", boost="#3b8d3e", fsr="#c99a2e", puck="#e0703a", sw="#555c66",
    fpc="#d9a521", red="#d62828", black="#222222", orange="#f08c00", yellow="#e0c000",
    blue="#1f6fd1", grey="#888888", note="#5a6473",
)

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

class Sheet:
    def __init__(self, w, h, title, subtitle):
        self.w, self.h = w, h
        self.el = []
        self.defs = f"""
<defs>
 <pattern id='hatch' width='6' height='6' patternUnits='userSpaceOnUse' patternTransform='rotate(45)'>
  <rect width='6' height='6' fill='{C['shell']}'/><line x1='0' y1='0' x2='0' y2='6' stroke='{C['hatch']}' stroke-width='1.2'/></pattern>
 <marker id='arr' viewBox='0 0 10 10' refX='10' refY='5' markerWidth='7' markerHeight='7' orient='auto-start-reverse'>
  <path d='M0,1 L10,5 L0,9 z' fill='{C['dim']}'/></marker>
 <marker id='arrk' viewBox='0 0 10 10' refX='10' refY='5' markerWidth='7' markerHeight='7' orient='auto-start-reverse'>
  <path d='M0,1 L10,5 L0,9 z' fill='{C['ink']}'/></marker>
 <marker id='dot' viewBox='0 0 10 10' refX='5' refY='5' markerWidth='5' markerHeight='5'>
  <circle cx='5' cy='5' r='4' fill='{C['ink']}'/></marker>
</defs>"""
        self.text(24, 34, title, 22, weight="bold")
        self.text(24, 56, subtitle, 13, fill=C['note'])

    def add(self, s): self.el.append(s)

    def text(self, x, y, s, size=11, fill=None, anchor="start", weight="normal", rot=None, italic=False):
        fill = fill or C['ink']
        tr = f" transform='rotate({rot} {x:.1f} {y:.1f})'" if rot else ""
        st = " font-style='italic'" if italic else ""
        self.add(f"<text x='{x:.1f}' y='{y:.1f}' {FONT} font-size='{size}' fill='{fill}' text-anchor='{anchor}' font-weight='{weight}'{st}{tr}>{esc(s)}</text>")

    def rect(self, x, y, w, h, fill, stroke=None, sw=1, rx=0, dash=None, op=1):
        stroke = stroke or "none"
        d = f" stroke-dasharray='{dash}'" if dash else ""
        self.add(f"<rect x='{x:.2f}' y='{y:.2f}' width='{w:.2f}' height='{h:.2f}' rx='{rx}' fill='{fill}' stroke='{stroke}' stroke-width='{sw}'{d} opacity='{op}'/>")

    def line(self, x1, y1, x2, y2, stroke=None, sw=1, dash=None, marker=None, mstart=None):
        stroke = stroke or C['ink']
        d = f" stroke-dasharray='{dash}'" if dash else ""
        m = f" marker-end='url(#{marker})'" if marker else ""
        ms = f" marker-start='url(#{mstart})'" if mstart else ""
        self.add(f"<line x1='{x1:.2f}' y1='{y1:.2f}' x2='{x2:.2f}' y2='{y2:.2f}' stroke='{stroke}' stroke-width='{sw}'{d}{m}{ms}/>")

    def path(self, d, fill="none", stroke=None, sw=1, dash=None, extra=""):
        stroke = stroke or C['ink']
        ds = f" stroke-dasharray='{dash}'" if dash else ""
        self.add(f"<path d='{d}' fill='{fill}' stroke='{stroke}' stroke-width='{sw}' stroke-linejoin='round' stroke-linecap='round'{ds} {extra}/>")

    def circle(self, cx, cy, r, fill, stroke=None, sw=1, dash=None):
        stroke = stroke or "none"
        d = f" stroke-dasharray='{dash}'" if dash else ""
        self.add(f"<circle cx='{cx:.2f}' cy='{cy:.2f}' r='{r:.2f}' fill='{fill}' stroke='{stroke}' stroke-width='{sw}'{d}/>")

    # horizontal dimension between page x1,x2 at page y; ext lines down/up to fy1/fy2
    def dimh(self, x1, x2, y, label, fy1=None, fy2=None, size=11):
        for x, fy in ((x1, fy1), (x2, fy2)):
            if fy is not None:
                self.line(x, fy, x, y + (4 if y > fy else -4), C['dim'], 0.7)
        self.line(x1, y, x2, y, C['dim'], 0.9, marker="arr", mstart="arr")
        self.rect((x1 + x2) / 2 - len(label) * size * 0.3 - 3, y - size * 0.75, len(label) * size * 0.6 + 6, size * 1.1, "white")
        self.text((x1 + x2) / 2, y + size * 0.3, label, size, C['dim'], "middle")

    def dimv(self, x, y1, y2, label, fx=None, size=11, left=True):
        if fx is not None:
            for y in (y1, y2):
                self.line(fx, y, x + (4 if x > fx else -4), y, C['dim'], 0.7)
        self.line(x, y1, x, y2, C['dim'], 0.9, marker="arr", mstart="arr")
        tx = x - 5 if left else x + 5
        self.text(tx, (y1 + y2) / 2 + 4, label, size, C['dim'], "end" if left else "start")

    def callout(self, x, y, tx, ty, label, size=11, anchor=None):
        self.line(tx, ty, x, y, C['ink'], 0.7, marker="dot")
        anchor = anchor or ("start" if tx >= x else "end")
        dx = 3 if anchor == "start" else -3
        for i, part in enumerate(label.split("\n")):
            self.text(tx + dx, ty + 4 + i * (size + 2), part, size, anchor=anchor)

    def save(self, name):
        body = "\n".join(self.el)
        svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{self.w}' height='{self.h}' viewBox='0 0 {self.w} {self.h}'>"
               f"{self.defs}<rect width='100%' height='100%' fill='white'/>{body}"
               f"<text x='{self.w-24}' y='{self.h-14}' {FONT} font-size='10' fill='{C['note']}' text-anchor='end'>Magic Wand pen, rev A sketch, 2026-11-08. All dimensions in mm. Not to scale when printed; use the numbers.</text></svg>")
        with open(os.path.join(OUT, name), "w") as f:
            f.write(svg)

# ---------------------------------------------------------------- geometry (mm)
L = 196          # overall length
R = 12.0         # outer radius
RI = 10.0        # inner radius
TIP = 20         # tip cone length
GRIP = (22, 44)  # flat for the index finger
FSR_X = 31       # FSR centre, 31 mm from tip
BTN_X = 36       # thumb button
NANO = (50, 95)  # Nano 33 BLE Sense Rev2, 45 x 18, USB end at 95
PCB_Y = (-2.0, -1.0)
BAT = (108, 158) # 701750 LiPo 7 x 17 x 50
BAT_Y = (-4.0, 3.0)
TP = (161, 187)  # TP4056 USB-C module 26 x 17
TP_Y = (-4.0, -2.4)
BST = (163, 178) # Pololu U1V11F5 15.2 x 11.4
BST_Y = (2.6, 3.6)
SW_X = 170       # slide switch, side wall
CAP = (188, 196)
RIBS = [(48, 50), (106, 107.5), (159, 160.5)]
SCREWS = [47, 106.5, 159.5]

def longsection(S, ox, oy, s, labels=True, layer="all", dy_top=0, dy_bot=0, dx_cap=0, explode=False):
    """Longitudinal section on the vertical mid-plane. layer: all | top | bottom | parts | cap"""
    X = lambda x: ox + x * s
    Y = lambda y: oy - y * s

    def shell_outline(half):
        # outer + inner outline as one even-odd path for a half (top: y>=-1, bottom: y<=-1)
        split = -1.0
        if half == "top":
            outer = (f"M{X(18)},{Y(split)} L{X(1.0)},{Y(split)} "  # tip: top half holds the cone above split
                     f"Q{X(0)},{Y(0)} {X(1.2)},{Y(1.3)} L{X(TIP)},{Y(R)} L{X(GRIP[0])},{Y(11)} L{X(GRIP[1])},{Y(11)} "
                     f"L{X(GRIP[1]+2)},{Y(R)} L{X(CAP[0])},{Y(R)} L{X(CAP[0])},{Y(split)} L{X(CAP[0]-2)},{Y(split)} "
                     f"L{X(CAP[0]-2)},{Y(RI)} L{X(GRIP[1]+2)},{Y(RI)} L{X(GRIP[1])},{Y(9)} L{X(GRIP[0])},{Y(9)} "
                     f"L{X(TIP)},{Y(RI)} L{X(18)},{Y(RI)} Z")
        else:
            outer = (f"M{X(18)},{Y(split)} L{X(1.0)},{Y(split)} Q{X(0)},{Y(-1.6)} {X(1.2)},{Y(-1.6)} "
                     f"L{X(TIP)},{Y(-R)} L{X(CAP[0])},{Y(-R)} L{X(CAP[0])},{Y(split)} L{X(CAP[0]-2)},{Y(split)} "
                     f"L{X(CAP[0]-2)},{Y(-RI)} L{X(18)},{Y(-RI)} Z")
        return outer

    def ribs(half):
        for a, b in RIBS:
            if half == "top":
                S.rect(X(a), Y(RI), (b - a) * s, 3 * s, "url(#hatch)", C['shellE'], 0.8)
            else:
                S.rect(X(a), Y(-6.5), (b - a) * s, 3.5 * s, "url(#hatch)", C['shellE'], 0.8)

    def bosses():
        for x in SCREWS:
            # screw from below into boss in top half: shown dashed (off-plane, beside the parts)
            S.rect(X(x - 1), Y(-1), 2 * s, 9 * s, "none", C['shellE'], 0.8, dash="3,2")
            S.rect(X(x - 1.9), Y(-R), 3.8 * s, 1.8 * s, "none", C['shellE'], 0.8, dash="3,2")

    if layer in ("all", "top"):
        g = f"<g transform='translate(0,{-dy_top})'>"
        S.add(g)
        S.path(shell_outline("top"), "url(#hatch)", C['shellE'], 1.2)
        ribs("top")
        # FSR pocket + FSR + puck on the flat
        S.rect(X(FSR_X - 4.2), Y(11), 8.4 * s, 0.5 * s, "white", C['shellE'], 0.6)
        S.add("</g>")
    if layer in ("all", "bottom"):
        S.add(f"<g transform='translate(0,{dy_bot})'>")
        S.path(shell_outline("bottom"), "url(#hatch)", C['shellE'], 1.2)
        ribs("bottom")
        # PCB ledges (in bottom half, off-plane) shown dashed
        if not explode:
            pass
        S.add("</g>")
    if layer in ("all",):
        bosses()
    if layer in ("all", "cap"):
        S.add(f"<g transform='translate({dx_cap},0)'>")
        cap = (f"M{X(CAP[0])},{Y(R)} L{X(CAP[1]-3)},{Y(R)} Q{X(CAP[1])},{Y(R)} {X(CAP[1])},{Y(R-3)} "
               f"L{X(CAP[1])},{Y(-R+3)} Q{X(CAP[1])},{Y(-R)} {X(CAP[1]-3)},{Y(-R)} L{X(CAP[0])},{Y(-R)} "
               f"L{X(CAP[0])},{Y(-RI)} L{X(CAP[0]-3)},{Y(-RI)} L{X(CAP[0]-3)},{Y(-RI+1)} L{X(CAP[1]-2)},{Y(-RI+1)} "
               f"L{X(CAP[1]-2)},{Y(RI-1)} L{X(CAP[0]-3)},{Y(RI-1)} L{X(CAP[0]-3)},{Y(RI)} L{X(CAP[0])},{Y(RI)} Z")
        S.path(cap, "url(#hatch)", C['shellE'], 1.2)
        # port openings in the end wall
        S.rect(X(CAP[1] - 2), Y(0.8), 2 * s, 3.2 * s, "white", C['ink'], 0.6)   # USB-C
        S.rect(X(CAP[1] - 2), Y(6.6), 2 * s, 3.0 * s, "white", C['ink'], 0.6)   # micro-USB female
        S.add("</g>")

    if layer in ("all", "parts"):
        # FSR on the flat + puck
        S.rect(X(FSR_X - 3.8), Y(10.9), 7.6 * s, 0.4 * s, C['fsr'], C['ink'], 0.5)
        S.path(f"M{X(FSR_X-3)},{Y(11.3)} Q{X(FSR_X)},{Y(14.4)} {X(FSR_X+3)},{Y(11.3)} Z", C['puck'], C['ink'], 0.7)
        # FSR tail: along flat to slot at x=36, into cavity, to connector at 40-46
        S.path(f"M{X(FSR_X+3.8)},{Y(11.1)} L{X(36)},{Y(11.1)} L{X(37)},{Y(8.5)} L{X(39)},{Y(6.2)} L{X(40)},{Y(6.2)}", "none", C['fsr'], 0.5 * s)
        S.rect(X(40), Y(7.6), 6 * s, 2.8 * s, C['comp'], None, rx=1)   # 2-pin header connector
        # resistor + cap block at the connector
        S.rect(X(40.5), Y(4.4), 5 * s, 1.6 * s, "#c9b38a", C['ink'], 0.5, rx=3)
        # thumb button (on side wall, off-plane) dashed
        S.rect(X(BTN_X - 3), Y(3), 6 * s, 6 * s, "none", C['ink'], 0.9, dash="3,2")
        S.circle(X(BTN_X), Y(0), 1.75 * s, "none", C['ink'], 0.9, dash="3,2")
        # Nano PCB + parts
        S.rect(X(NANO[0]), Y(PCB_Y[1]), 45 * s, 1.0 * s, C['pcb'], C['pcbE'], 0.8)
        S.rect(X(60), Y(1.2), 10 * s, 2.2 * s, "#bfc6cf", C['ink'], 0.6)   # NINA-B306 module
        S.rect(X(74), Y(0.0), 3 * s, 1.0 * s, C['comp'])                     # BMI270
        S.rect(X(79), Y(0.0), 2 * s, 1.0 * s, C['comp'])                     # BMM150
        S.rect(X(84), Y(0.4), 3 * s, 1.4 * s, C['comp'])
        S.rect(X(89.5), Y(1.6), 6.5 * s, 2.6 * s, "#c8ccd2", C['ink'], 0.7)  # micro-USB socket
        # FPC micro-USB extension: male plug + ribbon over battery + female end in cap
        S.rect(X(96), Y(2.6), 8.5 * s, 4.0 * s, C['comp'], None, rx=1)
        S.path(f"M{X(104.5)},{Y(1.5)} L{X(106)},{Y(4.6)} L{X(180)},{Y(4.6)} L{X(182)},{Y(5.1)}", "none", C['fpc'], 0.4 * s)
        S.rect(X(182), Y(6.6), 6 * s, 3.0 * s, "#c8ccd2", C['ink'], 0.7)
        # battery
        S.rect(X(BAT[0]), Y(BAT_Y[1]), 50 * s, 7 * s, C['bat'], C['batE'], 1, rx=4)
        S.rect(X(BAT[1] - 2.5), Y(1.5), 2.5 * s, 4 * s, "#d8dde4", C['batE'], 0.6)  # protection PCB end
        # TP4056 + USB-C
        S.rect(X(TP[0]), Y(TP_Y[1]), 26 * s, 1.6 * s, C['tp'], C['ink'], 0.7)
        S.rect(X(167), Y(-1.4), 5 * s, 1.0 * s, C['comp'])
        S.rect(X(184.3), Y(0.8), 3.7 * s, 3.2 * s, "#c8ccd2", C['ink'], 0.7)
        # boost on foam over the TP4056
        S.rect(X(BST[0]), Y(BST_Y[1]), 15.2 * s, 1.0 * s, C['boost'], C['ink'], 0.7)
        S.rect(X(BST[0] + 1), Y(BST_Y[0]), 13 * s, 1.6 * s, "#f3e6b3", C['ink'], 0.4)   # foam tape
        S.rect(X(168), Y(4.6), 3 * s, 1.0 * s, C['comp'])
        # slide switch on side wall (off-plane)
        S.rect(X(SW_X - 4.3), Y(1.8), 8.6 * s, 3.6 * s, "none", C['sw'], 0.9, dash="3,2")
        # wires in the lower channel
        wy = [-7.2, -8.2]
        S.path(f"M{X(BST[0])},{Y(3.0)} L{X(161)},{Y(1)} L{X(161)},{Y(wy[0])} L{X(54.7)},{Y(wy[0])} L{X(54.7)},{Y(-2)}", "none", C['red'], 1.6)
        S.path(f"M{X(BST[0])},{Y(2.8)} L{X(161.6)},{Y(0.8)} L{X(161.6)},{Y(wy[1])} L{X(57.2)},{Y(wy[1])} L{X(57.2)},{Y(-2)}", "none", C['black'], 1.6)
        S.path(f"M{X(46)},{Y(6.2)} L{X(47)},{Y(6.2)} L{X(47.5)},{Y(-5)} L{X(82.7)},{Y(-5)} L{X(82.7)},{Y(-2)}", "none", C['yellow'], 1.6)
        S.path(f"M{X(46)},{Y(5.6)} L{X(46.6)},{Y(5.6)} L{X(46.8)},{Y(-5.9)} L{X(87.8)},{Y(-5.9)} L{X(87.8)},{Y(-2)}", "none", C['orange'], 1.6)
        S.path(f"M{X(BTN_X+3)},{Y(-2)} L{X(42)},{Y(-6.4)} L{X(64.9)},{Y(-6.4)} L{X(64.9)},{Y(-2)}", "none", C['blue'], 1.6)


# ---------------------------------------------------------------- sheet 1: side section + plan
def sheet1():
    s = 5.0
    S = Sheet(1240, 880, "Magic Wand pen: side section and top view",
              "Arduino Nano 33 BLE Sense Rev2 (45 x 18 mm), FSR 400 squeeze sensor, D2 thumb button, 1-cell LiPo + TP4056 charger + 5 V boost")
    ox, oy = 90, 290
    X = lambda x: ox + x * s
    Y = lambda y: oy - y * s
    S.text(ox, 112, "VIEW 1: LONGITUDINAL SECTION ON THE CENTRE PLANE (tip left, USB end right; dashed = off-plane parts)", 12, weight="bold")
    longsection(S, ox, oy, s)
    S.line(X(-4), oy, X(L + 4), oy, C['grey'], 0.6, dash="10,3,2,3")
    S.line(X(10), Y(-1), X(185), Y(-1), C['shellE'], 0.6, dash="2,3")
    top = lambda r: Y(R) - 22 - 24 * r
    bot = lambda r: Y(-R) + 24 + 24 * r
    S.callout(X(FSR_X), Y(13.5), X(4), top(2), "FSR 400 + puck, under the index finger", anchor="start")
    S.callout(X(43), Y(6.2), X(40), top(0), "FSR plug + 10 kΩ / 0.1 µF", anchor="start")
    S.callout(X(65), Y(0.3), X(62), top(1), "Nano 33 BLE Sense Rev2 on side rails (no pin headers)", anchor="start")
    S.callout(X(100), Y(1), X(100), top(0), "micro-USB FPC extension to DATA port", anchor="start")
    S.callout(X(140), Y(4.6), X(150), top(2), "FPC ribbon over battery", anchor="start")
    S.callout(X(170), Y(3.4), X(170), top(1), "5 V boost (Pololu U1V11F5) on foam", anchor="start")
    S.callout(X(BTN_X), Y(-1.75), X(2), bot(0), "6x6 tact button, thumb side (D2)", anchor="start")
    S.callout(X(76), Y(-0.5), X(52), bot(1), "BMI270 + BMM150 IMU, ≈ 45 mm behind the FSR", anchor="start")
    S.callout(X(90), Y(-7.6), X(72), bot(2), "wire channel under the PCB and battery", anchor="start")
    S.callout(X(130), Y(-1), X(128), bot(0), "LiPo 701750, 3.7 V, ≈ 450 mAh", anchor="start")
    S.callout(X(SW_X), Y(-0.3), X(160), bot(1), "slide switch (side wall)", anchor="start")
    S.callout(X(176), Y(-3.2), X(176), bot(2), "TP4056 USB-C charger", anchor="start")
    S.callout(X(194), Y(5), X(200), top(0), "rear cap: DATA +\nCHARGE ports", anchor="start")
    S.text(X(L) + 6, Y(-1) + 4, "split", 9, C['shellE'])
    yc = bot(3) + 14
    chain = [(0, TIP), (TIP, NANO[0]), (NANO[0], NANO[1]), (NANO[1], BAT[0]), (BAT[0], BAT[1]), (BAT[1], CAP[0]), (CAP[0], CAP[1])]
    labs = ["tip", "grip", "Nano bay", "", "battery", "power bay", "cap"]
    for (a, b), t in zip(chain, labs):
        S.dimh(X(a), X(b), yc, f"{b-a:g}", Y(-R) + 4, Y(-R) + 4)
        S.text((X(a) + X(b)) / 2, yc + 16, t, 10, C['note'], "middle")
    S.dimh(X(0), X(L), yc + 40, f"overall {L}")
    S.dimv(X(L) + 34, Y(R), Y(-R), "Ø24", X(L) + 2, left=False)
    S.dimv(X(L) + 78, Y(RI), Y(-RI), "Ø20 bore", None, left=False)
    S.line(X(L) + 74, Y(RI), X(L) + 82, Y(RI), C['dim'], 0.7); S.line(X(L) + 74, Y(-RI), X(L) + 82, Y(-RI), C['dim'], 0.7)

    # ---- plan view
    oy2 = 690
    Z = lambda z: oy2 + z * s
    S.text(ox, oy2 - 112, "VIEW 2: TOP VIEW (outside). Section cuts A–D and rear view E are on sheet 2.", 12, weight="bold")
    outline = (f"M{X(TIP)},{Z(-R)} L{X(CAP[1]-3)},{Z(-R)} Q{X(CAP[1])},{Z(-R)} {X(CAP[1])},{Z(-R+3)} L{X(CAP[1])},{Z(R-3)} "
               f"Q{X(CAP[1])},{Z(R)} {X(CAP[1]-3)},{Z(R)} L{X(TIP)},{Z(R)} L{X(1.2)},{Z(1.5)} Q{X(0)},{Z(0)} {X(1.2)},{Z(-1.5)} Z")
    S.path(outline, C['shell'], C['shellE'], 1.3)
    S.line(X(CAP[0]), Z(-R), X(CAP[0]), Z(R), C['shellE'], 1)
    S.line(X(TIP), Z(-R), X(TIP), Z(R), C['shellE'], 0.6, dash="3,2")
    S.rect(X(GRIP[0]), Z(-5), (GRIP[1] - GRIP[0]) * s, 10 * s, "#cfd5de", C['shellE'], 0.8, rx=6)
    S.circle(X(FSR_X), Z(0), 3.8 * s, C['fsr'], C['ink'], 0.6)
    S.circle(X(FSR_X), Z(0), 3 * s, C['puck'], C['ink'], 0.6)
    S.rect(X(BTN_X - 1.75), Z(R - 0.2), 3.5 * s, 1.0 * s, C['ink'], None, rx=2)
    S.rect(X(SW_X - 1.5), Z(-R - 1.5), 3 * s, 1.5 * s, C['sw'], None, rx=1)
    for x in SCREWS:
        S.circle(X(x), Z(-6), 1.1 * s, "white", C['shellE'], 0.8, dash="2,2")
        S.circle(X(x), Z(6), 1.1 * s, "white", C['shellE'], 0.8, dash="2,2")
    S.line(X(-4), Z(0), X(L + 4), Z(0), C['grey'], 0.6, dash="10,3,2,3")
    for lab, x in (("A", FSR_X), ("B", 72), ("C", 133), ("D", 174)):
        S.line(X(x), Z(-R - 4), X(x), Z(R + 4), C['dim'], 1, dash="12,3,2,3")
        S.text(X(x) + 6, Z(-R - 3), lab, 13, C['dim'], "start", "bold")
        S.text(X(x) + 6, Z(R + 4) + 6, lab, 13, C['dim'], "start", "bold")
    S.line(X(L) + 10, Z(0), X(L) + 40, Z(0), C['dim'], 1, marker="arr")
    S.text(X(L) + 44, Z(0) + 4, "E", 13, C['dim'], weight="bold")
    S.callout(X(FSR_X + 3), Z(-3.5), X(44), Z(-R) - 42, "10 mm wide flat, 1 mm deep, with Ø8.4 x 0.5 FSR pocket", anchor="start")
    S.callout(X(SW_X), Z(-R - 1.5), X(112), Z(-R) - 22, "power switch, opposite side", anchor="start")
    S.callout(X(BTN_X), Z(R + 0.8), X(50), Z(R) + 30, "thumb button, stands 1 mm proud", anchor="start")
    S.callout(X(SCREWS[1]), Z(6 + 1.1), X(112), Z(R) + 30, "M2 screws from below, 6x (dashed)", anchor="start")
    S.dimv(X(0) - 18, Z(-R), Z(R), "24", X(TIP) - 2)
    S.dimh(X(0), X(FSR_X), Z(R) + 62, f"{FSR_X}", Z(0), Z(0))
    S.text(X(FSR_X) + 8, Z(R) + 66, "FSR centre from the tip (FORCE_SENSOR.md: 2–4 cm)", 10, C['dim'])
    S.dimh(X(GRIP[0]), X(GRIP[1]), Z(R) + 90, f"grip flat {GRIP[1]-GRIP[0]}", Z(5), Z(5))
    S.save("01_side_and_top.svg")


# ---------------------------------------------------------------- sheet 2: sections
def ring(S, cx, cy, s, flat=False):
    X = lambda z: cx + z * s
    Y = lambda y: cy - y * s
    if flat:
        import math
        a = math.degrees(math.asin(5 / R)); ai = math.degrees(math.asin(4.4 / RI))
        # outer with flat at y=11 (|z|<=5 approx), inner with flat at y=9
        zo = (R * R - 11 * 11) ** 0.5; zi = (RI * RI - 9 * 9) ** 0.5
        d = (f"M{X(-zo)},{Y(11)} L{X(zo)},{Y(11)} A{R*s},{R*s} 0 1 1 {X(-zo)},{Y(11)} Z "
             f"M{X(-zi)},{Y(9)} A{RI*s},{RI*s} 0 1 0 {X(zi)},{Y(9)} Z")
        S.path(d, "url(#hatch)", C['shellE'], 1.2, extra="fill-rule='evenodd'")
    else:
        d = (f"M{X(-R)},{Y(0)} A{R*s},{R*s} 0 1 1 {X(R)},{Y(0)} A{R*s},{R*s} 0 1 1 {X(-R)},{Y(0)} Z "
             f"M{X(-RI)},{Y(0)} A{RI*s},{RI*s} 0 1 0 {X(RI)},{Y(0)} A{RI*s},{RI*s} 0 1 0 {X(-RI)},{Y(0)} Z")
        S.path(d, "url(#hatch)", C['shellE'], 1.2, extra="fill-rule='evenodd'")
    S.line(X(-R - 3), Y(-1), X(R + 3), Y(-1), C['shellE'], 0.8, dash="3,2")
    S.line(X(0), Y(R + 3), X(0), Y(-R - 3), C['grey'], 0.5, dash="8,2,2,2")
    S.line(X(-R - 3), Y(0), X(R + 3), Y(0), C['grey'], 0.5, dash="8,2,2,2")

def wire(S, cx, cy, s, z, y, col):
    S.circle(cx + z * s, cy - y * s, 0.55 * s, col, "white", 0.6)

def sheet2():
    s = 8.0
    S = Sheet(1180, 760, "Magic Wand pen: cross-sections A–D and rear view E",
              "Looking from the rear toward the tip. Thumb side is on the left. Dashed line = split between top and bottom shell (y = −1 mm).")
    cy = 330
    cxs = [130, 365, 600, 835, 1065]
    titles = ["A–A  grip, x = 31", "B–B  Nano, x = 72", "C–C  battery, x = 133", "D–D  power bay, x = 174", "E  rear cap (outside)"]
    for cx, t in zip(cxs, titles):
        S.text(cx, 150, t, 13, anchor="middle", weight="bold")
    X = lambda cx, z: cx + z * s
    Y = lambda y: cy - y * s
    # A
    cx = cxs[0]
    ring(S, cx, cy, s, flat=True)
    S.rect(X(cx, -3.8), Y(11.0), 7.6 * s, 0.45 * s, C['fsr'], C['ink'], 0.5)
    S.path(f"M{X(cx,-3)},{Y(11.4)} Q{X(cx,0)},{Y(14.5)} {X(cx,3)},{Y(11.4)} Z", C['puck'], C['ink'], 0.7)
    S.rect(X(cx, -9.6), Y(3), 3.6 * s, 6 * s, C['comp'], None, rx=1)       # tact switch body
    S.rect(X(cx, -12.9), Y(1.75), 3.4 * s, 3.5 * s, C['ink'], None, rx=3)  # actuator through wall
    S.rect(X(cx, -6.2), Y(2.5), 1.2 * s, 5 * s, "url(#hatch)", C['shellE'], 0.6)  # switch backing rib
    for z, y, col in ((-1.2, -7.5, C['blue']), (0, -7.6, C['black']), (2.4, -6.8, C['yellow']), (3.6, -6.3, C['orange'])):
        wire(S, cx, cy, s, z, y, col)
    S.callout(X(cx, 2), Y(13), X(cx, 4), Y(17), "FSR + puck", 10, "start")
    S.callout(X(cx, -12), Y(-1.5), X(cx, -13), Y(-15.5), "thumb button (D2)", 10, "start")
    S.callout(X(cx, -5.6), Y(-2.2), X(cx, -13), Y(-18), "backing rib takes the push", 10, "start")
    S.dimv(X(cx, R) + 12, Y(11), Y(-R), "23", X(cx, 6), left=False)
    # B
    cx = cxs[1]
    ring(S, cx, cy, s)
    for zz in (-1, 1):  # side rails / ledges
        S.rect(X(cx, zz * 9.95 - (0.9 if zz > 0 else 0)), Y(-2), 0.95 * s, 2.0 * s, "url(#hatch)", C['shellE'], 0.6)
    S.rect(X(cx, -9), Y(-1), 18 * s, 1 * s, C['pcb'], C['pcbE'], 0.8)
    S.rect(X(cx, -5), Y(1.2), 10 * s, 2.2 * s, "#bfc6cf", C['ink'], 0.6)
    S.rect(X(cx, -6.5), Y(2.5) , 13 * s, 0.01, "none")
    S.rect(X(cx, -1.0), Y(9.9), 2 * s, 8.6 * s, "url(#hatch)", C['shellE'], 0.6)  # hold-down rib from top shell
    for z, col in ((-7.62, C['blue']), (7.62, C['red'])):
        S.circle(X(cx, z), Y(-1.5), 0.5 * s, "#d4af37", C['ink'], 0.5)
    for z, y, col in ((-3.0, -6.4, C['blue']), (-1.8, -7.6, C['black']), (-0.6, -7.2, C['red']), (0.6, -8.2, C['black']), (1.8, -5.0, C['yellow']), (3.0, -5.9, C['orange'])):
        wire(S, cx, cy, s, z, y, col)
    S.callout(X(cx, 0.8), Y(7), X(cx, 2), Y(17), "hold-down rib", 10, "start")
    S.callout(X(cx, -3), Y(0.6), X(cx, -2), Y(15.5), "radio module", 10, "end")
    S.callout(X(cx, 9.5), Y(-1.8), X(cx, -13), Y(-15.5), "PCB 18 x 1.0 on side ledges", 10, "start")
    S.callout(X(cx, -1.8), Y(-7.6), X(cx, -13), Y(-18), "wires to pads, from below", 10, "start")
    S.dimh(X(cx, -9), X(cx, 9), Y(-R) + 90, "18", Y(-2) + 2, Y(-2) + 2)
    # C
    cx = cxs[2]
    ring(S, cx, cy, s)
    S.rect(X(cx, -8.5), Y(BAT_Y[1]), 17 * s, 7 * s, C['bat'], C['batE'], 1, rx=8)
    S.rect(X(cx, -3.75), Y(4.9), 7.5 * s, 0.4 * s, C['fpc'], C['ink'], 0.4)
    S.rect(X(cx, -6), Y(-4), 12 * s, 1.0 * s, "#f3e6b3", C['ink'], 0.4)   # foam
    for z, y, col in ((-0.7, -7.2, C['red']), (0.7, -8.0, C['black'])):
        wire(S, cx, cy, s, z, y, col)
    S.callout(X(cx, 4), Y(1), X(cx, 2), Y(17), "LiPo 7 x 17 x 50", 10, "start")
    S.callout(X(cx, -2), Y(5), X(cx, -2), Y(15.5), "FPC ribbon", 10, "end")
    S.callout(X(cx, 4), Y(-4.5), X(cx, -13), Y(-15.5), "foam pad", 10, "start")
    S.callout(X(cx, 0), Y(-7.6), X(cx, -13), Y(-18), "5 V + GND to VIN", 10, "start")
    S.dimh(X(cx, -8.5), X(cx, 8.5), Y(-R) + 90, "17", Y(-4) + 2, Y(-4) + 2)
    S.dimv(X(cx, R) + 12, Y(3), Y(-4), "7", X(cx, 8.5), left=False)
    # D
    cx = cxs[3]
    ring(S, cx, cy, s)
    S.rect(X(cx, -8.5), Y(TP_Y[1]), 17 * s, 1.6 * s, C['tp'], C['ink'], 0.7)
    S.rect(X(cx, -2.5), Y(-1.4), 5 * s, 1.0 * s, C['comp'])
    S.rect(X(cx, -6.5), Y(BST_Y[0]), 13 * s, 1.6 * s, "#f3e6b3", C['ink'], 0.4)
    S.rect(X(cx, -5.7), Y(BST_Y[1]), 11.4 * s, 1.0 * s, C['boost'], C['ink'], 0.7)
    S.rect(X(cx, -1.5), Y(4.6), 3 * s, 1.0 * s, C['comp'])
    S.rect(X(cx, -3.75), Y(6.4), 7.5 * s, 0.4 * s, C['fpc'], C['ink'], 0.4)
    S.rect(X(cx, 5.6), Y(1.8), 3.6 * s, 3.6 * s, C['sw'], None, rx=1)      # switch body
    S.rect(X(cx, 9.2), Y(0.75), 3.6 * s, 1.5 * s, C['ink'], None, rx=1)    # lever through wall slot
    S.callout(X(cx, -4), Y(-3.2), X(cx, -13), Y(-15.5), "TP4056 charger, 17 wide", 10, "start")
    S.callout(X(cx, -3), Y(3.1), X(cx, -2), Y(15.5), "boost, 11.4 wide", 10, "end")
    S.callout(X(cx, 11), Y(0.5), X(cx, 3), Y(17), "slide switch", 10, "start")
    # E rear view
    cx = cxs[4]
    S.circle(cx, cy, R * s, C['shell'], C['shellE'], 1.3)
    S.circle(cx, cy, (R - 3) * s, "none", C['shellE'], 0.6, dash="3,2")
    S.rect(X(cx, -4.6), Y(0.8), 9.2 * s, 3.4 * s, "white", C['ink'], 1, rx=1.6 * s)
    S.rect(X(cx, -4.0), Y(6.6), 8.0 * s, 3.0 * s, "white", C['ink'], 1, rx=4)
    S.text(cx, Y(-4.2), "CHARGE", 11, anchor="middle", weight="bold")
    S.text(cx, Y(-6.2), "USB-C", 10, C['note'], "middle")
    S.text(cx, Y(9.4), "DATA (micro-USB)", 10, anchor="middle", weight="bold")
    S.circle(X(cx, -3.2), Y(-9), 0.9 * s, C['red'])
    S.callout(X(cx, -3.2), Y(-9), X(cx, -12), Y(-15.5), "charge LED window Ø2", 10, "start")
    S.text(cx, Y(-18.5), "USB-C opening 9.2 x 3.4", 10, C['dim'], "middle")
    S.text(cx, Y(-20.5), "micro-USB opening 8.0 x 3.0", 10, C['dim'], "middle")

    # notes block
    ny = 560
    notes = [
        "Why this layout",
        "• Nano sits right behind the grip so the IMU stays near your fingers and the tip; battery and charger go to the back, as in FORCE_SENSOR.md section 4.",
        "• The FSR lies on a flat, rigid pocket in the top shell. The Nano is clamped on its own rails 19 mm further back, so squeezing the grip does not flex the board (section 3).",
        "• The thumb button has a backing rib so pressing it doesn't push the switch into the cavity or flex the shell.",
        "• Shell splits at y = −1 mm (top of the PCB). The bottom half carries the PCB ledges and wire channel; the top half carries the FSR pocket and the hold-down ribs.",
        "• Bore Ø20 is set by the 18 mm Nano plus 1 mm clearance a side; 2 mm walls give a Ø24 body, about the size of a whiteboard marker.",
        "• Print in PETG or PLA, 0.2 mm layers, top half printed flat side down. Use 100 % infill around the FSR pocket so it stays rigid.",
    ]
    for i, n in enumerate(notes):
        S.text(40, ny + i * 22, n, 13 if i == 0 else 12, weight="bold" if i == 0 else "normal")
    S.save("02_cross_sections.svg")


# ---------------------------------------------------------------- sheet 3: exploded
def sheet3():
    s = 4.6
    S = Sheet(1180, 1000, "Magic Wand pen: exploded view and parts list",
              "Assembly order: wire the harness on the bench, drop parts into the bottom shell, close the top shell, fit the rear cap.")
    ox, oy = 70, 380
    X = lambda x: ox + x * s
    Y = lambda y: oy - y * s
    longsection(S, ox, oy, s, layer="top", dy_top=150)
    S.text(X(100), Y(R) - 150 - 14, "① TOP SHELL (FSR pocket, PCB hold-down ribs, screw bosses)", 12, anchor="middle", weight="bold")
    longsection(S, ox, oy, s, layer="parts")
    longsection(S, ox, oy, s, layer="bottom", dy_bot=150)
    S.text(X(60), Y(-R) + 150 + 84, "② BOTTOM SHELL (PCB ledges, wire channel, button + switch holes)", 12, anchor="middle", weight="bold")
    longsection(S, ox, oy, s, layer="cap", dx_cap=70)
    S.text(X(CAP[1]) + 70 - 10, Y(R) - 12, "③ REAR CAP", 12, anchor="middle", weight="bold")
    for x in (40, 100, 160):
        S.line(X(x), Y(R) - 125, X(x), Y(R) - 20, C['grey'], 1, dash="5,4", marker="arrk")
        S.line(X(x), Y(-R) + 125, X(x), Y(-R) + 20, C['grey'], 1, dash="5,4", marker="arrk")
    S.line(X(CAP[1]) + 50, oy, X(CAP[1]) + 12, oy, C['grey'], 1, dash="5,4", marker="arrk")
    # screws below bottom shell
    for x in SCREWS:
        sx = X(x); sy = Y(-R) + 150 + 40
        S.rect(sx - 1.9 * s, sy, 3.8 * s, 1.4 * s, C['ink'])
        S.rect(sx - 1 * s, sy - 6 * s, 2 * s, 6 * s, "#9aa0a8", C['ink'], 0.5)
    S.text(X(SCREWS[1]) + 30, Y(-R) + 150 + 84, "④ M2 x 8 pan-head screws, 6x (two per position, one each side)", 11)
    # numbered part tags on parts row
    tags = [(FSR_X, 13.5, "5"), (BTN_X, -3.5, "6"), (43, 9, "7"), (68, 3, "8"), (100, 4, "9"),
            (133, -1, "10"), (170, 5.5, "11"), (176, -3.4, "12"), (SW_X - 5, -1.6, "13")]
    for x, y, t in tags:
        S.circle(X(x), Y(y) - 14, 9, "white", C['ink'], 1)
        S.text(X(x), Y(y) - 10, t, 10, anchor="middle", weight="bold")
        S.line(X(x), Y(y) - 5, X(x), Y(y), C['ink'], 0.6)
    # BOM table
    rows = [
        ("#", "Part", "Size (mm)", "Notes"),
        ("1", "Top shell, printed", "196 x Ø24 half", "PETG/PLA, FSR pocket Ø8.4 x 0.5"),
        ("2", "Bottom shell, printed", "188 x Ø24 half", "ledges at y = −2, 3 screw bosses per side"),
        ("3", "Rear cap, printed", "8 x Ø24", "USB-C + micro-USB cut-outs, LED window"),
        ("4", "M2 x 8 screws", "6 pcs", "self-tapping into printed bosses, or M2 heat-set inserts"),
        ("5", "Interlink FSR 400 short tail + puck", "Ø7.6 x 0.3, tail ≈ 30", "puck: Ø6 TPU dome or hot-glue dot"),
        ("6", "Tact switch 6 x 6, 7 mm stem", "6 x 6 x 7", "D2 to GND, internal pull-up"),
        ("7", "2-pin female header, 10 kΩ, 0.1 µF", "", "FSR divider, heat-shrunk at the connector"),
        ("8", "Arduino Nano 33 BLE Sense Rev2", "45 x 18 x ≈ 5", "no pin headers; wires soldered under the pads"),
        ("9", "Micro-USB FPC extension, male to female", "≈ 100 long, 7.5 wide", "female end glued into the rear cap"),
        ("10", "LiPo 701750 with protection PCB", "7 x 17 x 50", "≈ 450 mAh, roughly 12–25 h of streaming"),
        ("11", "Pololu U1V11F5 5 V step-up", "15.2 x 11.4 x 3", "or any ≥ 200 mA 5 V boost that fits"),
        ("12", "TP4056 USB-C charger with DW01 protection", "26 x 17 x 5", "set charge current ≤ 1C: swap RPROG for 3.3 kΩ (≈ 360 mA)"),
        ("13", "SS12D00 slide switch", "8.6 x 3.6 x 3.5", "between TP4056 OUT+ and boost IN"),
        ("", "Silicone wire 28 AWG (signals), 26 AWG (power)", "", "colours as on sheet 4"),
    ]
    tx, ty = 40, 720
    cw = [40, 330, 190, 440]
    for i, r in enumerate(rows):
        y = ty + i * 17
        if i == 0:
            S.rect(tx - 4, y - 13, sum(cw), 17, "#eef1f5")
        x = tx
        for j, cell in enumerate(r):
            S.text(x, y, cell, 11, weight="bold" if i == 0 else "normal")
            x += cw[j]
    S.save("03_exploded_and_parts.svg")


# ---------------------------------------------------------------- sheet 4: wiring
def sheet4():
    s = 5.0
    S = Sheet(1180, 900, "Magic Wand pen: wiring and routing",
              "Top: plan view into the bottom shell, top shell removed (parts drawn see-through, wires run beneath them). Bottom: schematic.")
    ox, oy = 90, 190
    X = lambda x: ox + x * s
    Z = lambda z: oy + z * s
    outline = (f"M{X(TIP)},{Z(-R)} L{X(CAP[0])},{Z(-R)} L{X(CAP[0])},{Z(R)} L{X(TIP)},{Z(R)} L{X(1.2)},{Z(1.5)} Q{X(0)},{Z(0)} {X(1.2)},{Z(-1.5)} Z")
    S.path(outline, C['shell'], C['shellE'], 1.2)
    S.rect(X(18), Z(-RI), (CAP[0] - 2 - 18) * s, 2 * RI * s, "white", C['shellE'], 0.6)
    for a, b in RIBS:
        S.rect(X(a), Z(-RI), (b - a) * s, 2 * RI * s, "url(#hatch)", C['shellE'], 0.6, op=0.5)
    px = lambda i: 90.3 - i * 2.54
    top_row = ["D13", "3V3", "AREF", "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "5V", "RST", "GND", "VIN"]
    bot_row = ["D12", "D11", "D10", "D9", "D8", "D7", "D6", "D5", "D4", "D3", "D2", "GND", "RST", "RX0", "TX1"]
    P = {("t", n): px(i) for i, n in enumerate(top_row)}
    P.update({("b", n): px(i) for i, n in enumerate(bot_row)})
    def w(pts, col, wd=2.4):
        d = "M" + " L".join(f"{X(a)},{Z(b)}" for a, b in pts)
        S.path(d, "none", col, wd)
    # wires first (they run under the parts)
    w([(46, -1.2), (48.5, -3.0), (P["t", "A0"], -3.0), (P["t", "A0"], -7.62)], C['yellow'])
    w([(46, -2.0), (48.5, -4.6), (P["t", "3V3"], -4.6), (P["t", "3V3"], -7.62)], C['orange'])
    w([(46, 0.0), (48.5, -1.6), (55.8, -1.6), (P["t", "GND"], -6.0), (P["t", "GND"], -7.62)], C['black'])
    w([(BTN_X + 3, 6.0), (P["b", "D2"], 6.0), (P["b", "D2"], 7.62)], C['blue'])
    w([(BTN_X + 3, 4.8), (P["b", "GND"], 4.8), (P["b", "GND"], 7.62)], C['black'])
    w([(BST[0], 1.0), (53.4, 1.0), (53.4, -4.4), (P["t", "VIN"], -6.0), (P["t", "VIN"], -7.62)], C['red'])
    w([(BST[0], 2.4), (58.4, 2.4), (58.4, -5.6), (P["t", "GND"], -7.0)], C['black'])
    w([(158, -4), (161.5, -6)], C['red'], 1.8); w([(158, 4), (161.5, 6)], C['black'], 1.8)
    # parts
    S.rect(X(NANO[0]), Z(-9), 45 * s, 18 * s, C['pcb'], C['pcbE'], 1, rx=3, op=0.55)
    S.rect(X(89.5), Z(-3.8), 6.5 * s, 7.6 * s, "#c8ccd2", C['ink'], 0.7)
    S.text(X(72.5), Z(0.4) + 4, "Nano 33 BLE Sense Rev2 (component side up)", 10, C['ink'], "middle", "bold")
    for row, zz in ((top_row, -7.62), (bot_row, 7.62)):
        for i, name in enumerate(row):
            S.circle(X(px(i)), Z(zz), 0.75 * s, "#d4af37", C['ink'], 0.4)
    for (side, name, lift) in (("t", "3V3", 0), ("t", "A0", 0), ("t", "GND", 1), ("t", "VIN", 0), ("b", "D2", 0), ("b", "GND", 1)):
        zz = -7.62 if side == "t" else 7.62
        off = (-8 - 10 * lift) if side == "t" else (15 + 10 * lift)
        S.text(X(P[side, name]), Z(zz) + off, name, 9, C['ink'], "middle", "bold")
    S.text(X(91), Z(-R) - 6, "USB end", 9, C['note'], "middle")
    S.rect(X(96), Z(-3.75), 86 * s, 7.5 * s, "none", C['fpc'], 1.4, dash="6,3")
    S.rect(X(BAT[0]), Z(-8.5), 50 * s, 17 * s, C['bat'], C['batE'], 1, rx=6, op=0.55)
    S.text(X(133), Z(-5.5) + 4, "LiPo 701750 (leads exit at the rear)", 10, C['ink'], "middle", "bold")
    S.text(X(133), Z(0) + 4, "FPC ribbon on top (dashed)", 9.5, C['note'], "middle")
    S.rect(X(TP[0]), Z(-8.5), 26 * s, 17 * s, C['tp'], C['ink'], 0.8, op=0.55)
    S.rect(X(184.3), Z(-4.5), 3.7 * s, 9 * s, "#c8ccd2", C['ink'], 0.7)
    S.rect(X(BST[0]), Z(-5.7), 15.2 * s, 11.4 * s, C['boost'], C['ink'], 0.8, op=0.75)
    S.text(X(170.6), Z(-0.5), "BOOST", 9, "white", "middle", "bold")
    S.text(X(174), Z(7.6) + 3, "TP4056", 9, "white", "middle", "bold")
    S.rect(X(SW_X - 4.3), Z(-R + 0.2), 8.6 * s, 3.6 * s, C['sw'], None, rx=1)
    S.text(X(SW_X), Z(-R) - 6, "SW1", 9, C['note'], "middle", "bold")
    S.circle(X(FSR_X), Z(0), 3.8 * s, C['fsr'], C['ink'], 0.6)
    S.rect(X(FSR_X + 3.8), Z(-2.2), (36 - FSR_X - 3.8) * s, 4.4 * s, C['fsr'])
    S.text(X(FSR_X), Z(-R) - 6, "FSR (in top shell)", 9, C['note'], "middle")
    S.rect(X(40), Z(-2.5), 6 * s, 5 * s, C['comp'], None, rx=1)
    S.rect(X(BTN_X - 3), Z(4.2), 6 * s, 6 * s, C['comp'], None, rx=1)
    S.circle(X(BTN_X), Z(7.2), 1.75 * s, "#555")
    S.text(X(BTN_X), Z(R) + 14, "SW2 button", 9, C['note'], "middle")
    S.text(X(110), Z(R) + 30, "Pad order follows the classic Nano layout; check it against the silkscreen on your board before soldering.", 10.5, C['note'], "middle")

    # ---- schematic
    sy = 330
    S.text(40, sy, "SCHEMATIC", 13, weight="bold")
    def box(x, y, w, h, title, col, pins_l=(), pins_r=(), tcol="white"):
        S.rect(x, y, w, h, col, C['ink'], 1, rx=6)
        S.text(x + w / 2, y + 18, title, 12, tcol, "middle", "bold")
        pl = {}
        for i, p in enumerate(pins_l):
            yy = y + 40 + i * 24
            S.text(x + 8, yy + 4, p.strip(), 10, tcol); pl[p] = (x, yy)
        for i, p in enumerate(pins_r):
            yy = y + 40 + i * 24
            S.text(x + w - 8, yy + 4, p.strip(), 10, tcol, "end"); pl[p + ">"] = (x + w, yy)
        return pl
    def pl(pts, col, wd=2.2):
        S.path("M" + " L".join(f"{a},{b}" for a, b in pts), "none", col, wd)
    nano = box(520, sy + 30, 190, 150, "Nano 33 BLE Sense Rev2", C['pcb'], ("D2", "GND ", "VIN", "GND"), ("3V3", "A0", "GND", "USB"))
    bat = box(1010, sy + 300, 120, 80, "LiPo 3.7 V", C['bat'], ("+", "−"))
    tp = box(790, sy + 300, 150, 110, "TP4056 USB-C", C['tp'], ("OUT+", "OUT−", "USB-C"), ("B+", "B−"))
    bst = box(520, sy + 300, 150, 80, "5 V boost", C['boost'], ("VOUT", "GND"), ("VIN", "GND "))
    pl([tp["B+>"], bat["+"]], C['red']); pl([tp["B−>"], bat["−"]], C['black'])
    y1 = tp["OUT+"][1]
    pl([tp["OUT+"], (750, y1)], C['red']); pl([(712, y1), bst["VIN>"]], C['red'])
    S.circle(748, y1, 3, "white", C['ink'], 1.2); S.circle(714, y1, 3, "white", C['ink'], 1.2)
    S.line(716, y1, 746, y1 - 12, C['ink'], 1.6)
    S.text(731, y1 - 18, "SW1 power", 10, anchor="middle", weight="bold")
    pl([tp["OUT−"], bst["GND >"]], C['black'])
    pl([tp["USB-C"], (760, tp["USB-C"][1]), (760, tp["USB-C"][1] + 34)], C['grey'], 1.4)
    S.text(760, tp["USB-C"][1] + 48, "CHARGE port (rear cap)", 10, C['note'], "middle")
    pl([bst["VOUT"], (470, bst["VOUT"][1]), (470, nano["VIN"][1]), nano["VIN"]], C['red'])
    S.text(474, sy + 260, "5 V", 10, C['red'], weight="bold")
    pl([bst["GND"], (490, bst["GND"][1]), (490, nano["GND"][1]), nano["GND"]], C['black'])
    # button SW2: D2 -> button -> GND
    yd, yg = nano["D2"][1], nano["GND "][1]
    pl([nano["D2"], (420, yd)], C['blue'])
    S.circle(418, yd, 3, "white", C['ink'], 1.2); S.circle(382, yd, 3, "white", C['ink'], 1.2)
    S.line(380, yd - 9, 420, yd - 9, C['ink'], 1.6); S.line(400, yd - 9, 400, yd - 18, C['ink'], 1.6)
    pl([(379, yd), (360, yd), (360, yg), nano["GND "]], C['black'])
    S.text(400, yd - 24, "SW2 pen-down (D2, INPUT_PULLUP)", 10, anchor="middle", weight="bold")
    # FSR divider
    y3, ya, yg2 = nano["3V3>"][1], nano["A0>"][1], nano["GND>"][1]
    fx = 920; bus = sy + 200
    pl([nano["3V3>"], (760, y3), (760, sy + 10), (fx, sy + 10), (fx, sy + 22)], C['orange'])
    S.rect(fx - 7, sy + 22, 14, 34, C['fsr'], C['ink'], 1)
    S.text(fx + 14, sy + 43, "FSR 400", 10, weight="bold")
    node = sy + 76
    pl([(fx, sy + 56), (fx, node)], C['yellow'])
    pl([nano["A0>"], (860, ya), (860, node), (fx, node)], C['yellow'])
    S.circle(fx, node, 3.2, C['ink'])
    S.rect(fx - 7, node + 14, 14, 34, "#c9b38a", C['ink'], 1)
    pl([(fx, node), (fx, node + 14)], C['yellow'])
    S.text(fx + 14, node + 35, "10 kΩ", 10, weight="bold")
    pl([(fx, node + 48), (fx, bus)], C['black'])
    pl([(fx, node), (1000, node), (1000, node + 30)], C['yellow'])
    S.line(988, node + 30, 1012, node + 30, C['ink'], 2.2); S.line(988, node + 37, 1012, node + 37, C['ink'], 2.2)
    pl([(1000, node + 37), (1000, bus), (fx, bus)], C['black'])
    S.text(1018, node + 37, "0.1 µF", 10, weight="bold")
    pl([nano["GND>"], (820, yg2), (820, bus), (fx, bus)], C['black'])
    pl([nano["USB>"], (740, nano["USB>"][1]), (740, sy + 215)], C['fpc'], 3)
    S.text(740, sy + 230, "FPC extension to DATA port (rear cap)", 10, C['note'], "middle")

    lx, ly = 40, sy + 40
    S.text(lx, ly, "Wire colours", 12, weight="bold")
    for i, (col, t) in enumerate(((C['red'], "5 V, boost to VIN"), (C['black'], "GND"), (C['orange'], "3V3 to FSR"),
                                  (C['yellow'], "A0, FSR divider"), (C['blue'], "D2, button"), (C['fpc'], "USB FPC ribbon"))):
        S.line(lx, ly + 20 + i * 18, lx + 26, ly + 20 + i * 18, col, 3)
        S.text(lx + 34, ly + 24 + i * 18, t, 10)
    rules = [
        "Rules",
        "• FSR goes to 3V3, never 5V (nRF52840 pins max ≈ 3.6 V).",
        "• Boost 5 V goes to VIN only. Check the VIN range",
        "   for your board revision first.",
        "• SW1 sits after the charger, so the pen still charges",
        "   when switched off.",
        "• Turn SW1 off while the DATA cable is plugged in,",
        "   so USB and the boost don't both power the board.",
        "• Never connect the battery to the 3V3 pin.",
    ]
    for i, r in enumerate(rules):
        S.text(40 + (10 if r.startswith("   ") else 0), sy + 260 + i * 18, r, 12 if i == 0 else 10.5, weight="bold" if i == 0 else "normal")
    S.save("04_wiring.svg")


sheet1(); sheet2(); sheet3(); sheet4()
print("ok")
