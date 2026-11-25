"""
Ghostbusters.py - write letters in the air with the Magic Wand pen to blast ghosts.

Flow:  intro screen (Easy / Hard)  ->  tutorial (press SPACE)  ->  main game  ->  game over

How it connects to the pen
  live_predict.py (and through it live_draw.py, model.py and onhw_both_merged_acc2_gyro.pt)
  is loaded in a BACKGROUND THREAD, so pygame never freezes. That thread reads the Nano
  (USB first, Bluetooth if no cable, same as live_draw.py), feeds live_draw.PenTracker,
  records a letter between two SPACE presses (or while the pen-down button/grip is held),
  then calls live_predict.classify() and hands the top-3 letters to the game through a queue.
  No matplotlib window is opened: the game replaces live_draw's Canvas.

Where to put it
  Magic-Wand/GameFiles/Ghostbusters.py   (live_predict.py etc. one folder up is found
  automatically; the same folder works too). Enemy_ghost.PNG goes next to this file.

Keys
  SPACE      start / stop writing a letter with the pen
  A-Z        keyboard fallback: fire that letter directly (testing without the Nano)
  F5         recalibrate the gyro (hold the pen still)
  F11        fullscreen on/off       ESC  leave fullscreen / back to the menu
"""

import os
import sys
import math
import time
import queue
import random
import asyncio
import threading
import pygame as pg

# ---------------------------------------------------------------- paths
HERE = os.path.dirname(os.path.abspath(__file__))
PREDICT_DIR = next((d for d in (HERE, os.path.dirname(HERE))
                    if os.path.exists(os.path.join(d, "live_predict.py"))), None)
GHOST_IMG = os.path.join(HERE, "Enemy_ghost.PNG")

# ---------------------------------------------------------------- settings
WINDOW_WIDTH, WINDOW_HEIGHT = 1600, 800       # largest size; shrunk in fit_window() to fit your screen
S = 1.0                                       # pixel scale (window width / 1600), set in fit_window()
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIFFICULTY = {
    #        seconds to cross   first spawn gap   fastest gap   lives   ghosts at once   top-N guesses that count (1 = predicted letter only)
    "Easy": dict(cross_time=28.0, spawn_gap=7.0, min_gap=4.0, lives=5, max_ghosts=4, top_n=1),
    "Hard": dict(cross_time=16.0, spawn_gap=4.5, min_gap=2.2, lives=3, max_ghosts=7, top_n=1),
}
BEAM_TIME = 0.35            # seconds the proton beam stays on screen
GHOST_HEIGHT = 170          # px at full size (scaled with S)


