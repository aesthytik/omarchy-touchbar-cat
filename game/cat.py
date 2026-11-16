#!/usr/bin/env python3
"""Box Cat: a cat jumping over boxes on the MacBook Touch Bar.

Draws on the whole Touch Bar through tiny-dfr-plus's takeover socket and gets
Space/Esc/Up and touches back from it. Space, Up or a tap jumps; Esc or the
x at the right end quits. The best score is kept in
~/.local/state/touchbar-cat/highscore.
"""
import os
import random
import select
import socket
import struct
import time

W, H = 1085, 30          # logical pixels; tiny-dfr scales them 2x to the 2170x60 bar
GROUND = 27              # y of the ground line
FPS = 50
TAKEOVER = b"\0tiny-dfr-takeover"
KEY_ESC, KEY_SPACE, KEY_UP = 1, 57, 103
QUIT_ZONE_PX = 70        # physical pixels at the right end that quit when tapped

GRAVITY = 1500.0
JUMP_V = -235.0
START_SPEED, MAX_SPEED, ACCEL = 170.0, 430.0, 5.0
CAT_X = 40


def rgb(r, g, b):
    """RGB332 byte."""
    return (r >> 5) << 5 | (g >> 5) << 2 | (b >> 6)


BLACK = rgb(0, 0, 0)
ORANGE = rgb(255, 150, 40)
CREAM = rgb(255, 220, 160)
EYE = rgb(120, 255, 120)
BOX = rgb(205, 140, 60)
BOX_DARK = rgb(130, 80, 30)
GROUND_C = rgb(90, 90, 90)
TEXT = rgb(230, 230, 230)
DIM = rgb(120, 120, 120)
RED = rgb(255, 90, 90)

# 16x10 cat facing right. o = orange, c = cream, e = eye.
CAT_BODY = [
    "............o..o",
    "o...........oooo",
    ".o.........ooeoe",
    ".o.........oocco",
    "..ooooooooooooo.",
    "...ooocccccooo..",
    "...oooooooooo...",
]
CAT_LEGS = [
    ["...oo.....oo....", "...o.......o....", "..o.......o....."],
    ["....oo...oo.....", "....o.....o.....", ".....o...o......"],
]
CAT_JUMP_LEGS = ["..oo.......oo...", ".o...........o..", "................"]
COLORS = {"o": ORANGE, "c": CREAM, "e": EYE}

FONT = {  # 3x5
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111",
    "3": "111001111001111", "4": "101101111001001", "5": "111100111001111",
    "6": "111100111101111", "7": "111001010010010", "8": "111101111101111",
    "9": "111101111001111", "A": "010101111101101", "C": "111100100100111",
    "E": "111100110100111", "G": "111100101101111", "H": "101101111101101",
    "I": "111010010010111", "M": "101111111101101", "O": "111101101101111",
    "P": "111101111100100", "R": "110101110101101", "S": "111100111001111",
    "T": "111010010010010", "V": "101101101101010", "X": "101101010101101",
    "Y": "101101010010010", "U": "101101101101111", "N": "110101101101101",
    "L": "100100100100111", "Q": "111101101111001", " ": "000000000000000",
    ":": "000010000010000", "/": "001001010100100",
}


