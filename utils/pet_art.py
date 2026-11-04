import math

from PIL import Image, ImageDraw

from utils import cosmetics

SS = 2
BASE = 600
SCALES = [0.74, 0.84, 0.92, 1.0, 1.0]
INK = (38, 34, 44)
PINK = (255, 170, 185)
WHITE = (255, 255, 255)


class Art:
    def __init__(self, k):
        self.k = k
        self.img = Image.new("RGBA", (BASE * SS, BASE * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def t(self, x, y):
        return ((300 + (x - 300) * self.k) * SS, (540 + (y - 540) * self.k) * SS)

    def ell(self, cx, cy, rx, ry, fill, outline=None, w=0):
        x0, y0 = self.t(cx - rx, cy - ry)
        x1, y1 = self.t(cx + rx, cy + ry)
        self.d.ellipse((x0, y0, x1, y1), fill=fill, outline=outline, width=int(w * SS * self.k))

    def poly(self, points, fill, outline=None):
        self.d.polygon([self.t(*p) for p in points], fill=fill, outline=outline)

    def line(self, points, fill, w):
        self.d.line([self.t(*p) for p in points], fill=fill, width=max(1, int(w * SS * self.k)), joint="curve")

    def rrect(self, x0, y0, x1, y1, fill, r=10):
        a = self.t(x0, y0)
        b = self.t(x1, y1)
        self.d.rounded_rectangle((a[0], a[1], b[0], b[1]), radius=int(r * SS * self.k), fill=fill)

    def arc(self, cx, cy, rx, ry, start, end, fill, w):
        x0, y0 = self.t(cx - rx, cy - ry)
        x1, y1 = self.t(cx + rx, cy + ry)
        self.d.arc((x0, y0, x1, y1), start, end, fill=fill, width=max(1, int(w * SS * self.k)))


def shade(color, amount):
    return tuple(max(0, min(255, int(c + amount))) for c in color)


def back_layer(a, species, spec, outfit):
    body, accent = spec["body"], spec["accent"]
    if outfit == "cape":
        a.poly([(205, 330), (395, 330), (470, 540), (130, 540)], (200, 50, 70))
        a.poly([(205, 330), (395, 330), (430, 400), (170, 400)], (225, 70, 90))
    if species == "kitten":
        a.line([(380, 470), (470, 450), (500, 390), (480, 340)], shade(body, -18), 30)
        a.ell(480, 340, 16, 16, shade(body, -18))
    elif species == "fox":
        a.ell(450, 450, 62, 92, body)
        a.ell(468, 392, 34, 44, WHITE)
    elif species == "puppy":
        a.line([(385, 470), (440, 440), (462, 390)], shade(body, -22), 26)
    elif species == "dragon":
        a.poly([(210, 360), (90, 250), (130, 330), (70, 340), (140, 410), (210, 430)], shade(accent, -10))
        a.poly([(390, 360), (510, 250), (470, 330), (530, 340), (460, 410), (390, 430)], shade(accent, -10))
        a.line([(390, 480), (470, 500), (520, 460), (545, 420)], body, 30)
        a.poly([(545, 400), (575, 430), (535, 440)], accent)
    elif species == "penguin":
        a.poly([(300, 560), (330, 570), (270, 570)], (0, 0, 0, 0))


def body_layer(a, species, spec):
    body, belly, accent = spec["body"], spec["belly"], spec["accent"]
    if species == "chick":
        a.ell(300, 400, 118, 122, body)
        a.ell(300, 420, 80, 84, belly)
        a.ell(190, 410, 28, 52, shade(body, -20))
        a.ell(410, 410, 28, 52, shade(body, -20))
        a.line([(255, 520), (255, 548)], accent, 12)
        a.line([(345, 520), (345, 548)], accent, 12)
        a.line([(235, 552), (275, 552)], accent, 10)
        a.line([(325, 552), (365, 552)], accent, 10)
        return
    if species == "penguin":
        a.ell(300, 410, 108, 128, body)
        a.ell(300, 430, 78, 98, belly)
        a.poly([(200, 380), (150, 470), (205, 450)], shade(body, -12))
        a.poly([(400, 380), (450, 470), (395, 450)], shade(body, -12))
        a.ell(250, 535, 44, 18, accent)
        a.ell(350, 535, 44, 18, accent)
        return
    a.ell(300, 410, 106, 118, body)
    a.ell(300, 430, 70, 82, belly)
    if species == "panda":
        a.ell(190, 400, 34, 62, accent)
        a.ell(410, 400, 34, 62, accent)
        a.ell(240, 512, 44, 28, accent)
        a.ell(360, 512, 44, 28, accent)
    else:
        a.ell(240, 512, 44, 26, shade(body, -10))
        a.ell(360, 512, 44, 26, shade(body, -10))
    if species == "dragon":
        for x in (300, 262, 338):
            a.ell(x, 430, 24, 8, shade(belly, -24))


def head_layer(a, species, spec):
    body, belly, accent = spec["body"], spec["belly"], spec["accent"]
    if species == "kitten":
        a.poly([(185, 175), (205, 85), (275, 150)], body)
        a.poly([(415, 175), (395, 85), (325, 150)], body)
        a.poly([(205, 150), (213, 112), (245, 145)], PINK)
        a.poly([(395, 150), (387, 112), (355, 145)], PINK)
    elif species == "puppy":
        a.ell(172, 240, 38, 78, accent)
        a.ell(428, 240, 38, 78, accent)
    elif species == "fox":
        a.poly([(180, 180), (195, 70), (275, 150)], body)
        a.poly([(420, 180), (405, 70), (325, 150)], body)
        a.poly([(195, 70), (203, 112), (228, 98)], accent)
        a.poly([(405, 70), (397, 112), (372, 98)], accent)
    elif species == "panda":
        a.ell(205, 150, 44, 44, accent)
        a.ell(395, 150, 44, 44, accent)
    elif species == "dragon":
        a.poly([(210, 160), (190, 70), (250, 140)], accent)
        a.poly([(390, 160), (410, 70), (350, 140)], accent)
        a.poly([(285, 135), (300, 90), (315, 135)], accent)
    a.ell(300, 250, 130, 118, belly if species == "penguin" and False else body)
    if species == "fox":
        a.poly([(170, 290), (260, 330), (190, 340)], WHITE)
        a.poly([(430, 290), (340, 330), (410, 340)], WHITE)
        a.ell(300, 305, 70, 50, WHITE)
    elif species == "puppy":
        a.ell(300, 300, 62, 44, belly)
    elif species == "penguin":
        a.ell(300, 268, 100, 84, belly)
    elif species == "kitten":
        a.ell(300, 300, 54, 38, belly)
        for dx in (-30, 0, 30):
            a.line([(300 + dx, 150), (300 + dx, 175)], shade(body, -34), 7)
    elif species == "dragon":
        a.ell(300, 305, 60, 40, shade(belly, -4))
    elif species == "panda":
        a.ell(250, 262, 36, 44, accent)
        a.ell(350, 262, 36, 44, accent)
    if species == "chick":
        a.ell(285, 128, 12, 26, shade(body, -10))
        a.ell(300, 120, 12, 30, shade(body, -10))
        a.ell(315, 128, 12, 26, shade(body, -10))
    for cx in (250, 350):
        a.ell(cx, 262, 16, 22, INK)
        a.ell(cx + 5, 254, 6, 7, WHITE)
        a.ell(cx - 5, 270, 3, 3, WHITE)
    a.ell(218, 304, 20, 12, PINK)
    a.ell(382, 304, 20, 12, PINK)
    if species == "chick":
        a.poly([(278, 285), (322, 285), (300, 318)], accent)
    elif species == "penguin":
        a.poly([(278, 288), (322, 288), (300, 320)], accent)
    elif species == "dragon":
        a.ell(283, 296, 4, 5, INK)
        a.ell(317, 296, 4, 5, INK)
        a.line([(280, 320), (300, 332), (320, 320)], INK, 5)
    else:
        a.poly([(286, 292), (314, 292), (300, 308)], INK if species in ("puppy", "fox", "panda") else (230, 110, 130))
        a.line([(300, 308), (300, 320)], INK, 4)
        a.line([(276, 322), (288, 332), (300, 324), (312, 332), (324, 322)], INK, 4)
    if species == "kitten":
        for side in (-1, 1):
            a.line([(300 + side * 55, 306), (300 + side * 110, 296)], INK, 3)
            a.line([(300 + side * 55, 316), (300 + side * 110, 320)], INK, 3)
    if species == "puppy":
        a.ell(300, 342, 14, 16, (240, 110, 130))


def outfit_layer(a, outfit, spec):
    if outfit == "bandana":
        a.poly([(205, 352), (395, 352), (300, 432)], (210, 52, 62))
        for x, y in ((250, 372), (300, 388), (350, 372), (300, 360)):
            a.ell(x, y, 6, 6, WHITE)
    elif outfit == "bow":
        a.poly([(350, 160), (420, 120), (420, 205)], (255, 110, 160))
        a.poly([(350, 160), (280, 120), (280, 205)], (255, 110, 160))
        a.ell(350, 160, 22, 22, (230, 70, 130))
    elif outfit == "scarf":
        a.rrect(190, 338, 410, 382, (60, 150, 220), 20)
        a.rrect(330, 360, 378, 480, (45, 125, 195), 14)
        for y in (380, 410, 440):
            a.line([(334, y), (374, y)], WHITE, 6)
    elif outfit == "glasses":
        for cx in (250, 350):
            a.ell(cx, 262, 36, 34, (190, 225, 255), INK, 6)
        a.line([(286, 258), (314, 258)], INK, 6)
        a.line([(214, 256), (176, 244)], INK, 6)
        a.line([(386, 256), (424, 244)], INK, 6)
    elif outfit == "partyhat":
        a.poly([(300, 20), (225, 150), (375, 150)], (120, 90, 230))
        a.poly([(300, 20), (262, 150), (300, 150)], (150, 120, 255))
        for x, y, c in ((285, 90, (255, 220, 80)), (320, 110, (255, 120, 160)), (270, 128, (110, 220, 190))):
            a.ell(x, y, 8, 8, c)
        a.ell(300, 18, 20, 20, (255, 220, 80))
    elif outfit == "headphones":
        a.arc(300, 250, 138, 132, 190, 350, (60, 60, 72), 22)
        a.ell(160, 262, 30, 50, (80, 200, 170))
        a.ell(440, 262, 30, 50, (80, 200, 170))
        a.ell(160, 262, 16, 34, (40, 40, 52))
        a.ell(440, 262, 16, 34, (40, 40, 52))
    elif outfit == "cape":
        a.ell(300, 345, 16, 16, (255, 210, 80))
    elif outfit == "wizard":
        a.poly([(300, -10), (205, 150), (395, 150)], (70, 50, 150))
        a.ell(300, 150, 118, 24, (60, 42, 130))
        a.ell(285, 80, 9, 9, (255, 230, 120))
        a.ell(325, 118, 7, 7, (255, 230, 120))
        a.ell(272, 125, 6, 6, (255, 230, 120))
    elif outfit == "crown":
        a.poly([(215, 158), (385, 158), (400, 70), (350, 108), (300, 52), (250, 108), (200, 70)], (255, 204, 60))
        a.rrect(215, 150, 385, 172, (240, 176, 30), 8)
        for x, c in ((250, (230, 70, 90)), (300, (90, 170, 240)), (350, (230, 70, 90))):
            a.ell(x, 160, 8, 8, c)


def legendary_layer(a):
    a.arc(300, 70, 72, 20, 0, 360, (255, 224, 120), 8)
    for x, y, r in ((90, 120, 14), (520, 160, 18), (70, 330, 10), (540, 360, 12), (140, 60, 9), (470, 50, 11)):
        a.poly([(x, y - r * 1.6), (x + r * 0.5, y - r * 0.5), (x + r * 1.6, y), (x + r * 0.5, y + r * 0.5), (x, y + r * 1.6), (x - r * 0.5, y + r * 0.5), (x - r * 1.6, y), (x - r * 0.5, y - r * 0.5)], (255, 232, 140))


def render(species: str, xp: int, outfit: str = "", size: int = 400) -> Image.Image:
    spec = cosmetics.SPECIES.get(species) or cosmetics.SPECIES["kitten"]
    index = cosmetics.stage_index(xp)
    a = Art(SCALES[index])
    back_layer(a, species, spec, outfit)
    body_layer(a, species, spec)
    head_layer(a, species, spec)
    outfit_layer(a, outfit, spec)
    if index == len(cosmetics.STAGES) - 1:
        legendary_layer(a)
    return a.img.resize((size, size), Image.Resampling.LANCZOS)
