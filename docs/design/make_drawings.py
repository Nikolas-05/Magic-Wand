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
               f"<text x='{self.w-24}' y='{self.h-14}' {FONT} font-size='10' fill='{C['note']}' text-anchor='end'>Magic Wand pen, rev D sketch, 2026-11-10. All dimensions in mm. Not to scale when printed; use the numbers.</text></svg>")
        with open(os.path.join(OUT, name), "w") as f:
            f.write(svg)

# ---------------------------------------------------------------- geometry (mm)
L = 166          # overall length (rev D)
R = 15.0         # outer radius (rev D: Ø30 body)
RI = 13.0        # inner radius (Ø26 bore)
FO = 14.0        # outer grip flat (y)
FI = 12.4        # inner face under the grip flat (1.6 wall under the FSR)
LAPR = 14.0      # shell end stepped to Ø28 under the cap sleeve
SZ = 8.0         # screw bosses at z = ±8
TIP = 20         # tip cone length
GRIP = (22, 44)  # flat for the index finger
FSR_X = 31       # FSR centre, 31 mm from tip
BTN_X = 36       # thumb button
DN = 24          # Nano shift vs rev B (Nano was at 50-95)
NANO = (74, 119) # Nano 33 BLE Sense Rev2, 45 x 18, USB end at 119
PCB_Y = (-2.0, -1.0)
# Spektrum SPMX8001S30 1S 800 mAh, 51 x 24 x 8, standing ON EDGE under the grip
BAT = (18.6, 69.6)
BAT_W, BAT_T = 8.0, 24.0       # BAT_W = across (z), BAT_T = height (y)
BAT_Y = (-12.1, 11.9)
DP = -30         # power-bay shift vs rev B
TP = (138, 164)  # TP4056 USB-C module 26 x 17, USB-C face against the cap wall
TP_Y = (-4.0, -2.4)
BST = (140, 155.2) # Pololu U1V11F5 15.2 x 11.4
BST_Y = (2.6, 3.6)
SW_X = 135.5     # slide switch, side wall
CAP = (154, 166)  # cap seam at 154; cap sleeve laps over the shell to 158
SHELL_END = 158
RIBS = [(70.5, 72), (129, 130)]
SCREWS = [26, 71.25, 129.25]
CONN = (40, 48.5)  # FSR 2-pin connector, in the side gap beside the battery

def longsection(S, ox, oy, s, labels=True, layer="all", dy_top=0, dy_bot=0, dx_cap=0, explode=False):
    """Longitudinal section on the vertical mid-plane. layer: all | top | bottom | parts | cap"""
    X = lambda x: ox + x * s
    Y = lambda y: oy - y * s

    def shell_outline(half):
        # outer + inner outline as one even-odd path for a half (top: y>=-1, bottom: y<=-1)
        split = -1.0
        if half == "top":
            outer = (f"M{X(18)},{Y(split)} L{X(1.0)},{Y(split)} "  # tip: top half holds the cone above split
                     f"Q{X(0)},{Y(0)} {X(1.2)},{Y(1.3)} L{X(TIP)},{Y(R)} L{X(GRIP[0])},{Y(FO)} L{X(GRIP[1])},{Y(FO)} "
                     f"L{X(GRIP[1]+2)},{Y(R)} L{X(CAP[0])},{Y(R)} L{X(CAP[0])},{Y(LAPR)} L{X(SHELL_END)},{Y(LAPR)} "
                     f"L{X(SHELL_END)},{Y(RI)} L{X(GRIP[1]+2)},{Y(RI)} L{X(GRIP[1])},{Y(FI)} L{X(GRIP[0])},{Y(FI)} "
                     f"L{X(TIP)},{Y(RI)} L{X(18)},{Y(RI)} Z")
        else:
            outer = (f"M{X(18)},{Y(split)} L{X(1.0)},{Y(split)} Q{X(0)},{Y(-1.6)} {X(1.2)},{Y(-1.6)} "
                     f"L{X(TIP)},{Y(-R)} L{X(CAP[0])},{Y(-R)} L{X(CAP[0])},{Y(-LAPR)} L{X(SHELL_END)},{Y(-LAPR)} "
                     f"L{X(SHELL_END)},{Y(-RI)} L{X(18)},{Y(-RI)} Z")
        return outer

    def ribs(half):
        for a, b in RIBS:
            if half == "top":
                S.rect(X(a), Y(RI), (b - a) * s, 3 * s, "url(#hatch)", C['shellE'], 0.8)
            else:
                S.rect(X(a), Y(-RI + 3.5), (b - a) * s, 3.5 * s, "url(#hatch)", C['shellE'], 0.8)

    def bosses():
        for x in SCREWS:
            # screw from below into boss in top half: shown dashed (off-plane, beside the parts)
            S.rect(X(x - 1), Y(4), 2 * s, (R + 2.2) * s, "none", C['shellE'], 0.8, dash="3,2")
            S.rect(X(x - 1.9), Y(-R + 1.8), 3.8 * s, 1.4 * s, "none", C['shellE'], 0.8, dash="3,2")

    if layer in ("all", "top"):
        g = f"<g transform='translate(0,{-dy_top})'>"
        S.add(g)
        S.path(shell_outline("top"), "url(#hatch)", C['shellE'], 1.2)
        ribs("top")
        # FSR pocket + FSR + puck on the flat
        S.rect(X(FSR_X - 4.2), Y(FO), 8.4 * s, 0.5 * s, "white", C['shellE'], 0.6)
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
               f"L{X(CAP[0])},{Y(-LAPR)} L{X(SHELL_END)},{Y(-LAPR)} L{X(SHELL_END)},{Y(-RI)} L{X(CAP[1]-2)},{Y(-RI)} "
               f"L{X(CAP[1]-2)},{Y(RI)} L{X(SHELL_END)},{Y(RI)} L{X(SHELL_END)},{Y(LAPR)} L{X(CAP[0])},{Y(LAPR)} Z")
        S.path(cap, "url(#hatch)", C['shellE'], 1.2)
        # port openings in the end wall
        for yt, h in ((0.9, 3.4), (6.6, 3.0)):   # USB-C, micro-USB: 0.8 mm web + 1.2 mm outside spot-face
            S.rect(X(CAP[1] - 1.2), Y(yt + 1.5), 1.2 * s, (h + 3) * s, "white", C['ink'], 0.6)
            S.rect(X(CAP[1] - 2), Y(yt), 2 * s, h * s, "white", C['ink'], 0.6)
        S.add("</g>")

    if layer in ("all", "parts"):
        N = lambda x: x + DN
        # FSR on the flat + puck; tail runs to the side (off-plane, dashed) into the connector beside the battery
        S.rect(X(FSR_X - 3.8), Y(FO - 0.1), 7.6 * s, 0.4 * s, C['fsr'], C['ink'], 0.5)
        S.path(f"M{X(FSR_X-3)},{Y(FO+0.3)} Q{X(FSR_X)},{Y(FO+3.4)} {X(FSR_X+3)},{Y(FO+0.3)} Z", C['puck'], C['ink'], 0.7)
        S.path(f"M{X(FSR_X+3.8)},{Y(FO+0.1)} L{X(36)},{Y(FO+0.1)} L{X(37)},{Y(FI-1)} L{X(38.5)},{Y(4.0)} L{X(CONN[0])},{Y(4.0)}", "none", C['fsr'], 1.6, dash="4,2")
        S.rect(X(CONN[0]), Y(5.2), (CONN[1] - CONN[0]) * s, 2.5 * s, "none", C['comp'], 1.2, dash="4,2")
        # battery standing on edge
        S.rect(X(BAT[0]), Y(BAT_Y[1]), (BAT[1] - BAT[0]) * s, BAT_T * s, C['bat'], C['batE'], 1, rx=4)
        S.rect(X(BAT[1] - 2.5), Y(4), 2.5 * s, 8 * s, "#d8dde4", C['batE'], 0.6)  # protection PCB end
        # thumb button (on side wall, off-plane) dashed
        S.rect(X(BTN_X - 3), Y(3), 6 * s, 6 * s, "none", C['ink'], 0.9, dash="3,2")
        S.circle(X(BTN_X), Y(0), 1.75 * s, "none", C['ink'], 0.9, dash="3,2")
        # Nano PCB + parts
        S.rect(X(NANO[0]), Y(PCB_Y[1]), 45 * s, 1.0 * s, C['pcb'], C['pcbE'], 0.8)
        S.rect(X(N(60)), Y(1.2), 10 * s, 2.2 * s, "#bfc6cf", C['ink'], 0.6)   # NINA-B306 module
        S.rect(X(N(74)), Y(0.0), 3 * s, 1.0 * s, C['comp'])                     # BMI270
        S.rect(X(N(79)), Y(0.0), 2 * s, 1.0 * s, C['comp'])                     # BMM150
        S.rect(X(N(84)), Y(0.4), 3 * s, 1.4 * s, C['comp'])
        S.rect(X(N(89.5)), Y(1.6), 6.5 * s, 2.6 * s, "#c8ccd2", C['ink'], 0.7)  # micro-USB socket
        # FPC micro-USB extension: male plug + ribbon over the power bay + female end in cap
        S.rect(X(N(96)), Y(2.6), 8.5 * s, 4.0 * s, C['comp'], None, rx=1)
        S.path(f"M{X(N(104.5))},{Y(1.5)} L{X(N(106))},{Y(6.4)} L{X(SHELL_END-2)},{Y(6.4)} L{X(SHELL_END)},{Y(5.1)}", "none", C['fpc'], 0.4 * s)
        S.rect(X(SHELL_END), Y(6.6), 6 * s, 3.0 * s, "#c8ccd2", C['ink'], 0.7)
        # TP4056 + USB-C
        S.rect(X(TP[0]), Y(TP_Y[1]), 26 * s, 1.6 * s, C['tp'], C['ink'], 0.7)
        S.rect(X(TP[0] + 6), Y(-1.4), 5 * s, 1.0 * s, C['comp'])
        S.rect(X(TP[1] - 3.7), Y(0.8), 3.7 * s, 3.2 * s, "#c8ccd2", C['ink'], 0.7)
        # boost on foam over the TP4056
        S.rect(X(BST[0]), Y(BST_Y[1]), 15.2 * s, 1.0 * s, C['boost'], C['ink'], 0.7)
        S.rect(X(BST[0] + 1), Y(BST_Y[0]), 13 * s, 1.6 * s, "#f3e6b3", C['ink'], 0.4)   # foam tape
        S.rect(X(BST[0] + 5), Y(4.6), 3 * s, 1.0 * s, C['comp'])
        # slide switch on side wall (off-plane)
        S.rect(X(SW_X - 4.3), Y(1.8), 8.6 * s, 3.6 * s, "none", C['sw'], 0.9, dash="3,2")
        # wires: under the Nano in the channel, then beside the battery (off-plane, dashed)
        wy = [-9.2, -10.2]
        S.path(f"M{X(BST[0])},{Y(3.0)} L{X(BST[0]-3)},{Y(1)} L{X(BST[0]-3)},{Y(wy[0])} L{X(N(54.7))},{Y(wy[0])} L{X(N(54.7))},{Y(-2)}", "none", C['red'], 1.6)
        S.path(f"M{X(BST[0])},{Y(2.8)} L{X(BST[0]-2.4)},{Y(0.8)} L{X(BST[0]-2.4)},{Y(wy[1])} L{X(N(57.2))},{Y(wy[1])} L{X(N(57.2))},{Y(-2)}", "none", C['black'], 1.6)
        S.path(f"M{X(BAT[1])},{Y(-5)} L{X(TP[0]+1)},{Y(-9.0)} L{X(TP[0]+1)},{Y(-4)}", "none", C['red'], 1.3, dash="5,3")
        for col, y0, yl, xp in ((C['yellow'], 3, -5, 82.7), (C['orange'], 2.4, -5.9, 87.8)):
            S.path(f"M{X(CONN[1])},{Y(y0)} L{X(CONN[1]+2)},{Y(yl)} L{X(72)},{Y(yl)}", "none", col, 1.4, dash="5,3")
            S.path(f"M{X(72)},{Y(yl)} L{X(N(xp))},{Y(yl)} L{X(N(xp))},{Y(-2)}", "none", col, 1.6)
        S.path(f"M{X(BTN_X+3)},{Y(-2)} L{X(BTN_X+5)},{Y(-6.4)} L{X(72)},{Y(-6.4)}", "none", C['blue'], 1.4, dash="5,3")
        S.path(f"M{X(72)},{Y(-6.4)} L{X(N(64.9))},{Y(-6.4)} L{X(N(64.9))},{Y(-2)}", "none", C['blue'], 1.6)