# ================================================================= pen + model (background)
class PenPredictor(threading.Thread):
    """Loads live_predict's model, reads the pen and puts predictions on self.results.

    The game only talks to it through:
        toggle_recording(), recalibrate(), status, recording, connected, ready,
        path (list of (x, y) of the letter being written), results (queue of top-3 lists)
    """

    def __init__(self):
        super().__init__(daemon=True)
        self.results = queue.Queue()
        self.status = "Loading the letter model..."
        self.connected = False      # a Nano is streaming
        self.ready = False          # model loaded
        self.recording = False
        self.path = []
        self.stop = False
        self._lock = threading.Lock()
        self._toggle = False
        self._recal = False
        self._rec = None
        self._last_btn = 0

    # ---- called from the game thread
    def toggle_recording(self):
        with self._lock:
            self._toggle = True

    def recalibrate(self):
        with self._lock:
            self._recal = True

    # ---- thread body
    def run(self):
        if PREDICT_DIR is None:
            self.status = "live_predict.py not found - keyboard mode (type the letters)"
            return
        try:
            sys.path.insert(0, PREDICT_DIR)
            old = os.getcwd()
            os.chdir(PREDICT_DIR)               # live_predict loads its .pt with a relative path
            try:
                import live_predict
            finally:
                os.chdir(old)
            self.lp = live_predict
            self.ld = live_predict.live_draw
        except Exception as e:
            self.status = f"Model failed to load ({e}) - keyboard mode"
            print("[Ghostbusters] could not load live_predict:", repr(e))
            return
        self.ready = True
        self.tracker = self.ld.PenTracker()
        port = self.ld.find_usb_port()
        try:
            if port is not None:
                self._run_usb(port)
            else:
                asyncio.run(self._run_ble())
        except Exception as e:
            self.connected = False
            self.status = f"Pen connection lost ({e}) - keyboard still works"
            print("[Ghostbusters] pen error:", repr(e))

    def _run_usb(self, port):
        self.status = f"Opening {port}..."
        ser = self.ld.open_port(port)
        last_ms = None
        try:
            ser.reset_input_buffer()
            buf = b""
            while not self.stop:
                buf += ser.read(ser.in_waiting or 1)
                *lines, buf = buf.split(b"\n")
                for raw in lines:
                    line = raw.decode(errors="ignore").strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        v = [float(x) for x in line.split(",")]
                    except ValueError:
                        continue
                    if len(v) < 7:
                        continue
                    dt = 0.01 if last_ms is None else (v[0] - last_ms) / 1000.0
                    last_ms = v[0]
                    if not 0 < dt < 0.2:
                        continue
                    btn = int(v[10]) if len(v) > 10 else 0
                    self._sample(dt, v[1:4], v[4:7], btn)
                if not lines:
                    time.sleep(0.002)
        finally:
            ser.close()
            self.connected = False

    async def _run_ble(self):
        try:
            from bleak import BleakScanner, BleakClient
        except ImportError:
            self.status = "No Nano on USB and bleak not installed - keyboard mode"
            return
        import struct
        from collections import deque
        self.status = f"No USB pen, scanning Bluetooth for '{self.ld.DEVICE_NAME}'..."
        device = await BleakScanner.find_device_by_name(self.ld.DEVICE_NAME, timeout=15)
        if device is None:
            self.status = "Pen not found (USB or Bluetooth) - keyboard mode (type the letters)"
            return
        samples = deque()

        def on_data(_, data):
            seq, flags, ax, ay, az, gx, gy, gz, *_m = struct.unpack(self.ld.PACKET_FMT,
                                                                     data[:self.ld.PACKET_LEN])
            samples.append((seq, flags & 1, (ax / 1000, ay / 1000, az / 1000),
                            (gx / 10, gy / 10, gz / 10)))

        last_seq = None
        async with BleakClient(device) as client:
            await client.start_notify(self.ld.CHAR_UUID, on_data)
            while client.is_connected and not self.stop:
                while samples:
                    seq, btn, acc, gyr = samples.popleft()
                    steps = 1 if last_seq is None else (seq - last_seq) % 256
                    last_seq = seq
                    if 0 < steps < 20:
                        self._sample(0.01 * steps, acc, gyr, btn)
                self._handle_requests()
                await asyncio.sleep(0.01)
        self.connected = False
        self.status = "Bluetooth pen disconnected - keyboard still works"

    # ---- per-sample work (same steps as live_draw.Canvas, without matplotlib)
    def _sample(self, dt, acc, gyr, btn):
        t = self.tracker
        self.connected = True
        t.update(dt, acc, gyr)
        if btn != self._last_btn:               # pen-down button / grip squeeze, if wired
            self._last_btn = btn
            if bool(btn) != (self._rec is not None):
                self.toggle_recording()
        self._handle_requests()
        if self._rec is not None and t.calibrated:
            r = self._rec
            r["t"].append(r["t"][-1] + dt if r["t"] else 0.0)
            r["acc"].append(list(acc))
            r["gyr"].append(list(gyr))
            self.path.append((t.x, t.y))
        if not t.calibrated:
            self.status = t.status
        elif self._rec is None and not self.status.startswith(("Too short", "Predicted")):
            self.status = "Pen ready - press SPACE, write a letter, press SPACE"

    def _handle_requests(self):
        with self._lock:
            toggle, recal = self._toggle, self._recal
            self._toggle = self._recal = False
        if recal:
            self._rec = None
            self.recording = False
            self.tracker.start_calibration()
        if toggle:
            if self._rec is None:
                self._start()
            else:
                self._finish()

    def _start(self):
        if not self.tracker.calibrated:
            self.status = "Wait for calibration to finish (hold the pen still)"
            return
        self.tracker.recenter()
        self._rec = {"t": [], "acc": [], "gyr": []}
        self.path = [(0.0, 0.0)]
        self.recording = True
        self.status = "WRITING... press SPACE when the letter is done"

    def _finish(self):
        import numpy as np
        rec, self._rec = self._rec, None
        self.recording = False
        dur = rec["t"][-1] if rec["t"] else 0.0
        if dur < self.ld.MIN_RECORD_S:
            self.status = f"Too short ({dur:.2f} s) - try again"
            return
        top, _, _ = self.lp.classify(np.array(rec["acc"]), np.array(rec["gyr"]) - self.tracker.bias)
        self.results.put(top)
        self.status = "Predicted: " + ", ".join(f"{c.upper()} {100 * p:.0f}%" for c, p in top)