class Image:
    """A small pre-rendered picture, copied onto the screen row by row."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.rows = [bytearray(w) for _ in range(h)]

    def put(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.rows[y][x] = c


def sprite_image(rows):
    img = Image(len(rows[0]), len(rows))
    for y, line in enumerate(rows):
        for x, ch in enumerate(line):
            if ch in COLORS:
                img.put(x, y, COLORS[ch])
    return img


_text_cache = {}


def text_image(s, c, scale=1):
    key = (s, c, scale)
    if key not in _text_cache:
        img = Image(max(1, len(s) * 4 * scale - scale), 5 * scale)
        for n, ch in enumerate(s.upper()):
            for i, bit in enumerate(FONT.get(ch, FONT[" "])):
                if bit == "1":
                    for yy in range(scale):
                        for xx in range(scale):
                            img.put(n * 4 * scale + (i % 3) * scale + xx, (i // 3) * scale + yy, c)
        if len(_text_cache) > 256:
            _text_cache.clear()
        _text_cache[key] = img
    return _text_cache[key]


CAT_RUN = [sprite_image(CAT_BODY + legs) for legs in CAT_LEGS]
CAT_JUMP = sprite_image(CAT_BODY + CAT_JUMP_LEGS)


class Screen:
    def __init__(self):
        self.buf = bytearray(W * H)
        self.blank = bytes(W * H)
        self.ground = bytes(([GROUND_C] * 8 + [BLACK] * 4) * (W // 12 + 2))

    def clear(self):
        self.buf[:] = self.blank

    def rect(self, x, y, w, h, c):
        x0, x1 = max(0, int(x)), min(W, int(x + w))
        if x1 <= x0:
            return
        row = bytes([c]) * (x1 - x0)
        for yy in range(max(0, int(y)), min(H, int(y + h))):
            o = yy * W
            self.buf[o + x0:o + x1] = row

    def blit(self, img, x, y):
        """Opaque copy: the image's black pixels overwrite what's under them."""
        x, y = int(x), int(y)
        x0, x1 = max(0, x), min(W, x + img.w)
        if x1 <= x0:
            return
        for dy, row in enumerate(img.rows):
            yy = y + dy
            if 0 <= yy < H:
                o = yy * W
                self.buf[o + x0:o + x1] = row[x0 - x:x1 - x]

    def ground_line(self, offset):
        o = GROUND * W
        self.buf[o:o + W] = self.ground[offset:offset + W]

    def text(self, s, x, y, c, scale=1):
        self.blit(text_image(s, c, scale), x, y)

    @staticmethod
    def text_width(s, scale=1):
        return len(s) * 4 * scale - scale


def state_file():
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "touchbar-cat", "highscore")


def load_high():
    try:
        with open(state_file()) as f:
            return max(0, int(f.read().strip()[:12]))
    except (OSError, ValueError):
        return 0


def save_high(score):
    path = state_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(str(score))
    os.replace(tmp, path)


class Game:
    def __init__(self):
        self.high = load_high()
        self.state = "ready"
        self.reset()

    def reset(self):
        self.y = 0.0          # height above the ground, px (up is negative)
        self.vy = 0.0
        self.speed = START_SPEED
        self.dist = 0.0
        self.boxes = []       # [x, w, h]
        self.next_box = W + 40
        self.t = 0.0

    @property
    def score(self):
        return int(self.dist / 10)

    def jump(self):
        if self.state == "ready":
            self.state = "running"
        elif self.state == "over":
            if self.t > 0.4:      # don't restart from the same key press that ended it
                self.reset()
                self.state = "running"
            return
        if self.y == 0.0:
            self.vy = JUMP_V

    def update(self, dt):
        self.t += dt
        if self.state != "running":
            return
        self.speed = min(MAX_SPEED, self.speed + ACCEL * dt)
        self.dist += self.speed * dt
        self.vy += GRAVITY * dt
        self.y = min(0.0, self.y + self.vy * dt)
        if self.y == 0.0:
            self.vy = 0.0
        for b in self.boxes:
            b[0] -= self.speed * dt
        self.boxes = [b for b in self.boxes if b[0] + b[1] > 0]
        self.next_box -= self.speed * dt
        if self.next_box <= W:
            w = random.choice((7, 8, 9, 10, 12))
            h = random.choice((6, 7, 8, 9, 11))
            self.boxes.append([float(W), w, h])
            if random.random() < 0.25 and self.speed > 230:   # a second box right behind
                self.boxes.append([float(W + w + 1), random.choice((7, 8)), random.choice((6, 7))])
            gap = self.speed * random.uniform(0.6, 1.3) + 60
            self.next_box = W + gap
        # hit test, a little forgiving
        cx0, cx1 = CAT_X + 3, CAT_X + 14
        cy1 = GROUND + self.y
        for bx, bw, bh in self.boxes:
            if bx < cx1 and bx + bw > cx0 and cy1 > GROUND - bh + 1:
                self.state = "over"
                self.t = 0.0
                if self.score > self.high:
                    self.high = self.score
                    save_high(self.high)
                break

    def draw(self, s):
        s.clear()
        # ground, dashed so it scrolls
        s.ground_line(int(self.dist) % 12)
        for bx, bw, bh in self.boxes:
            s.rect(bx, GROUND - bh, bw, bh, BOX)
            s.rect(bx, GROUND - bh, bw, 1, BOX_DARK)
            s.rect(bx + bw // 2, GROUND - bh, 1, max(2, bh // 3), BOX_DARK)   # tape
        top = int(GROUND + self.y) - 10
        if self.y < 0:
            cat = CAT_JUMP
        else:
            cat = CAT_RUN[int(self.dist / 9) % 2] if self.state == "running" else CAT_RUN[0]
        s.blit(cat, CAT_X, top)
        # right side: score, best, quit
        x = W - 8
        s.rect(x - 1, 4, 1, 1, RED)
        for i in range(5):                       # x mark
            s.rect(x - 2 + i, 2 + i, 1, 1, RED)
            s.rect(x + 2 - i, 2 + i, 1, 1, RED)
        right = W - 18
        hi = "HI %05d" % self.high
        sc = "%05d" % self.score
        s.text(hi, right - s.text_width(hi) - s.text_width(sc, 2) - 10, 9, DIM)
        s.text(sc, right - s.text_width(sc, 2), 6, TEXT, 2)
        if self.state == "ready":
            s.text("PRESS SPACE TO JUMP", 120, 6, TEXT, 2)
            s.text("ESC TO QUIT", 120 + s.text_width("PRESS SPACE TO JUMP", 2) + 16, 9, DIM)
        elif self.state == "over":
            s.text("GAME OVER", 120, 6, RED, 2)
            s.text("SPACE TO RETRY", 120 + s.text_width("GAME OVER", 2) + 16, 9, DIM)


def main():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind("")             # autobind, so tiny-dfr can send keys back
    sock.setblocking(False)
    header = b"TDT1" + struct.pack("<HH", W, H)
    screen, game = Screen(), Game()
    last = time.monotonic()
    while True:
        # Between rounds nothing moves, so 10 frames a second keep the bar alive.
        frame_time = 1.0 / (FPS if game.state == "running" else 10)
        deadline = last + frame_time
        while True:
            wait = deadline - time.monotonic()
            r, _, _ = select.select([sock], [], [], max(0.0, wait))
            if not r:
                break
            try:
                msg = sock.recv(64)
            except BlockingIOError:
                continue
            if len(msg) != 11 or msg[:4] != b"TDE1":
                continue
            kind, code, value = struct.unpack("<BHi", msg[4:])
            if kind == 1 and value == 1:
                if code == KEY_ESC:
                    return
                if code in (KEY_SPACE, KEY_UP):
                    game.jump()
            elif kind == 2:
                if value >= 2 * W - QUIT_ZONE_PX:
                    return
                game.jump()
        now = time.monotonic()
        game.update(min(0.05, now - last))
        last = now
        game.draw(screen)
        try:
            sock.sendto(header + screen.buf, TAKEOVER)
        except (ConnectionRefusedError, FileNotFoundError, BlockingIOError):
            pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