# ---------------------------------------------------------------- sheet 1: side section + plan
def sheet1():
    s = 5.0
    N_IMU = 76 + DN
    S = Sheet(1240, 910, "Magic Wand pen: side section and top view",
              "Arduino Nano 33 BLE Sense Rev2 (45 x 18 mm), FSR 400 squeeze sensor, D2 thumb button, 1-cell LiPo + TP4056 charger + 5 V boost")
    ox, oy = 90, 290
    X = lambda x: ox + x * s
    Y = lambda y: oy - y * s
    S.text(ox, 112, "VIEW 1: LONGITUDINAL SECTION ON THE CENTRE PLANE (tip left, USB end right; dashed = off-plane parts)", 12, weight="bold")
    longsection(S, ox, oy, s)
    S.line(X(-4), oy, X(L + 4), oy, C['grey'], 0.6, dash="10,3,2,3")
    S.line(X(10), Y(-1), X(SHELL_END), Y(-1), C['shellE'], 0.6, dash="2,3")
    top = lambda r: Y(R) - 22 - 24 * r
    bot = lambda r: Y(-R) + 24 + 24 * r
    S.callout(X(FSR_X), Y(FO + 2.5), X(4), top(2), "FSR 400 + puck, under the index finger", anchor="start")
    S.callout(X(44), Y(4), X(40), top(0), "FSR plug + 10 kΩ / 0.1 µF beside the cell", anchor="start")
    S.callout(X(90), Y(0.3), X(86), top(1), "Nano 33 BLE Sense Rev2 on side rails", anchor="start")
    S.callout(X(125), Y(1), X(118), top(0), "micro-USB FPC to DATA port", anchor="start")
    S.callout(X(BST[0] + 7), Y(3.4), X(140), top(2), "5 V boost on foam", anchor="start")
    S.callout(X(BTN_X), Y(-1.75), X(2), bot(0), "6x6 tact button, thumb side (D2)", anchor="start")
    S.callout(X(45), Y(-4), X(10), bot(2), "Spektrum 800 mAh LiPo (51 x 24 x 8), on edge", anchor="start")
    S.callout(X(N_IMU), Y(-0.5), X(76), bot(1), "BMI270 + BMM150 IMU, ≈ 71 mm behind the FSR", anchor="start")
    S.callout(X(110), Y(-9.6), X(98), bot(0), "wire channel under the PCB", anchor="start")
    S.callout(X(SW_X), Y(-0.3), X(128), bot(2), "slide switch (side wall)", anchor="start")
    S.callout(X(TP[0] + 14), Y(-3.2), X(140), bot(1), "TP4056 USB-C charger", anchor="start")
    S.callout(X(L - 2), Y(5), X(L + 4), top(0), "rear cap: DATA +\nCHARGE ports", anchor="start")
    S.text(X(L) + 6, Y(-1) + 4, "split", 9, C['shellE'])
    yc = bot(3) + 14
    chain = [(0, BAT[0]), (BAT[0], BAT[1]), (BAT[1], NANO[0]), (NANO[0], NANO[1]), (NANO[1], CAP[0]), (CAP[0], CAP[1])]
    labs = ["tip", "battery (under grip)", "", "Nano bay", "power bay", "cap"]
    for (a, b), t in zip(chain, labs):
        S.dimh(X(a), X(b), yc, f"{b-a:g}", Y(-R) + 4, Y(-R) + 4)
        S.text((X(a) + X(b)) / 2, yc + 16, t, 10, C['note'], "middle")
    S.dimh(X(0), X(L), yc + 40, f"overall {L}")
    S.dimv(X(L) + 34, Y(R), Y(-R), f"Ø{2*R:g}", X(L) + 2, left=False)
    S.dimv(X(L) + 78, Y(RI), Y(-RI), f"Ø{2*RI:g} bore", None, left=False)
    S.line(X(L) + 74, Y(RI), X(L) + 82, Y(RI), C['dim'], 0.7); S.line(X(L) + 74, Y(-RI), X(L) + 82, Y(-RI), C['dim'], 0.7)

    # ---- plan view
    oy2 = 720
    Z = lambda z: oy2 + z * s
    S.text(ox, oy2 - 128, "VIEW 2: TOP VIEW (outside). Section cuts A–D and rear view E are on sheet 2.", 12, weight="bold")
    outline = (f"M{X(TIP)},{Z(-R)} L{X(CAP[1]-3)},{Z(-R)} Q{X(CAP[1])},{Z(-R)} {X(CAP[1])},{Z(-R+3)} L{X(CAP[1])},{Z(R-3)} "
               f"Q{X(CAP[1])},{Z(R)} {X(CAP[1]-3)},{Z(R)} L{X(TIP)},{Z(R)} L{X(1.2)},{Z(1.5)} Q{X(0)},{Z(0)} {X(1.2)},{Z(-1.5)} Z")
    S.path(outline, C['shell'], C['shellE'], 1.3)
    S.line(X(CAP[0]), Z(-R), X(CAP[0]), Z(R), C['shellE'], 1)
    S.line(X(TIP), Z(-R), X(TIP), Z(R), C['shellE'], 0.6, dash="3,2")
    S.rect(X(GRIP[0]), Z(-5.4), (GRIP[1] - GRIP[0]) * s, 10.8 * s, "#cfd5de", C['shellE'], 0.8, rx=6)
    S.circle(X(FSR_X), Z(0), 3.8 * s, C['fsr'], C['ink'], 0.6)
    S.circle(X(FSR_X), Z(0), 3 * s, C['puck'], C['ink'], 0.6)
    S.rect(X(BTN_X - 1.75), Z(R - 0.2), 3.5 * s, 1.0 * s, C['ink'], None, rx=2)
    S.rect(X(SW_X - 1.5), Z(-R - 1.5), 3 * s, 1.5 * s, C['sw'], None, rx=1)
    for x in SCREWS:
        S.circle(X(x), Z(-SZ), 1.1 * s, "white", C['shellE'], 0.8, dash="2,2")
        S.circle(X(x), Z(SZ), 1.1 * s, "white", C['shellE'], 0.8, dash="2,2")
    S.line(X(-4), Z(0), X(L + 4), Z(0), C['grey'], 0.6, dash="10,3,2,3")
    for lab, x in (("A", FSR_X), ("B", 96), ("C", 58), ("D", 148)):
        S.line(X(x), Z(-R - 4), X(x), Z(R + 4), C['dim'], 1, dash="12,3,2,3")
        S.text(X(x) + 6, Z(-R - 3), lab, 13, C['dim'], "start", "bold")
        S.text(X(x) + 6, Z(R + 4) + 6, lab, 13, C['dim'], "start", "bold")
    S.line(X(L) + 10, Z(0), X(L) + 40, Z(0), C['dim'], 1, marker="arr")
    S.text(X(L) + 44, Z(0) + 4, "E", 13, C['dim'], weight="bold")
    S.callout(X(FSR_X + 3), Z(-3.5), X(44), Z(-R) - 42, "11 mm wide flat, 1 mm deep, with Ø8.4 x 0.5 FSR pocket", anchor="start")
    S.callout(X(SW_X), Z(-R - 1.5), X(104), Z(-R) - 22, "power switch, opposite side", anchor="start")
    S.callout(X(BTN_X), Z(R + 0.8), X(50), Z(R) + 30, "thumb button, stands 1 mm proud", anchor="start")
    S.callout(X(SCREWS[1]), Z(SZ + 1.1), X(104), Z(R) + 30, "M2 screws from below, 6x (dashed)", anchor="start")
    S.dimv(X(0) - 18, Z(-R), Z(R), f"{2*R:g}", X(TIP) - 2)
    S.dimh(X(0), X(FSR_X), Z(R) + 62, f"{FSR_X}", Z(0), Z(0))
    S.text(X(FSR_X) + 8, Z(R) + 66, "FSR centre from the tip (FORCE_SENSOR.md: 2–4 cm)", 10, C['dim'])
    S.dimh(X(GRIP[0]), X(GRIP[1]), Z(R) + 92, f"grip flat {GRIP[1]-GRIP[0]}", Z(5.4), Z(5.4))
    S.save("01_side_and_top.svg")