def letter_matches(ghost_letter, predicted, merge):
    """Model classes can be merged (e.g. 'o' = O/o, 'l' = I/l) or lowercase: compare in uppercase."""
    return predicted.upper() == ghost_letter or merge.get(ghost_letter) == predicted


# ================================================================= drawing helpers
def font(size, w):
    return pg.font.Font(None, int(size * w / 800))


def draw_center(screen, surf, x, y):
    screen.blit(surf, surf.get_rect(center=(x, y)))


def draw_pen_panel(screen, pen, rect):
    """Small box that shows the letter being written, like live_draw's canvas."""
    pg.draw.rect(screen, (25, 25, 45), rect, border_radius=10)
    pg.draw.rect(screen, (255, 80, 80) if pen.recording else (90, 90, 130), rect, 3, border_radius=10)
    pts = list(pen.path)
    if len(pts) > 1:
        view = max(30.0, *(abs(c) + 5 for p in pts for c in p))
        s = (rect.width / 2 - 10) / view
        mapped = [(rect.centerx + x * s, rect.centery - y * s) for x, y in pts]
        pg.draw.lines(screen, (90, 170, 255), False, mapped, 4)
        pg.draw.circle(screen, (60, 200, 90), mapped[0], 6)


def load_ghost_image():
    if os.path.exists(GHOST_IMG):
        img = pg.image.load(GHOST_IMG).convert_alpha()
        scale = GHOST_HEIGHT / img.get_height()
        return pg.transform.smoothscale(img, (int(img.get_width() * scale), GHOST_HEIGHT))
    surf = pg.Surface((GHOST_HEIGHT, GHOST_HEIGHT), pg.SRCALPHA)       # fallback ghost
    pg.draw.ellipse(surf, (235, 235, 255, 220), (10, 0, GHOST_HEIGHT - 20, GHOST_HEIGHT - 10))
    return surf


def handle_window_keys(event):
    if event.type == pg.QUIT:
        pg.quit()
        sys.exit()
    if event.type == pg.KEYDOWN:
        full = pg.display.is_fullscreen()
        if event.key == pg.K_F11 or (event.key == pg.K_ESCAPE and full):
            pg.display.toggle_fullscreen()
            return True
    return False


# ================================================================= screens
def startScreen(screen, window_width, window_height, clock, ghost_img):
    title_font, big = font(72, window_width), font(64, window_width)
    title = title_font.render('GHOSTBUSTERS', True, (120, 255, 140))
    sub = font(26, window_width).render('Write letters in the air to bust the ghosts', True, 'white')
    prompt = big.render('Select Difficulty', True, 'white')
    easy_rect = big.render('Easy', True, 'white').get_rect(center=(window_width / 3, window_height * 0.75))
    hard_rect = big.render('Hard', True, 'white').get_rect(center=(window_width * 2 / 3, window_height * 0.75))
    t0 = time.time()

    while True:
        mouse = pg.mouse.get_pos()
        for event in pg.event.get():
            handle_window_keys(event)
            if event.type == pg.MOUSEBUTTONDOWN and easy_rect.collidepoint(mouse):
                return 'Easy'
            if event.type == pg.MOUSEBUTTONDOWN and hard_rect.collidepoint(mouse):
                return 'Hard'
            if event.type == pg.KEYDOWN and event.key in (pg.K_1, pg.K_e):
                return 'Easy'
            if event.type == pg.KEYDOWN and event.key in (pg.K_2, pg.K_h):
                return 'Hard'

        screen.fill((10, 8, 25))
        bob = math.sin((time.time() - t0) * 2) * 12
        screen.blit(ghost_img, ghost_img.get_rect(center=(window_width * 0.15, window_height * 0.35 + bob)))
        screen.blit(pg.transform.flip(ghost_img, True, False),
                    ghost_img.get_rect(center=(window_width * 0.85, window_height * 0.35 - bob)))
        draw_center(screen, title, window_width / 2, window_height * 0.25)
        draw_center(screen, sub, window_width / 2, window_height * 0.37)
        draw_center(screen, prompt, window_width / 2, window_height * 0.55)
        for text, rect in (('Easy', easy_rect), ('Hard', hard_rect)):
            color = 'red' if rect.collidepoint(mouse) else 'white'
            draw_center(screen, big.render(text, True, color), *rect.center)
        pg.display.update()
        clock.tick(60)


def tutorialScreen(screen, window_width, window_height, clock, difficulty, pen, ghost_img):
    f_title, f_text, f_small = font(48, window_width), font(22, window_width), font(16, window_width)
    s = DIFFICULTY[difficulty]
    lines = [
        "Ghosts float in from the right carrying a letter.",
        "Hold the pen still for a moment so it can calibrate.",
        "Press SPACE, write the ghost's letter in the air (like a laser pointer on a wall), press SPACE again.",
        "Every ghost carrying the letter the pen predicts gets blasted!",
        "If a ghost reaches the left side you lose a life.",
        f"{difficulty}: {s['lives']} lives.",
        "No pen? Type the letter on the keyboard instead.   F5 = recalibrate the pen.",
    ]
    f_letter = font(26, window_width)
    example = Ghost('A', window_width * 0.12, window_height * 0.8, 0, ghost_img)
    t0 = time.time()
    while True:
        for event in pg.event.get():
            handle_window_keys(event)
            if event.type == pg.KEYDOWN and event.key == pg.K_SPACE:
                return True
            if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE and not pg.display.is_fullscreen():
                return False
            if event.type == pg.KEYDOWN and event.key == pg.K_F5:
                pen.recalibrate()

        screen.fill((10, 8, 25))
        draw_center(screen, f_title.render('How to play', True, (120, 255, 140)), window_width / 2, window_height * 0.1)
        for i, line in enumerate(lines):
            draw_center(screen, f_text.render(line, True, 'white'), window_width / 2, window_height * (0.22 + 0.075 * i))
        bob = math.sin((time.time() - t0) * 2) * 10
        example.y = window_height * 0.8 + bob
        example.draw(screen, f_letter)
        draw_center(screen, f_small.render(f"Pen: {pen.status}", True, (180, 180, 220)),
                    window_width / 2, window_height * 0.75)
        if int((time.time() - t0) * 2) % 2 == 0:
            draw_center(screen, f_text.render('Press SPACE to start', True, (255, 220, 90)),
                        window_width / 2, window_height * 0.94)
        pg.display.update()
        clock.tick(60)


class Ghost:
    def __init__(self, letter, x, y, speed, img):
        self.letter, self.x, self.y0, self.speed, self.img = letter, x, y, speed, img
        self.phase = random.uniform(0, math.tau)
        self.y = y

    def update(self, dt, t):
        self.x -= self.speed * dt
        self.y = self.y0 + math.sin(t * 2 + self.phase) * 18

    def draw(self, screen, letter_font):
        rect = self.img.get_rect(center=(self.x, self.y))
        screen.blit(self.img, rect)
        badge = (int(self.x), int(self.y))           # letter in the centre of the ghost
        r = int(30 * S)
        disk = pg.Surface((2 * r, 2 * r), pg.SRCALPHA)
        pg.draw.circle(disk, (255, 255, 255, 200), (r, r), r - 2)
        pg.draw.circle(disk, (40, 40, 40, 255), (r, r), r - 2, 3)
        screen.blit(disk, disk.get_rect(center=badge))
        draw_center(screen, letter_font.render(self.letter, True, (20, 20, 20)), *badge)