# ---------------------------------------------------------------- sheet 2: sections
def ring(S, cx, cy, s, flat=False):
    X = lambda z: cx + z * s
    Y = lambda y: cy - y * s
    if flat:
        import math
        a = math.degrees(math.asin(5 / R)); ai = math.degrees(math.asin(4.4 / RI))
        # outer with flat at y=11 (|z|<=5 approx), inner with flat at y=9
        zo = (R * R - FO * FO) ** 0.5; zi = (RI * RI - FI * FI) ** 0.5
        d = (f"M{X(-zo)},{Y(FO)} L{X(zo)},{Y(FO)} A{R*s},{R*s} 0 1 1 {X(-zo)},{Y(FO)} Z "
             f"M{X(-zi)},{Y(FI)} A{RI*s},{RI*s} 0 1 0 {X(zi)},{Y(FI)} Z")
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
    s = 6.5
    S = Sheet(1180, 760, "Magic Wand pen: cross-sections A–D and rear view E",
              "Looking from the rear toward the tip. Thumb side is on the left. Dashed line = split between top and bottom shell (y = −1 mm).")
    cy = 330
    cxs = [130, 365, 600, 835, 1065]
    titles = ["A–A  grip, x = 31", "B–B  Nano, x = 96", "C–C  battery, x = 58", "D–D  power bay, x = 148", "E  rear cap (outside)"]
    for cx, t in zip(cxs, titles):
        S.text(cx, 150, t, 13, anchor="middle", weight="bold")
    X = lambda cx, z: cx + z * s
    Y = lambda y: cy - y * s
    # A
    cx = cxs[0]
    ring(S, cx, cy, s, flat=True)
    S.rect(X(cx, -3.8), Y(FO), 7.6 * s, 0.45 * s, C['fsr'], C['ink'], 0.5)
    S.path(f"M{X(cx,-3)},{Y(FO+0.4)} Q{X(cx,0)},{Y(FO+3.5)} {X(cx,3)},{Y(FO+0.4)} Z", C['puck'], C['ink'], 0.7)
    S.rect(X(cx, -12.6), Y(3), 3.6 * s, 6 * s, C['comp'], None, rx=1)       # tact switch body
    S.rect(X(cx, -15.9), Y(1.75), 3.4 * s, 3.5 * s, C['ink'], None, rx=3)  # actuator through wall
    S.rect(X(cx, -9.2), Y(2.5), 1.2 * s, 5 * s, "url(#hatch)", C['shellE'], 0.6)  # switch backing rib
    S.rect(X(cx, -4), Y(BAT_Y[1]), 8 * s, 24 * s, C['bat'], C['batE'], 1, rx=6)
    for z, y, col in ((-5.6, -6.5, C['blue']), (-6.2, -7.8, C['black']), (5.6, -6.5, C['red']), (6.2, -7.8, C['black'])):
        wire(S, cx, cy, s, z, y, col)
    S.callout(X(cx, 2), Y(FO + 2), X(cx, 4), Y(R + 5), "FSR + puck", 10, "start")
    S.callout(X(cx, -15), Y(-1.5), X(cx, -R - 1), Y(-R - 3.5), "thumb button (D2)", 10, "start")
    S.callout(X(cx, -8.6), Y(-2.2), X(cx, -R - 1), Y(-R - 6), "backing rib takes the push", 10, "start")
    S.callout(X(cx, 1.5), Y(-4), X(cx, 1), Y(-R - 8.5), "800 mAh pack on edge", 10, "start")
    S.dimv(X(cx, R) + 10, Y(FO), Y(-R), f"{FO + R:g}", X(cx, 6), left=False)
    # B
    cx = cxs[1]
    ring(S, cx, cy, s)
    for zz in (-1, 1):  # side rail blocks (bottom shell) under the PCB edges
        S.rect(X(cx, 8.5 if zz > 0 else -12.85), Y(-2), 4.35 * s, 2.4 * s, "url(#hatch)", C['shellE'], 0.6)
    S.rect(X(cx, -9), Y(-1), 18 * s, 1 * s, C['pcb'], C['pcbE'], 0.8)
    S.rect(X(cx, -5), Y(1.2), 10 * s, 2.2 * s, "#bfc6cf", C['ink'], 0.6)
    S.rect(X(cx, -6.5), Y(2.5) , 13 * s, 0.01, "none")
    for zz in (-1, 1):   # hold-down fingers from the top shell press on the PCB edge
        z0 = 8.5 if zz > 0 else -9.6
        S.rect(X(cx, z0), Y(9.3), 1.1 * s, 10.3 * s, "url(#hatch)", C['shellE'], 0.6)
    for z, col in ((-7.62, C['blue']), (7.62, C['red'])):
        S.circle(X(cx, z), Y(-1.5), 0.5 * s, "#d4af37", C['ink'], 0.5)
    for z, y, col in ((-3.0, -6.4, C['blue']), (-1.8, -7.6, C['black']), (-0.6, -7.2, C['red']), (0.6, -8.2, C['black']), (1.8, -5.0, C['yellow']), (3.0, -5.9, C['orange'])):
        wire(S, cx, cy, s, z, y, col)
    S.callout(X(cx, 9.0), Y(2), X(cx, 2), Y(R + 5), "hold-down fingers", 10, "start")
    S.callout(X(cx, -3), Y(0.6), X(cx, -2), Y(R + 3.5), "radio module", 10, "end")
    S.callout(X(cx, 10.5), Y(-2.8), X(cx, -R - 1), Y(-R - 3.5), "PCB 18 x 1.0 on side rail blocks", 10, "start")
    S.callout(X(cx, -1.8), Y(-7.6), X(cx, -R - 1), Y(-R - 6), "wires to pads, from below", 10, "start")
    S.dimh(X(cx, -9), X(cx, 9), Y(-R) + 70, "18", Y(-2) + 2, Y(-2) + 2)
    # C
    cx = cxs[2]
    ring(S, cx, cy, s)
    for sgn in (-1, 1):   # side guide ribs in the top and bottom shell
        a, b = sorted((sgn * 4.2, sgn * 5.3))
        ty = (RI * RI - 5.3 ** 2) ** 0.5
        S.rect(X(cx, a), Y(ty + 0.2), (b - a) * s, (ty + 0.2 + 0.6) * s, "url(#hatch)", C['shellE'], 0.6)
        S.rect(X(cx, a), Y(-1.4), (b - a) * s, (ty + 0.2 - 1.4) * s, "url(#hatch)", C['shellE'], 0.6)
    S.rect(X(cx, -4), Y(BAT_Y[1]), 8 * s, 24 * s, C['bat'], C['batE'], 1, rx=6)
    for z, y, col in ((-7.0, -3.0, C['blue']), (-7.4, -4.6, C['black']), (7.0, -3.0, C['yellow']), (7.4, -4.6, C['orange']),
                      (7.8, -6.2, C['black']), (-7.8, -6.2, C['red']), (-7.0, 3.0, C['red']), (7.0, 3.0, C['black'])):
        wire(S, cx, cy, s, z, y, col)
    S.callout(X(cx, 1), Y(6), X(cx, 3), Y(R + 5), "Spektrum 800 mAh on edge", 10, "start")
    S.callout(X(cx, -4.75), Y(6), X(cx, -2), Y(R + 3.5), "guide ribs", 10, "end")
    S.callout(X(cx, 7.4), Y(-4.6), X(cx, -R - 1), Y(-R - 3.5), "wires run in the side gaps", 10, "start")
    S.dimh(X(cx, -4), X(cx, 4), Y(-R) + 70, "8", Y(BAT_Y[0]) + 2, Y(BAT_Y[0]) + 2)
    S.dimv(X(cx, R) + 10, Y(BAT_Y[1]), Y(BAT_Y[0]), "24", X(cx, 4), left=False)
    # D
    cx = cxs[3]
    ring(S, cx, cy, s)
    S.rect(X(cx, -8.5), Y(TP_Y[1]), 17 * s, 1.6 * s, C['tp'], C['ink'], 0.7)
    S.rect(X(cx, -2.5), Y(-1.4), 5 * s, 1.0 * s, C['comp'])
    S.rect(X(cx, -6.5), Y(BST_Y[0]), 13 * s, 1.6 * s, "#f3e6b3", C['ink'], 0.4)
    S.rect(X(cx, -5.7), Y(BST_Y[1]), 11.4 * s, 1.0 * s, C['boost'], C['ink'], 0.7)
    S.rect(X(cx, -1.5), Y(4.6), 3 * s, 1.0 * s, C['comp'])
    S.rect(X(cx, -3.75), Y(6.4), 7.5 * s, 0.4 * s, C['fpc'], C['ink'], 0.4)
    for zz in (-1, 1):   # PCB guide grooves in the bottom shell
        S.rect(X(cx, 8.7 if zz > 0 else -12.4), Y(-2.2), 3.7 * s, 2.0 * s, "url(#hatch)", C['shellE'], 0.6)
    S.callout(X(cx, -4), Y(-3.2), X(cx, -R - 1), Y(-R - 3.5), "TP4056 charger, 17 wide", 10, "start")
    S.callout(X(cx, -3), Y(3.1), X(cx, -2), Y(R + 3.5), "boost, 11.4 wide", 10, "end")
    S.callout(X(cx, 10.5), Y(-2.6), X(cx, 3), Y(R + 5), "PCB guide grooves", 10, "start")
    # E rear view
    cx = cxs[4]
    S.circle(cx, cy, R * s, C['shell'], C['shellE'], 1.3)
    S.circle(cx, cy, (R - 3) * s, "none", C['shellE'], 0.6, dash="3,2")
    S.rect(X(cx, -4.6), Y(0.8), 9.2 * s, 3.4 * s, "white", C['ink'], 1, rx=1.6 * s)
    S.rect(X(cx, -4.0), Y(6.6), 8.0 * s, 3.0 * s, "white", C['ink'], 1, rx=4)
    S.text(cx, Y(-4.2), "CHARGE", 11, anchor="middle", weight="bold")
    S.text(cx, Y(-6.2), "USB-C", 10, C['note'], "middle")
    S.text(cx, Y(9.4), "DATA (micro-USB)", 10, anchor="middle", weight="bold")
    S.text(cx, Y(-R - 3.5), "charge LED: Ø2 window on top of the cap", 10, anchor="middle")
    S.text(cx, Y(-R - 6.5), "USB-C opening 9.2 x 3.4", 10, C['dim'], "middle")
    S.text(cx, Y(-R - 8.5), "micro-USB opening 8.0 x 3.0", 10, C['dim'], "middle")

    # notes block
    ny = 560
    notes = [
        "Why this layout",
        "• Rev D: Ø30 body so the Spektrum 800 mAh pack (51 x 24 x 8) stands on edge under the grip; the Nano follows, the charger is at the back. Pen is 166 mm.",
        "• The FSR lies on a flat, rigid pocket in the top shell. The Nano is clamped on its own rails 43 mm further back, so squeezing the grip cannot flex the board (section 3).",
        "• The thumb button has a backing rib so pressing it doesn't push the switch into the cavity or flex the shell.",
        "• Shell splits at y = −1 mm (top of the PCB). The bottom half carries the Nano rail blocks and wire channel; the top half carries the FSR pocket and the hold-down ribs.",
        "• Bore Ø26 is set by the 24 x 8 pack (diagonal 25.3). The pack leaves 4–8 mm side gaps for the button and wires; the Nano sits on 4 mm side rail blocks.",
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
    S.text(X(60), Y(-R) + 150 + 84, "② BOTTOM SHELL (Nano rail blocks, wire channel, button + switch holes)", 12, anchor="middle", weight="bold")
    longsection(S, ox, oy, s, layer="cap", dx_cap=70)
    S.text(X(CAP[1]) + 70 - 10, Y(R) - 12, "③ REAR CAP", 12, anchor="middle", weight="bold")
    for x in (40, 95, 145):
        S.line(X(x), Y(R) - 125, X(x), Y(R) - 20, C['grey'], 1, dash="5,4", marker="arrk")
        S.line(X(x), Y(-R) + 125, X(x), Y(-R) + 20, C['grey'], 1, dash="5,4", marker="arrk")
    S.line(X(CAP[1]) + 50, oy, X(CAP[1]) + 12, oy, C['grey'], 1, dash="5,4", marker="arrk")
    # screws below bottom shell
    for x in SCREWS:
        sx = X(x); sy = Y(-R) + 150 + 40
        S.rect(sx - 1.9 * s, sy, 3.8 * s, 1.4 * s, C['ink'])
        S.rect(sx - 1 * s, sy - 6 * s, 2 * s, 6 * s, "#9aa0a8", C['ink'], 0.5)
    S.text(X(112), Y(-R) + 150 + 84, "④ M2 x 10 pan-head screws, 6x (two per position, one each side)", 11)
    # numbered part tags on parts row
    tags = [(FSR_X, 16.5, "5"), (BTN_X - 4, -3.5, "6"), (CONN[0] + 4, 5.5, "7"), (92, 3, "8"), (124, 4, "9"),
            (55, 11.5, "10"), (BST[0] + 7, 5.5, "11"), (TP[0] + 20, -3.4, "12"), (SW_X - 5, -1.6, "13")]
    for x, y, t in tags:
        S.circle(X(x), Y(y) - 14, 9, "white", C['ink'], 1)
        S.text(X(x), Y(y) - 10, t, 10, anchor="middle", weight="bold")
        S.line(X(x), Y(y) - 5, X(x), Y(y), C['ink'], 0.6)
    # BOM table
    rows = [
        ("#", "Part", "Size (mm)", "Notes"),
        ("1", "Top shell, printed", "158 x Ø30 half", "PETG/PLA, FSR pocket Ø8.4 x 0.5"),
        ("2", "Bottom shell, printed", "158 x Ø30 half", "Nano rail blocks at y = −2, battery guide ribs, 3 bosses per side"),
        ("3", "Rear cap, printed", "12 x Ø30", "sleeve laps over the shell; port windows, Ø2 LED window"),
        ("4", "M2 x 10 screws", "6 pcs", "self-tapping into printed bosses, or M2 heat-set inserts"),
        ("5", "Interlink FSR 400 short tail + puck", "Ø7.6 x 0.3, tail ≈ 30", "puck: Ø6 TPU dome or hot-glue dot"),
        ("6", "Tact switch 6 x 6, 7 mm stem", "6 x 6 x 7", "D2 to GND, internal pull-up"),
        ("7", "2-pin female header, 10 kΩ, 0.1 µF", "", "FSR divider, heat-shrunk at the connector"),
        ("8", "Arduino Nano 33 BLE Sense Rev2", "45 x 18 x ≈ 5", "no pin headers; wires soldered under the pads"),
        ("9", "Micro-USB FPC extension, male to female", "≈ 50 long, 7.5 wide", "female end glued into the rear cap"),
        ("10", "Spektrum SPMX8001S30 LiPo + 1S protection board", "51 x 24 x 8", "800 mAh, JST-RCY, no built-in PCM: add DW01 board; on edge under the grip"),
        ("11", "Pololu U1V11F5 5 V step-up", "15.2 x 11.4 x 3", "or any ≥ 200 mA 5 V boost that fits"),
        ("12", "TP4056 USB-C charger with DW01 protection", "26 x 17 x 5", "USB-C face against the cap wall; RPROG 2.4 kΩ (≈ 500 mA)"),
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
    outline = (f"M{X(TIP)},{Z(-R)} L{X(CAP[1])},{Z(-R)} L{X(CAP[1])},{Z(R)} L{X(TIP)},{Z(R)} L{X(1.2)},{Z(1.5)} Q{X(0)},{Z(0)} {X(1.2)},{Z(-1.5)} Z")
    S.path(outline, C['shell'], C['shellE'], 1.2)
    S.line(X(CAP[0]), Z(-R), X(CAP[0]), Z(R), C['shellE'], 1)
    S.rect(X(18), Z(-RI), (CAP[1] - 2 - 18) * s, 2 * RI * s, "white", C['shellE'], 0.6)
    for a, b in RIBS:
        S.rect(X(a), Z(-RI), (b - a) * s, 2 * RI * s, "url(#hatch)", C['shellE'], 0.6, op=0.5)
    px = lambda i: 90.3 + DN - i * 2.54
    top_row = ["D13", "3V3", "AREF", "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "5V", "RST", "GND", "VIN"]
    bot_row = ["D12", "D11", "D10", "D9", "D8", "D7", "D6", "D5", "D4", "D3", "D2", "GND", "RST", "RX0", "TX1"]
    P = {("t", n): px(i) for i, n in enumerate(top_row)}
    P.update({("b", n): px(i) for i, n in enumerate(bot_row)})
    def w(pts, col, wd=2.4):
        d = "M" + " L".join(f"{X(a)},{Z(b)}" for a, b in pts)
        S.path(d, "none", col, wd)
    # wires first (they run under the parts)
    w([(CONN[1], -5.4), (P["t", "A0"], -5.4), (P["t", "A0"], -7.62)], C['yellow'])
    w([(CONN[1], -6.4), (P["t", "3V3"] - 1.2, -6.4), (P["t", "3V3"], -7.62)], C['orange'])
    w([(CONN[1], -4.4), (72.5, -4.4), (P["t", "GND"], -6.0), (P["t", "GND"], -7.62)], C['black'])
    w([(BTN_X + 3, 5.6), (P["b", "D2"], 5.6), (P["b", "D2"], 7.62)], C['blue'])
    w([(BTN_X + 3, 4.6), (P["b", "GND"], 4.6), (P["b", "GND"], 7.62)], C['black'])
    w([(BST[0], 1.0), (P["t", "VIN"] - 1.4, 1.0), (P["t", "VIN"] - 1.4, -4.4), (P["t", "VIN"], -6.0), (P["t", "VIN"], -7.62)], C['red'])
    w([(BST[0], 2.4), (P["t", "GND"] + 1.2, 2.4), (P["t", "GND"] + 1.2, -5.6), (P["t", "GND"], -7.0)], C['black'])
    w([(BAT[1], -1.6), (73, -3.4), (TP[0] - 1, -3.4), (TP[0] + 0.5, -6)], C['red'], 1.8)
    w([(BAT[1], 1.6), (73, 3.2), (TP[0] - 1, 3.2), (TP[0] + 0.5, 6)], C['black'], 1.8)
    # parts
    S.rect(X(NANO[0]), Z(-9), 45 * s, 18 * s, C['pcb'], C['pcbE'], 1, rx=3, op=0.55)
    S.rect(X(89.5 + DN), Z(-3.8), 6.5 * s, 7.6 * s, "#c8ccd2", C['ink'], 0.7)
    S.text(X(72.5 + DN), Z(0.4) + 4, "Nano 33 BLE Sense Rev2 (component side up)", 10, C['ink'], "middle", "bold")
    for row, zz in ((top_row, -7.62), (bot_row, 7.62)):
        for i, name in enumerate(row):
            S.circle(X(px(i)), Z(zz), 0.75 * s, "#d4af37", C['ink'], 0.4)
    for (side, name, lift) in (("t", "3V3", 0), ("t", "A0", 0), ("t", "GND", 1), ("t", "VIN", 0), ("b", "D2", 0), ("b", "GND", 1)):
        zz = -7.62 if side == "t" else 7.62
        off = (-8 - 10 * lift) if side == "t" else (15 + 10 * lift)
        S.text(X(P[side, name]), Z(zz) + off, name, 9, C['ink'], "middle", "bold")
    S.text(X(91 + DN), Z(-R) - 6, "USB end", 9, C['note'], "middle")
    S.rect(X(96 + DN), Z(-3.75), (SHELL_END + 6 - 96 - DN) * s, 7.5 * s, "none", C['fpc'], 1.4, dash="6,3")
    S.rect(X(BAT[0]), Z(-BAT_W / 2), (BAT[1] - BAT[0]) * s, BAT_W * s, C['bat'], C['batE'], 1, rx=6, op=0.55)
    S.text(X(44), Z(-R) - 20, "Spektrum 800 mAh on edge (8 wide seen from above)", 10, C['ink'], "middle", "bold")
    S.text(X(138), Z(-R) - 20, "FPC ribbon above the power bay (dashed)", 9.5, C['note'], "middle")
    S.rect(X(TP[0]), Z(-8.5), 26 * s, 17 * s, C['tp'], C['ink'], 0.8, op=0.55)
    S.rect(X(TP[1] - 3.7), Z(-4.5), 3.7 * s, 9 * s, "#c8ccd2", C['ink'], 0.7)
    S.rect(X(BST[0]), Z(-5.7), 15.2 * s, 11.4 * s, C['boost'], C['ink'], 0.8, op=0.75)
    S.text(X(BST[0] + 7.6), Z(-0.5), "BOOST", 9, "white", "middle", "bold")
    S.text(X(TP[0] + 13), Z(7.6) + 3, "TP4056", 9, "white", "middle", "bold")
    S.rect(X(SW_X - 4.3), Z(-R + 0.2), 8.6 * s, 3.6 * s, C['sw'], None, rx=1)
    S.text(X(SW_X), Z(-R) - 6, "SW1", 9, C['note'], "middle", "bold")
    S.circle(X(FSR_X), Z(0), 3.8 * s, C['fsr'], C['ink'], 0.6)
    S.rect(X(FSR_X + 3.8), Z(-2.2), (36 - FSR_X - 3.8) * s, 4.4 * s, C['fsr'])
    S.text(X(FSR_X), Z(-R) - 6, "FSR (in top shell)", 9, C['note'], "middle")
    S.rect(X(CONN[0]), Z(-7.6), (CONN[1] - CONN[0]) * s, 2.5 * s, C['comp'], None, rx=1)
    S.path(f"M{X(36)},{Z(-1)} L{X(38)},{Z(-6.3)} L{X(CONN[0])},{Z(-6.3)}", "none", C['fsr'], 2.4)
    S.rect(X(BTN_X - 3), Z(7.0), 6 * s, 6 * s, C['comp'], None, rx=1)
    S.circle(X(BTN_X), Z(10.0), 1.75 * s, "#555")
    S.text(X(BTN_X), Z(R) + 14, "SW2 button", 9, C['note'], "middle")
    S.text(X(90), Z(R) + 30, "Pad order follows the classic Nano layout; check it against the silkscreen on your board before soldering.", 10.5, C['note'], "middle")

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

# ================================================================ detail sheets (rev B)
import math

def frame(S, x, y, w, h, title, scale):
    S.rect(x, y, w, h, "none", "#b8c0cc", 1, rx=6)
    S.rect(x, y, w, 26, "#eef1f5", None, rx=6)
    S.rect(x, y + 20, w, 6, "#eef1f5")
    S.text(x + 12, y + 18, title, 12.5, weight="bold")
    if scale:
        S.text(x + w - 12, y + 18, f"SCALE {scale}", 11, C['note'], "end")

_clip_n = [0]
def clip_begin(S, x, y, w, h):
    _clip_n[0] += 1
    cid = f"clip{_clip_n[0]}"
    S.add(f"<clipPath id='{cid}'><rect x='{x}' y='{y}' width='{w}' height='{h}'/></clipPath><g clip-path='url(#{cid})'>")
def clip_end(S):
    S.add("</g>")

def poly(S, pts, X, Y, fill, stroke=None, sw=1.0, dash=None):
    d = "M" + " L".join(f"{X(a):.2f},{Y(b):.2f}" for a, b in pts) + " Z"
    S.path(d, fill, stroke or C['shellE'], sw, dash)

HATCH_B = "url(#hatchB)"
def add_hatchB(S):
    S.defs += f"""<defs><pattern id='hatchB' width='6' height='6' patternUnits='userSpaceOnUse' patternTransform='rotate(-45)'>
  <rect width='6' height='6' fill='#e9e2d4'/><line x1='0' y1='0' x2='0' y2='6' stroke='#b8a888' stroke-width='1.2'/></pattern></defs>"""

def legend_shells(S, x, y):
    S.rect(x, y - 10, 22, 12, "url(#hatch)", C['shellE'], 0.8); S.text(x + 28, y, "top shell", 10.5)
    S.rect(x + 100, y - 10, 22, 12, HATCH_B, "#8c7b5a", 0.8); S.text(x + 128, y, "bottom shell", 10.5)
    S.rect(x + 230, y - 10, 22, 12, "url(#hatchC)", "#6c8a6c", 0.8); S.text(x + 258, y, "rear cap", 10.5)

def add_hatchC(S):
    S.defs += f"""<defs><pattern id='hatchC' width='5' height='5' patternUnits='userSpaceOnUse' patternTransform='rotate(45)'>
  <rect width='5' height='5' fill='#dfeadf'/><line x1='0' y1='0' x2='0' y2='5' stroke='#8fb08f' stroke-width='1.2'/></pattern></defs>"""

# ---------------------------------------------------------------- sheet 5
def sheet5():
    S = Sheet(1240, 1010, "Magic Wand pen: inner features 1, grip and Nano bay",
              "Enlarged details of the printed features that hold each part. Dimensions in mm; 3D-print clearances are included in the numbers.")
    add_hatchB(S); add_hatchC(S)
    legend_shells(S, 860, 52)

    # ---------- DETAIL 1: grip long section x 16..53
    fx, fy, fw, fh = 30, 80, 690, 440
    frame(S, fx, fy, fw, fh, "DETAIL 1  Grip: FSR pocket, tail path, battery underneath (long section)", "2.6:1")
    s = 10.5
    ox = fx + 40 - 16 * s; oy = fy + 80 + 15 * s
    X = lambda x: ox + x * s
    Y = lambda y: oy - y * s
    clip_begin(S, fx + 2, fy + 27, fw - 4, fh - 30)
    yc = lambda x: 1.3 + (x - 1.2) * ((R - 1.3) / 18.8)
    top = [(15.5, -1), (15.5, yc(15.5)), (20, R), (22, FO), (44, FO), (46, R), (53.5, R), (53.5, RI), (46, RI), (44, FI), (22, FI), (20, RI), (18, RI), (18, -1)]
    poly(S, top, X, Y, "url(#hatch)", C['shellE'], 1.1)
    bot = [(15.5, -1), (18, -1), (18, -RI), (53.5, -RI), (53.5, -R), (20, -R), (15.5, -yc(15.5))]
    poly(S, bot, X, Y, HATCH_B, "#8c7b5a", 1.1)
    # pocket + tail groove + slot (cut-outs)
    S.rect(X(FSR_X - 4.2), Y(FO), 8.4 * s, 0.5 * s, "white", C['shellE'], 0.6)
    S.rect(X(FSR_X + 4.2), Y(FO), (37.2 - FSR_X - 4.2) * s, 0.5 * s, "white", C['shellE'], 0.6)
    S.path(f"M{X(35.6)},{Y(FO-0.5)} L{X(35.6)},{Y(FI+0.6)} Q{X(35.6)},{Y(FI)} {X(36.2)},{Y(FI)} L{X(37.2)},{Y(FI)} L{X(37.2)},{Y(FO-0.5)} Z", "white", C['shellE'], 0.6)
    # battery standing on edge in the centre
    S.rect(X(BAT[0]), Y(BAT_Y[1]), (53.5 - BAT[0]) * s, BAT_T * s, C['bat'], C['batE'], 1, rx=8)
    S.text(X(35), Y(-5.5) + 4, "Spektrum 800 mAh on edge (continues to x = 69.6)", 11, C['batE'], "middle", "bold")
    # FSR, adhesive, puck, cover
    S.rect(X(FSR_X - 3.8), Y(FO - 0.4), 7.6 * s, 0.1 * s, "#f3e6b3")
    S.rect(X(FSR_X - 3.8), Y(FO - 0.1), 7.6 * s, 0.3 * s, C['fsr'], C['ink'], 0.5)
    S.path(f"M{X(FSR_X-3)},{Y(FO-0.1)} L{X(FSR_X-3)},{Y(FO+0.6)} Q{X(FSR_X-3)},{Y(FO+1.9)} {X(FSR_X)},{Y(FO+1.9)} Q{X(FSR_X+3)},{Y(FO+1.9)} {X(FSR_X+3)},{Y(FO+0.6)} L{X(FSR_X+3)},{Y(FO-0.1)} Z", C['puck'], C['ink'], 0.8)
    S.path(f"M{X(23)},{Y(FO)} L{X(27)},{Y(FO)} L{X(FSR_X-3.2)},{Y(FO+2)} L{X(FSR_X+3.2)},{Y(FO+2)} L{X(35)},{Y(FO)} L{X(43)},{Y(FO)}", "none", C['ink'], 1, dash="4,3")
    # FSR tail: in plane to the slot, then off-plane (dashed) down the side gap to the connector
    S.path(f"M{X(FSR_X+3.8)},{Y(FO-0.25)} L{X(36.0)},{Y(FO-0.25)} Q{X(36.4)},{Y(FO-0.3)} {X(36.4)},{Y(FO-0.8)} L{X(36.4)},{Y(FI-0.2)}", "none", C['fsr'], 0.3 * s)
    S.path(f"M{X(36.4)},{Y(FI-0.2)} L{X(37.5)},{Y(5.5)} L{X(CONN[0])},{Y(4.0)}", "none", C['fsr'], 2.5, dash="5,3")
    S.rect(X(CONN[0]), Y(5.2), (CONN[1] - CONN[0]) * s, 2.5 * s, "none", C['comp'], 1.3, dash="5,3")
    # button (off-plane, dashed)
    S.rect(X(BTN_X - 3), Y(3), 6 * s, 6 * s, "none", C['ink'], 1, dash="4,3")
    S.line(X(16), Y(-1), X(53.5), Y(-1), C['shellE'], 0.8, dash="3,3")
    S.line(X(16), Y(0), X(53.5), Y(0), C['grey'], 0.5, dash="10,3,2,3")
    clip_end(S)
    # labels for detail 1 (outside the clip, right column + top)
    L1 = fx + 470
    co = lambda px_, py_, ty, t: S.callout(px_, py_, L1, ty, t, 10.5, "start")
    co(X(FSR_X + 2), Y(FO + 1.6), fy + 50, "Ø6 x 2 puck (TPU or hot glue),\nglued on the FSR's active area")
    co(X(FSR_X - 4.0), Y(FO), fy + 86, "pocket Ø8.4 x 0.5 deep; FSR 0.3 on\n0.1 adhesive sits 0.1 below the flat")
    co(X(36.6), Y(FO - 0.4), fy + 122, "tail groove 4.6 wide x 0.5, then a\n4.6 x 1.6 slot with R0.5 edges")
    co(X(40), Y(FO + 1.2), fy + 158, "optional 0.8 TPU grip pad (dashed),\nglued at its edges only")
    co(X(CONN[0] + 3), Y(4.5), fy + 194, "2-pin header + 10 kΩ / 0.1 µF in the side\ngap beside the cell (off-plane, dashed)")
    co(X(BTN_X - 3), Y(-1), fy + 240, "thumb button on the other side\n(off-plane, detail 2)")
    co(X(40), Y(BAT_Y[1]), fy + 286, "0.5 gap between the cell and the\nflat: the FSR never presses on it")
    co(X(30), Y(BAT_Y[0]), fy + 332, "cell stops against the tip at x = 18.6")
    S.text(L1 + 3, fy + 380, "Print the top shell's flat at 100 % infill", 10.5, C['note'])
    S.text(L1 + 3, fy + 394, "so the FSR is pressed against a rigid floor.", 10.5, C['note'])
    S.dimh(X(FSR_X - 4.2), X(FSR_X + 4.2), fy + 46, "Ø8.4", Y(FO) - 2, Y(FO) - 2, size=10)
    S.dimv(X(22) - 14, Y(FO), Y(FI), "1.6", X(22) - 2, size=10)
    S.dimv(X(22) - 14, Y(R), Y(FO), "", None, size=10)
    S.text(X(22) - 18, Y(R) + 2, "1.0", 10, C['dim'], "end")
    S.dimh(X(22), X(44), Y(-R) + 16, "grip flat 22", Y(-12) + 2, Y(-12) + 2, size=10)

    # ---------- DETAIL 2: button section at x = 36 (thumb side)
    gx, gy, gw, gh = 740, 80, 470, 440
    frame(S, gx, gy, gw, gh, "DETAIL 2  Thumb button mount (section at x = 36)", "3:1")
    s = 12.0
    cx = gx + 235; cy = gy + 240
    Xz = lambda z: cx + z * s
    Yy = lambda y: cy - y * s
    clip_begin(S, gx + 2, gy + 27, 260, gh - 30)
    zo = (R * R - FO * FO) ** 0.5; zi = (RI * RI - FI * FI) ** 0.5
    d_top = (f"M{Xz(-zo)},{Yy(FO)} L{Xz(zo)},{Yy(FO)} A{R*s},{R*s} 0 0 1 {Xz((R*R-1)**0.5)},{Yy(-1)} L{Xz((RI*RI-1)**0.5)},{Yy(-1)} "
             f"A{RI*s},{RI*s} 0 0 0 {Xz(zi)},{Yy(FI)} L{Xz(-zi)},{Yy(FI)} A{RI*s},{RI*s} 0 0 0 {Xz(-(RI*RI-1)**0.5)},{Yy(-1)} "
             f"L{Xz(-(R*R-1)**0.5)},{Yy(-1)} A{R*s},{R*s} 0 0 1 {Xz(-zo)},{Yy(FO)} Z")
    S.path(d_top, "url(#hatch)", C['shellE'], 1.1)
    d_bot = (f"M{Xz(-(R*R-1)**0.5)},{Yy(-1)} A{R*s},{R*s} 0 0 0 {Xz((R*R-1)**0.5)},{Yy(-1)} L{Xz((RI*RI-1)**0.5)},{Yy(-1)} "
             f"A{RI*s},{RI*s} 0 0 1 {Xz(-(RI*RI-1)**0.5)},{Yy(-1)} Z")
    S.path(d_bot, HATCH_B, "#8c7b5a", 1.1)
    # stem hole through wall
    S.rect(Xz(-15.6), Yy(1.9), 3.0 * s, 3.8 * s, "white", None)
    S.line(Xz(-15.6), Yy(1.9), Xz(-12.6), Yy(1.9), C['shellE'], 0.6); S.line(Xz(-15.6), Yy(-1.9), Xz(-12.6), Yy(-1.9), C['shellE'], 0.6)
    # switch cradle (bottom shell): backing rib + top/bottom guides
    S.path(f"M{Xz(-9.1)},{Yy(3.6)} L{Xz(-7.9)},{Yy(3.6)} L{Xz(-7.9)},{Yy(-10.6)} L{Xz(-9.1)},{Yy(-9.9)} Z", HATCH_B, "#8c7b5a", 0.8)
    S.rect(Xz(-12.7), Yy(-3.2), 3.6 * s, 1.0 * s, HATCH_B, "#8c7b5a", 0.8)
    S.rect(Xz(-12.0), Yy(4.2), 2.9 * s, 1.0 * s, HATCH_B, "#8c7b5a", 0.8)
    S.path(f"M{Xz(-12.0)},{Yy(3.2)} L{Xz(-9.1)},{Yy(3.2)} L{Xz(-9.1)},{Yy(3.6)}", "none", "#8c7b5a", 0.8)
    # switch: body 3.5 thick, stem Ø3.5 x 3.5
    S.rect(Xz(-12.6), Yy(3), 3.5 * s, 6 * s, C['comp'], None, rx=2)
    S.rect(Xz(-16.1), Yy(1.75), 3.5 * s, 3.5 * s, "#4a4f57", None, rx=3)
    # legs + wires
    S.path(f"M{Xz(-10.5)},{Yy(-3)} L{Xz(-10.5)},{Yy(-4.6)} L{Xz(-7.9)},{Yy(-5.8)}", "none", C['blue'], 2)
    S.path(f"M{Xz(-11.5)},{Yy(-3)} L{Xz(-11.5)},{Yy(-5.4)} L{Xz(-7.9)},{Yy(-7.0)}", "none", C['black'], 2)
    S.rect(Xz(-4), Yy(BAT_Y[1]), 8 * s, 24 * s, C['bat'], C['batE'], 1, rx=6)
    # FSR + puck at top
    S.rect(Xz(-3.8), Yy(FO - 0.1), 7.6 * s, 0.4 * s, C['fsr'], C['ink'], 0.5)
    S.path(f"M{Xz(-3)},{Yy(FO - 0.1)} Q{Xz(0)},{Yy(FO + 2.6)} {Xz(3)},{Yy(FO - 0.1)} Z", C['puck'], C['ink'], 0.8)
    S.line(Xz(-17), Yy(-1), Xz(3), Yy(-1), C['shellE'], 0.8, dash="3,3")
    clip_end(S)
    L2 = gx + 268
    co2 = lambda px_, py_, ty, t: S.callout(px_, py_, L2, ty, t, 10.5, "start")
    co2(Xz(-15.2), Yy(1.2), gy + 60, "stem hole Ø3.8 (stem Ø3.5);\nstem stands 1.0–1.5 proud")
    co2(Xz(-11), Yy(0.5), gy + 110, "6 x 6 tact switch, 3.5 body,\n7 mm total height")
    co2(Xz(-8.5), Yy(-7), gy + 160, "backing rib 1.2 thick from the\nbottom shell takes the push")
    co2(Xz(-11), Yy(-2.8), gy + 210, "guide ribs above and below\nthe body, 0.2 clearance")
    co2(Xz(-10.5), Yy(-4.6), gy + 260, "legs bent flat, wires soldered,\nthen a dab of hot glue")
    co2(Xz(1), Yy(FO + 1.5), gy + 310, "FSR + puck on the flat\n(detail 1)")
    co2(Xz(0), Yy(-3), gy + 360, "cell on edge: 3.9 clear of\nthe backing rib")
    S.text(gx + 16, gy + gh - 16, "Thumb side shown on the left (looking from the rear).", 10.5, C['note'])

    # ---------- DETAIL 3: Nano rail, finger, tongue and groove (section at x = 72, right side)
    hx, hy, hw, hh = 30, 540, 560, 440
    frame(S, hx, hy, hw, hh, "DETAIL 3  Nano rail, hold-down finger and shell joint (x = 96)", "6:1")
    s = 24.0
    cx = hx + 20 - 4.0 * s; cy = hy + 230
    Xz = lambda z: cx + z * s
    Yy = lambda y: cy - y * s
    clip_begin(S, hx + 2, hy + 27, 300, hh - 30)
    def arc_pts(r, a0, a1, n=40):
        return [(r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
    a_split_o = math.degrees(math.asin(-1 / R)); a_split_i = math.degrees(math.asin(-1 / RI))
    topring = arc_pts(R, a_split_o, 60) + list(reversed(arc_pts(RI, a_split_i, 60)))
    poly(S, topring, Xz, Yy, "url(#hatch)", C['shellE'], 1.1)
    botring = arc_pts(R, -40, a_split_o) + list(reversed(arc_pts(RI, -40, a_split_i)))
    poly(S, botring, Xz, Yy, HATCH_B, "#8c7b5a", 1.1)
    # groove in top shell + tongue on bottom shell
    zg = (R + RI) / 2 - 0.05
    S.rect(Xz(zg - 0.65), Yy(0.2), 1.3 * s, 1.2 * s, "white", C['shellE'], 0.6)
    S.rect(Xz(zg - 0.5), Yy(0.0), 1.0 * s, 1.0 * s, HATCH_B, "#8c7b5a", 0.8)
    # ledge (bottom shell)
    poly(S, [(8.5, -2.0), (12.95, -2.0), (12.4, -4.4), (9.7, -4.4), (8.5, -3.2)], Xz, Yy, HATCH_B, "#8c7b5a", 0.8)
    # PCB and castellated pad
    S.rect(Xz(4.0), Yy(-1.0), 5.0 * s, 1.0 * s, C['pcb'], C['pcbE'], 0.8)
    S.rect(Xz(6.77), Yy(-1.0) - 2, 1.7 * s, 2, "#d4af37")
    S.rect(Xz(6.77), Yy(-2.0), 1.7 * s, 2, "#d4af37")
    S.circle(Xz(7.62), Yy(-2.35), 0.35 * s, "#c9c9c9", C['ink'], 0.5)      # solder blob
    S.path(f"M{Xz(7.62)},{Yy(-2.6)} Q{Xz(7.4)},{Yy(-4.2)} {Xz(5.5)},{Yy(-5.2)} L{Xz(4)},{Yy(-5.2)}", "none", C['red'], 0.5 * s)
    # hold-down finger (top shell) with crush rib
    yw = (RI * RI - 9.6 * 9.6) ** 0.5
    poly(S, [(8.5, yw + 1.5), (9.6, yw + 1.5), (9.6, -0.9), (9.0, -0.9), (9.0, -1.0), (8.6, -1.0), (8.6, -0.9), (8.5, -0.9)], Xz, Yy, "url(#hatch)", C['shellE'], 0.8)
    S.line(Xz(4), Yy(0), Xz(15.5), Yy(0), C['grey'], 0.5, dash="10,3,2,3")
    S.line(Xz(4), Yy(-1), Xz(15.5), Yy(-1), C['shellE'], 0.8, dash="3,3")
    clip_end(S)
    L3 = hx + 300
    co3 = lambda px_, py_, ty, t: S.callout(px_, py_, L3, ty, t, 10.5, "start")
    co3(Xz(9.1), Yy(2.5), hy + 60, "hold-down finger, 1.1 wide, 5 long\n(3 per side); 0.1 crush rib on the tip")
    co3(Xz(zg), Yy(-0.5), hy + 110, "tongue 1.0 x 1.0 (bottom) in groove\n1.3 x 1.2 (top) keeps the halves aligned")
    co3(Xz(6.0), Yy(-0.5), hy + 160, "Nano PCB, 1.0 thick (measure yours)")
    co3(Xz(10.5), Yy(-3.0), hy + 200, "rail block: 0.5 under the PCB edge, so\nit clears the castellated pads (8.47)")
    co3(Xz(11.2), Yy(-0.6), hy + 250, "4 mm side gap PCB to wall (wires)")
    co3(Xz(7.62), Yy(-2.35), hy + 290, "wire soldered under the pad")
    co3(Xz(9.1), Yy(-3.9), hy + 330, "45° underside: prints without support")
    S.text(L3 + 3, hy + 380, "Split line at y = −1 (top of the PCB).", 10.5, C['note'])
    S.text(L3 + 3, hy + 396, "Close the shell and the PCB is clamped.", 10.5, C['note'])

    # ---------- DETAIL 4: screw boss section at x = 106.5
    kx, ky, kw, kh = 610, 540, 600, 440
    frame(S, kx, ky, kw, kh, "DETAIL 4  Screw bosses + locating rib (section at x = 71.25)", "2.25:1")
    s = 9.0
    cx = kx + 160; cy = ky + 230
    Xz = lambda z: cx + z * s
    Yy = lambda y: cy - y * s
    # top shell ring half + bottom half
    topring = arc_pts(R, a_split_o, 180 - a_split_o, 80) + list(reversed(arc_pts(RI, a_split_i, 180 - a_split_i, 80)))
    poly(S, topring, Xz, Yy, "url(#hatch)", C['shellE'], 1.1)
    botring = arc_pts(R, 180 - a_split_o, 360 + a_split_o, 80) + list(reversed(arc_pts(RI, 180 - a_split_i, 360 + a_split_i, 80)))
    poly(S, botring, Xz, Yy, HATCH_B, "#8c7b5a", 1.1)
    # locating ring rib: top part (r 7..10 above split) and bottom part with a wire notch
    rt = arc_pts(RI, a_split_i, 180 - a_split_i, 60) + list(reversed(arc_pts(7, math.degrees(math.asin(-1/7)), 180 - math.degrees(math.asin(-1/7)), 60)))
    poly(S, rt, Xz, Yy, "url(#hatch)", C['shellE'], 0.6)
    a7 = math.degrees(math.asin(-1/7)); an = math.degrees(math.atan2(-6.3, 3))
    rb1 = arc_pts(RI, 180 - a_split_i, 360 + an, 40) + [(3, -6.3)] + list(reversed(arc_pts(7, 180 - a7, 360 + an, 40)))
    S.path("M" + " L".join(f"{Xz(a):.2f},{Yy(b):.2f}" for a, b in arc_pts(RI, 180 - a_split_i, 256.7, 30) + [(-3, -12.65), (-3, -6.3)] + list(reversed(arc_pts(7, 180 - a7, 244, 30)))) + " Z", HATCH_B, "#8c7b5a", 0.6)
    S.path("M" + " L".join(f"{Xz(a):.2f},{Yy(b):.2f}" for a, b in arc_pts(RI, 283.3, 360 + a_split_i, 30) + list(reversed(arc_pts(7, 296, 360 + a7, 30))) + [(3, -6.3), (3, -12.65)]) + " Z", HATCH_B, "#8c7b5a", 0.6)
    for zz in (-SZ, SZ):
        # bottom boss, top boss
        yb = -(RI * RI - (abs(zz) + 2) ** 2) ** 0.5
        poly(S, [(zz - 2, -1), (zz + 2, -1), (zz + 2, -10.2), (zz - 2, -10.2)], Xz, Yy, HATCH_B, "#8c7b5a", 0.8)
        poly(S, [(zz - 2, -1), (zz + 2, -1), (zz + 2, 10.2), (zz - 2, 10.2)], Xz, Yy, "url(#hatch)", C['shellE'], 0.8)
        # holes
        S.rect(Xz(zz - 2.1), Yy(-8.4), 4.2 * s, 6.0 * s, "white", None)   # counterbore Ø4.2 from outside
        S.rect(Xz(zz - 1.2), Yy(-1.0), 2.4 * s, 7.4 * s, "white", None)            # clearance Ø2.4
    S.rect(Xz(-SZ - 0.85), Yy(3.0), 1.7 * s, 4 * s, "white", C['shellE'], 0.5)   # pilot Ø1.7 x 4
    S.rect(Xz(SZ - 1.6), Yy(3.0), 3.2 * s, 4 * s, "white", C['shellE'], 0.5)     # insert hole Ø3.2 x 4
    S.rect(Xz(SZ - 1.75), Yy(2.0), 3.5 * s, 3 * s, "#c8a24a", C['ink'], 0.6)     # heat-set insert
    for zz in (-SZ, SZ):
        S.rect(Xz(zz - 1.9), Yy(-8.4), 3.8 * s, 1.4 * s, "#5b6068", None, rx=2)  # head
        top_y = 2.0
        S.rect(Xz(zz - 1.0), Yy(top_y), 2.0 * s, (top_y + 8.4) * s, "#9aa0a8", C['ink'], 0.5)
        for k in range(19):
            yy_ = -6.6 + k * 0.45
            S.line(Xz(zz - 1.0), Yy(yy_), Xz(zz + 1.0), Yy(yy_ + 0.25), C['ink'], 0.4)
    # contents passing through the rib
    for z, y, col in ((-3.4, -4.6, C['blue']), (-3.0, -5.6, C['black']), (3.4, -4.6, C['yellow']), (3.0, -5.6, C['orange']), (-0.7, -7.6, C['red']), (0.7, -8.4, C['black'])):
        S.circle(Xz(z), Yy(y), 0.55 * s, col, "white", 0.6)
    S.rect(Xz(-4), Yy(BAT_Y[1]), 8 * s, 24 * s, "none", C['batE'], 1.2, rx=6, dash="5,4")
    S.line(Xz(-16), Yy(-1), Xz(16), Yy(-1), C['shellE'], 0.8, dash="3,3")
    L4 = kx + 318
    co4 = lambda px_, py_, ty, t: S.callout(px_, py_, L4, ty, t, 10.5, "start")
    co4(Xz(-SZ), Yy(2.5), ky + 56, "self-tapping: pilot Ø1.7 x 4 deep,\nM2 x 10 pan head bites ≈ 3 mm")
    co4(Xz(SZ + 0.8), Yy(1), ky + 106, "or M2 heat-set insert (Ø3.5 x 3) in a\nØ3.2 x 4 hole (stronger, re-openable)")
    co4(Xz(SZ), Yy(-4.5), ky + 156, "clearance hole Ø2.4 through the\nbottom boss; bosses Ø4")
    co4(Xz(SZ), Yy(-11.5), ky + 206, "counterbore Ø4.2 so the head\nsits below the surface")
    co4(Xz(1.5), Yy(10), ky + 256, "locating ring rib, opening Ø14:\nstops the cell, passes the wires")
    co4(Xz(2.6), Yy(-10), ky + 306, "6 x 3 wire notch")
    co4(Xz(-3.6), Yy(4), ky + 340, "cell on edge, in front (dashed)")
    S.text(kx + 16, ky + kh - 16, "Same boss at x = 26 and x = 129.25. Left: self-tapping. Right: heat-set insert. Pick one.", 10.5, C['note'])
    S.save("05_inner_grip_and_nano.svg")


# ---------------------------------------------------------------- sheet 6
def sheet6():
    S = Sheet(1240, 1010, "Magic Wand pen: inner features 2, battery and power bay, rear cap",
              "Rev D: Ø30 body, Spektrum 800 mAh cell on edge under the grip, Nano behind it, charger at the back with its USB-C mouth at the cap wall.")
    add_hatchB(S); add_hatchC(S)
    legend_shells(S, 860, 52)
    # detail 5 is drawn in rev B coordinates (power bay 30 mm further back); labels give rev D numbers
    CAP = (184, 196); SHELL_END = 188; TP = (168, 194); BST = (170, 185.2); SW_X = 165.5

    # ---------- DETAIL 5: power bay long section x 154..197
    fx, fy, fw, fh = 30, 80, 1180, 440
    frame(S, fx, fy, fw, fh, "DETAIL 5  Power bay and rear cap (long section on the centre plane)", "2.1:1")
    s = 12.0
    ox = fx + 40 - 154 * s; oy = fy + 45 + 15 * s
    X = lambda x: ox + x * s
    Y = lambda y: oy - y * s
    clip_begin(S, fx + 2, fy + 27, 44 * s + 40, fh - 30)
    poly(S, [(153, R), (CAP[0], R), (CAP[0], LAPR), (SHELL_END, LAPR), (SHELL_END, RI), (153, RI)], X, Y, "url(#hatch)", C['shellE'], 1.1)
    poly(S, [(153, -R), (CAP[0], -R), (CAP[0], -LAPR), (SHELL_END, -LAPR), (SHELL_END, -RI), (153, -RI)], X, Y, HATCH_B, "#8c7b5a", 1.1)
    cap = [(CAP[0], R), (CAP[1] - 3, R), (CAP[1] - 1.2, R - 0.8), (CAP[1], R - 3), (CAP[1], -R + 3), (CAP[1] - 1.2, -R + 0.8), (CAP[1] - 3, -R), (CAP[0], -R),
           (CAP[0], -LAPR - 0.05), (SHELL_END, -LAPR - 0.05), (SHELL_END, -RI), (CAP[1] - 2, -RI), (CAP[1] - 2, RI), (SHELL_END, RI), (SHELL_END, LAPR + 0.05), (CAP[0], LAPR + 0.05)]
    poly(S, cap, X, Y, "url(#hatchC)", "#6c8a6c", 1.1)
    # snap bump on the lap
    S.circle(X(186), Y(LAPR), 0.35 * s, "white", "#6c8a6c", 0.8)
    # port windows: 0.8 web + 1.2 spot-face
    for yt, h in ((0.9, 3.4), (6.6, 3.0)):
        S.rect(X(CAP[1] - 1.2), Y(yt + 1.5), 1.2 * s, (h + 3) * s, "white", "#6c8a6c", 0.6)
        S.rect(X(CAP[1] - 2), Y(yt), 0.8 * s, h * s, "white", "#6c8a6c", 0.6)
    # LED window on top of the cap
    S.rect(X(190.0), Y(R), 2 * s, 2 * s, "white", "#6c8a6c", 0.6)
    S.rect(X(190.0), Y(R), 2 * s, 2 * s, "#ffe3e3", "#6c8a6c", 0.6, op=0.6)
    # ribs at 159-160.5
    S.rect(X(159.4), Y(RI), 1.0 * s, 3 * s, "url(#hatch)", C['shellE'], 0.8)
    S.rect(X(159.4), Y(-RI + 3.5), 1.0 * s, 3.5 * s, HATCH_B, "#8c7b5a", 0.8)
    # grooves for the TP4056 (behind the cut, dashed)
    S.rect(X(167.5), Y(-2.25), (194 - 167.5) * s, 1.9 * s, "none", "#8c7b5a", 1, dash="5,3")
    # Nano end, FPC plug and battery leads coming from the front along the channel
    S.rect(X(150), Y(PCB_Y[1]), 3 * s, 1.0 * s, C['pcb'], C['pcbE'], 0.8)
    S.rect(X(150.5), Y(2.6), 8.5 * s, 4.0 * s, C['comp'], None, rx=1)
    S.path(f"M{X(BST[0] - 3)},{Y(-9.2)} L{X(153)},{Y(-9.2)}", "none", C['red'], 0.15 * s + 1)
    S.path(f"M{X(BST[0] - 3)},{Y(-10.0)} L{X(153)},{Y(-10.0)}", "none", C['black'], 0.15 * s + 1)
    S.path(f"M{X(BST[0] - 3)},{Y(-9.2)} Q{X(TP[0])},{Y(-9.2)} {X(TP[0] + 0.6)},{Y(-4.2)}", "none", C['red'], 0.15 * s + 1)
    S.path(f"M{X(BST[0] - 3)},{Y(-10.0)} Q{X(TP[0] + 1)},{Y(-10.0)} {X(TP[0] + 1.6)},{Y(-4.2)}", "none", C['black'], 0.15 * s + 1)
    # TP4056 + USB-C
    S.rect(X(TP[0]), Y(TP_Y[1]), 26 * s, 1.6 * s, C['tp'], C['ink'], 0.7)
    S.rect(X(174), Y(-1.4), 5 * s, 1.0 * s, C['comp'])
    S.rect(X(186.5), Y(-1.8), 1.6 * s, 0.6 * s, "#d22")
    S.rect(X(188.5), Y(-1.8), 1.6 * s, 0.6 * s, "#36c")
    S.rect(X(190.3), Y(0.8), 3.7 * s, 3.2 * s, "#c8ccd2", C['ink'], 0.7)
    # boost on foam + output wires
    S.rect(X(BST[0] + 1), Y(BST_Y[0]), 13 * s, 1.6 * s, "#f3e6b3", C['ink'], 0.4)
    S.rect(X(BST[0]), Y(BST_Y[1]), 15.2 * s, 1.0 * s, C['boost'], C['ink'], 0.7)
    S.rect(X(175), Y(4.6), 3 * s, 1.0 * s, C['comp'])
    S.path(f"M{X(BST[0])},{Y(3.0)} L{X(167)},{Y(1)} L{X(167)},{Y(-10.8)} L{X(153)},{Y(-10.8)}", "none", C['red'], 2)
    S.path(f"M{X(BST[0])},{Y(2.8)} L{X(167.6)},{Y(0.6)} L{X(167.6)},{Y(-11.6)} L{X(153)},{Y(-11.6)}", "none", C['black'], 2)
    # TP OUT -> switch -> boost IN (short loop)
    S.path(f"M{X(169)},{Y(-2.4)} Q{X(166)},{Y(1)} {X(SW_X+2)},{Y(1.4)}", "none", C['red'], 1.6, dash="2,0")
    # switch (off-plane, dashed) + its slot
    S.rect(X(SW_X - 4.3), Y(1.8), 8.6 * s, 3.6 * s, "none", C['sw'], 1.2, dash="4,3")
    # FPC + female micro-USB in its pocket
    S.path(f"M{X(159)},{Y(1.5)} L{X(160.5)},{Y(6.4)} L{X(186)},{Y(6.4)} L{X(188)},{Y(5.1)}", "none", C['fpc'], 0.4 * s)
    poly(S, [(187.5, 7.0), (194, 7.0), (194, 7.4), (187.5, 7.4)], X, Y, "url(#hatchC)", "#6c8a6c", 0.6)
    S.rect(X(188), Y(6.6), 6 * s, 3.0 * s, "#c8ccd2", C['ink'], 0.7)
    S.line(X(153), Y(-1), X(SHELL_END), Y(-1), C['shellE'], 0.8, dash="3,3")
    S.line(X(153), Y(0), X(197), Y(0), C['grey'], 0.5, dash="10,3,2,3")
    clip_end(S)
    L5 = fx + 44 * s + 60
    co5 = lambda px_, py_, ty, t: S.callout(px_, py_, L5, ty, t, 10.5, "start")
    co5(X(195.4), Y(3.9), fy + 46, "port windows: wall thinned to 0.8 by a\n1.2 deep spot-face, so plugs seat fully")
    co5(X(191), Y(R), fy + 88, "Ø2 window over the charge LEDs;\nor print the cap in translucent PETG")
    co5(X(186), Y(LAPR), fy + 130, "lap joint: shell stepped to Ø28 for 4 mm,\ncap sleeve slides over (0.05 gap) +\n0.3 snap bump; a drop of CA to make it permanent")
    co5(X(191), Y(6), fy + 186, "micro-USB female (FPC end) glued into\na cap pocket, mouth against the wall")
    co5(X(192), Y(-0.8), fy + 228, "TP4056 USB-C mouth touches the cap wall")
    co5(X(180), Y(-2.9), fy + 258, "TP4056 slides into 1.9-high grooves in\nthe bottom shell (dashed), stops at the rib")
    co5(X(178), Y(3.2), fy + 300, "boost on 1.6 foam tape over the charger")
    co5(X(SW_X), Y(-1.8), fy + 330, "slide switch in the side wall (detail 7)")
    co5(X(166), Y(-9.2), fy + 360, "battery leads arrive from the front along\nthe channel, up to TP4056 B+ / B−")
    co5(X(155), Y(2.0), fy + 400, "FPC plug on the Nano's USB; rib at x = 129–130")
    S.dimh(X(CAP[0]), X(CAP[1]), fy + 38, "cap 12", Y(R) - 2, Y(R) - 2, size=10)
    S.dimh(X(TP[0]), X(TP[1]), Y(-R) + 26, "TP4056 26", Y(-4) + 2, Y(-4) + 2, size=10)
    S.dimh(X(CAP[0]), X(SHELL_END), Y(-R) + 26, "lap 4", Y(-R) + 2, Y(-R) + 2, size=10)

    # ---------- DETAIL 6: battery cradle (section at x = 58)
    hx, hy, hw, hh = 30, 540, 470, 440
    frame(S, hx, hy, hw, hh, "DETAIL 6  Battery cradle, cell on edge (x = 58)", "2.3:1")
    s = 8.5
    cx = hx + 150; cy = hy + 225
    Xz = lambda z: cx + z * s
    Yy = lambda y: cy - y * s
    def arc_pts(r, a0, a1, n=60):
        return [(r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
    a_o = math.degrees(math.asin(-1 / R)); a_i = math.degrees(math.asin(-1 / RI))
    poly(S, arc_pts(R, a_o, 180 - a_o) + list(reversed(arc_pts(RI, a_i, 180 - a_i))), Xz, Yy, "url(#hatch)", C['shellE'], 1.1)
    poly(S, arc_pts(R, 180 - a_o, 360 + a_o) + list(reversed(arc_pts(RI, 180 - a_i, 360 + a_i))), Xz, Yy, HATCH_B, "#8c7b5a", 1.1)
    for sgn in (-1, 1):
        zin, zout = sgn * 4.2, sgn * 5.3
        a, b = min(zin, zout), max(zin, zout)
        top_y = (RI * RI - b * b) ** 0.5
        poly(S, [(a, top_y + 0.3), (b, top_y + 0.3), (b, -0.6), (a, -0.6)], Xz, Yy, "url(#hatch)", C['shellE'], 0.8)
        poly(S, [(a, -1.4), (b, -1.4), (b, -top_y - 0.3), (a, -top_y - 0.3)], Xz, Yy, HATCH_B, "#8c7b5a", 0.8)
    S.rect(Xz(-2.0), Yy(12.9), 4 * s, 0.7 * s, "url(#hatch)", C['shellE'], 0.6)
    S.rect(Xz(-2.0), Yy(BAT_Y[0] - 0.3), 4 * s, 0.6 * s, HATCH_B, "#8c7b5a", 0.6)
    S.rect(Xz(-4), Yy(BAT_Y[1]), 8 * s, 24 * s, C['bat'], C['batE'], 1, rx=0.8 * s)
    S.rect(Xz(-1.8), Yy(BAT_Y[1] + 0.3), 3.6 * s, 0.3 * s, "#f3e6b3", C['ink'], 0.4)
    S.rect(Xz(-1.8), Yy(BAT_Y[0]), 3.6 * s, 0.3 * s, "#f3e6b3", C['ink'], 0.4)
    for z, y, col in ((-7.0, -3.0, C['blue']), (-7.4, -4.6, C['black']), (7.0, -3.0, C['yellow']), (7.4, -4.6, C['orange']),
                      (7.8, -6.2, C['black']), (-7.8, -6.2, C['red']), (-7.0, 3.0, C['red']), (7.0, 3.0, C['black'])):
        S.circle(Xz(z), Yy(y), 0.5 * s, col, "white", 0.6)
    S.line(Xz(-16), Yy(-1), Xz(16), Yy(-1), C['shellE'], 0.8, dash="3,3")
    co6 = lambda px_, py_, tx, ty, t, a="start": S.callout(px_, py_, tx, ty, t, 10.5, a)
    L6 = hx + 300
    co6(Xz(4.75), Yy(4), L6, hy + 60, "guide ribs 1.1 thick, 8.4 apart\n(0.2 gap a side), in both shells")
    co6(Xz(0), Yy(12.5), L6, hy + 120, "end pads + 0.3 foam clamp the\ncell top and bottom")
    co6(Xz(7.0), Yy(3.0), L6, hy + 180, "battery leads (from the rear\nend) run back in the upper gaps")
    co6(Xz(7.4), Yy(-4.6), L6, hy + 240, "FSR, button and 5 V wires run\nin the lower side gaps")
    co6(Xz(-3.5), Yy(-6), L6, hy + 300, "Spektrum 800 mAh, 8 x 24 x 51")
    S.text(hx + 16, hy + hh - 16, "Cell sits between the tip (x = 18.6) and the rib at x = 70.5; 0.3 foam each end.", 10.5, C['note'])

    # ---------- DETAIL 7: slide switch in the side wall (section at x = 165)
    gx, gy, gw, gh = 520, 540, 340, 440
    frame(S, gx, gy, gw, gh, "DETAIL 7  Power switch (x = 135.5)", "5:1")
    s = 18.0
    cx = gx - 115; cy = gy + 230
    Xz = lambda z: cx + z * s
    Yy = lambda y: cy - y * s
    clip_begin(S, gx + 2, gy + 27, 180, gh - 52)
    poly(S, arc_pts(R, a_o, 75) + list(reversed(arc_pts(RI, a_i, 75))), Xz, Yy, "url(#hatch)", C['shellE'], 1.1)
    poly(S, arc_pts(R, -75, a_o) + list(reversed(arc_pts(RI, -75, a_i))), Xz, Yy, HATCH_B, "#8c7b5a", 1.1)
    # slot through wall (in top shell, above split): lever slot 2.2 tall
    S.rect(Xz(12.5), Yy(2.4), 3 * s, 2.2 * s, "white", None)
    # pocket ribs holding the switch body
    S.rect(Xz(8.6), Yy(4.4), 4.0 * s, 0.6 * s, "url(#hatch)", C['shellE'], 0.6)
    S.rect(Xz(8.6), Yy(-0.4), 4.4 * s, 0.6 * s, HATCH_B, "#8c7b5a", 0.6)
    S.rect(Xz(8.3), Yy(4.4), 0.6 * s, 5.4 * s, HATCH_B, "#8c7b5a", 0.6)
    # switch body (3.5 tall in y here, 3.6 deep in z) + lever
    S.rect(Xz(9.0), Yy(3.8), 3.6 * s, 3.6 * s, C['sw'], C['ink'], 0.6, rx=2)
    S.rect(Xz(12.6), Yy(2.0), 2.9 * s, 1.4 * s, C['ink'], None, rx=2)
    S.path(f"M{Xz(9.0)},{Yy(1.0)} L{Xz(8)},{Yy(-1.6)} L{Xz(6)},{Yy(-3)}", "none", C['red'], 0.12 * s + 1)
    S.line(Xz(5), Yy(-1), Xz(16.5), Yy(-1), C['shellE'], 0.8, dash="3,3")
    clip_end(S)
    L7 = gx + 250
    L7 = gx + 196
    S.callout(Xz(15.2), Yy(1.6), L7, gy + 70, "lever slot 4.5 (x)\nx 2.2; lever 0.5\nproud", 10, "start")
    S.callout(Xz(10.5), Yy(2.2), L7, gy + 150, "SS12D00 body\n8.6 x 3.6 x 3.5", 10, "start")
    S.callout(Xz(10.6), Yy(4.1), L7, gy + 215, "pocket ribs, 0.15\ngap; pushed in\nfrom inside, glued", 10, "start")
    S.callout(Xz(7.5), Yy(-2.2), L7, gy + 300, "leads to TP OUT+\nand boost IN", 10, "start")
    S.text(gx + 16, gy + gh - 16, "Opposite side from the thumb button.", 10.5, C['note'])

    # ---------- table: print clearances
    tx, ty, tw, th = 880, 540, 330, 440
    frame(S, tx, ty, tw, th, "Print clearances used", "")
    rows = [("Fit", "Gap (mm)"),
            ("PCB in ledge / guide groove", "0.2–0.3"),
            ("PCB clamp (finger crush rib)", "−0.1"),
            ("Battery in rails", "0.2 a side"),
            ("Tongue in groove", "0.15 a side"),
            ("Cap sleeve over shell lap", "0.05 + bump"),
            ("Button stem in wall hole", "0.15 a side"),
            ("Switch in pocket", "0.15"),
            ("M2 self-tap pilot", "Ø1.7"),
            ("M2 clearance / counterbore", "Ø2.4 / Ø4.2"),
            ("Heat-set insert hole", "Ø3.2 x 4"),
            ("USB windows vs connector", "+0.3 all round")]
    for i, (a, b) in enumerate(rows):
        y = ty + 56 + i * 24
        if i == 0:
            S.rect(tx + 10, y - 15, tw - 20, 22, "#eef1f5")
        S.text(tx + 18, y, a, 11, weight="bold" if i == 0 else "normal")
        S.text(tx + tw - 18, y, b, 11, anchor="end", weight="bold" if i == 0 else "normal")
    S.text(tx + 18, ty + th - 50, "Tuned for a 0.4 nozzle on PETG/PLA. Print one", 10.5, C['note'])
    S.text(tx + 18, ty + th - 34, "test ring at x = 60–80 first and adjust.", 10.5, C['note'])
    S.save("06_inner_power_and_cap.svg")

sheet5(); sheet6()

print("ok")