def mainGame(screen, window_width, window_height, clock, difficulty, pen, ghost_img):
    s = DIFFICULTY[difficulty]
    merge = getattr(getattr(pen, "lp", None), "MERGE", {}) or {}
    f_hud, f_letter, f_msg = font(24, window_width), font(26, window_width), font(18, window_width)
    speed = (window_width + GHOST_HEIGHT) / s['cross_time']
    player = (90 * S, window_height / 2)
    ghosts, beams, pops = [], [], []
    score, lives, streak = 0, s['lives'], 0
    spawn_gap, next_spawn = s['spawn_gap'], 1.0
    last_guess = ""
    t = 0.0
    while not pen.results.empty():          # drop predictions made during the tutorial
        pen.results.get_nowait()

    def fire(guesses, source):
        nonlocal score, streak, last_guess
        letters = [c for c, _ in guesses[:s['top_n']]]
        hit = [g for g in ghosts if any(letter_matches(g.letter, c, merge) for c in letters)]
        for g in hit:
            ghosts.remove(g)
            beams.append([g.x, g.y, BEAM_TIME])
            pops.append([g.x, g.y, 0.0])
        streak = streak + 1 if hit else 0
        score += len(hit) * 100 * (1 + min(streak, 5) // 2)
        shown = ", ".join(f"{c.upper()} {100 * p:.0f}%" for c, p in guesses) if source == "pen" else guesses[0][0]
        last_guess = f"{source}: {shown}  ->  {len(hit)} ghost{'s' if len(hit) != 1 else ''} busted"

    while True:
        dt = clock.tick(60) / 1000
        t += dt
        for event in pg.event.get():
            if handle_window_keys(event):
                continue
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    return score
                if event.key == pg.K_SPACE:
                    pen.toggle_recording()
                elif event.key == pg.K_F5:
                    pen.recalibrate()
                elif event.unicode and event.unicode.upper() in LETTERS:
                    fire([(event.unicode.upper(), 1.0)], "keyboard")

        while not pen.results.empty():
            fire(pen.results.get_nowait(), "pen")

        # spawning: never two ghosts with the same letter on screen, gets faster with score
        next_spawn -= dt
        if next_spawn <= 0 and len(ghosts) < s['max_ghosts']:
            free = [c for c in LETTERS if c not in {g.letter for g in ghosts}]
            y = random.uniform(GHOST_HEIGHT, window_height - GHOST_HEIGHT)
            boost = 1 + min(score / 3000, 0.6)
            ghosts.append(Ghost(random.choice(free), window_width + GHOST_HEIGHT, y, speed * boost, ghost_img))
            spawn_gap = max(s['min_gap'], spawn_gap * 0.95)
            next_spawn = spawn_gap

        for g in ghosts[:]:
            g.update(dt, t)
            if g.x < player[0]:
                ghosts.remove(g)
                lives -= 1
                streak = 0
                pops.append([g.x, g.y, 0.0])
                if lives <= 0:
                    return score

        # ---- draw
        screen.fill((10, 8, 25))
        for i in range(0, window_width, 80):                       # faint floor grid
            pg.draw.line(screen, (22, 20, 45), (i, 0), (i, window_height))
        pg.draw.line(screen, (120, 40, 40), (player[0], 0), (player[0], window_height), 3)
        pg.draw.circle(screen, (90, 200, 255), player, 30 * S)         # the buster
        pg.draw.circle(screen, (255, 255, 255), player, 30 * S, 3)
        for g in ghosts:
            g.draw(screen, f_letter)
        for b in beams[:]:
            b[2] -= dt
            if b[2] <= 0:
                beams.remove(b)
                continue
            for w, col in ((14, (255, 120, 40)), (6, (255, 240, 120))):
                pts = [player]
                for k in range(1, 9):                               # wiggly proton stream
                    f = k / 8
                    pts.append((player[0] + (b[0] - player[0]) * f,
                                player[1] + (b[1] - player[1]) * f + random.uniform(-14, 14) * (k < 8)))
                pg.draw.lines(screen, col, False, pts, w)
        for p in pops[:]:
            p[2] += dt
            if p[2] > 0.4:
                pops.remove(p)
                continue
            pg.draw.circle(screen, (255, 230, 150), (int(p[0]), int(p[1])), int((20 + 140 * p[2]) * S), 4)

        hud = f"Score {score}     Lives {lives}    {difficulty}"
        screen.blit(f_hud.render(hud, True, 'white'), (150 * S, 15 * S))
        panel = pg.Rect(window_width - 230 * S, window_height - 230 * S, 210 * S, 210 * S)
        draw_pen_panel(screen, pen, panel)
        status_col = (255, 110, 110) if pen.recording else (190, 190, 230)
        status = f_msg.render(f"Pen: {pen.status}", True, status_col)
        screen.blit(status, status.get_rect(topright=(window_width - 20 * S, 20 * S)))
        if last_guess:
            screen.blit(f_msg.render(last_guess, True, (255, 220, 90)), (150 * S, window_height - 40 * S))
        pg.display.update()


def endScreen(screen, window_width, window_height, clock, score):
    big, small = font(64, window_width), font(26, window_width)
    while True:
        for event in pg.event.get():
            if handle_window_keys(event):
                continue
            if event.type in (pg.KEYDOWN, pg.MOUSEBUTTONDOWN):
                return
        screen.fill((10, 8, 25))
        draw_center(screen, big.render('GAME OVER', True, (255, 90, 90)), window_width / 2, window_height * 0.4)
        draw_center(screen, small.render(f'Score: {score}', True, 'white'), window_width / 2, window_height * 0.55)
        draw_center(screen, small.render('Press any key for the menu', True, (180, 180, 220)),
                    window_width / 2, window_height * 0.7)
        pg.display.update()
        clock.tick(30)


# ================================================================= main loop
def fit_window():
    """Shrink the window (keeping 2:1) so it and its title bar fit on this screen with room
    for the taskbar. Drag the window edge or maximise it to make it bigger; F11 = fullscreen."""
    global WINDOW_WIDTH, WINDOW_HEIGHT, S, GHOST_HEIGHT
    try:
        desk_w, desk_h = pg.display.get_desktop_sizes()[0]
    except Exception:
        desk_w, desk_h = 1280, 720
    w = int(min(1600, desk_w * 0.85, desk_h * 0.75 * 2)) // 2 * 2
    S = w / 1600
    WINDOW_WIDTH, WINDOW_HEIGHT = w, w // 2
    GHOST_HEIGHT = int(170 * S)


def main():
    pg.init()
    pg.display.set_caption("Ghostbusters - Magic Wand")
    clock = pg.time.Clock()
    fit_window()
    os.environ["SDL_VIDEO_CENTERED"] = "1"      # open in the middle so the title bar is on screen
    screen = pg.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pg.SCALED | pg.RESIZABLE)
    ghost_img = load_ghost_image()

    pen = PenPredictor()        # starts loading live_predict + connecting while you pick a difficulty
    pen.start()
    try:
        while True:
            difficulty = startScreen(screen, WINDOW_WIDTH, WINDOW_HEIGHT, clock, ghost_img)
            if not tutorialScreen(screen, WINDOW_WIDTH, WINDOW_HEIGHT, clock, difficulty, pen, ghost_img):
                continue
            score = mainGame(screen, WINDOW_WIDTH, WINDOW_HEIGHT, clock, difficulty, pen, ghost_img)
            endScreen(screen, WINDOW_WIDTH, WINDOW_HEIGHT, clock, score)
    finally:
        pen.stop = True         # lets the thread close the COM port


if __name__ == "__main__":
    main()
