"""Pixel-art boat, passengers and airborne Pokémon for the 24-second lake loop."""
from bisect import bisect_right
from math import cos, pi, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

SPRITES = Path(__file__).parent / 'sprites'
PIXEL = Image.Resampling.NEAREST
TAU = 2 * pi


def lit(sprite, light):
    """Keep the ink and silhouette, letting each phase tint the sprite highlights."""
    r, g, b, a = sprite.split()
    return Image.merge('RGBA', (*[ch.point(lambda p, k=k: round(p * k))
                                  for ch, k in zip((r, g, b), light)], a))


def scale(sprite, factor):
    return sprite.resize(tuple(max(1, round(n * factor)) for n in sprite.size), PIXEL)


class Cycle:
    def __init__(self, frames, durations):
        self.frames = frames
        self.ends = []
        for duration in durations:
            self.ends.append((self.ends[-1] if self.ends else 0) + duration)
        self.cycles = max(1, round(24_000 / self.ends[-1]))

    def at(self, t, offset=0):
        pos = (self.cycles * t + offset) % 1 * self.ends[-1]
        return self.frames[bisect_right(self.ends, pos)]


def gif_cycle(species, width, light, *, mirror=False):
    with Image.open(SPRITES / f'{species}.gif') as gif:
        frames, durations = [], []
        for i in range(gif.n_frames):
            gif.seek(i)
            frame = gif.convert('RGBA')
            frames.append(frame.crop(frame.getbbox()))
            durations.append(gif.info.get('duration', 100))
    factor = width / max(f.width for f in frames)
    return Cycle([lit(scale(ImageOps.mirror(f) if mirror else f, factor), light)
                  for f in frames], durations)


def bird_cycle(species, size, light):
    with Image.open(SPRITES / f'{species:04}-hover.png') as png:
        sheet = png.convert('RGBA')
    width, height = {396: (24, 48), 397: (32, 56), 398: (32, 64)}[species]
    # SpriteCollab row 2 is the right-facing profile. Keep its shared origin so
    # feet and head stay steady while the wings change shape.
    frames = [sheet.crop((x, 2 * height, x + width, 3 * height))
              for x in range(0, sheet.width, width)]
    return Cycle([lit(scale(frame, size / width), light) for frame in frames],
                 [85] * len(frames))


class LakeTraffic:
    def __init__(self, lake, mode, step):
        self.lake = lake
        self.w, self.h = lake.size
        brightness = {'day': 1, 'night': 0.54}.get(mode, 0.54 + step * .054)
        warm = sin(pi * step / 9) if mode in ('rise', 'set') else 0
        self.light = (min(1, brightness + warm * .08), brightness,
                      min(1, brightness + (1 - brightness) * .34 - warm * .04))
        self.flock = [(bird_cycle(species, size, self.light), lead, level, seed)
                      for species, size, lead, level, seed in [
                          (396, 32, -.069, .166, .12), (397, 43, -.036, .143, .39),
                          (398, 53, 0, .155, .77), (396, 29, -.092, .147, .93)]]
        self.gull = gif_cycle(278, 63, self.light)
        self.balloon = gif_cycle(425, 30, self.light, mirror=True)
        self.bat = gif_cycle(41, 40, self.light)
        self.passengers = [(gif_cycle(s, width, self.light, mirror=turn), x, seat, seed)
                           for s, width, turn, x, seat, seed in [
                               (393, 30, True, 31, 32, .4), (387, 39, False, 59, 31, .1),
                               (390, 31, False, 87, 31, .73)]]
        # Trace the near bank in the original pixel artwork. The boat disappears
        # behind these rocky ledges and spruce branches at the west end of its run.
        mask = Image.new('L', lake.size)
        boundary = [(0, 508), (155, 508), (145, 523), (184, 535), (171, 538),
                    (189, 541), (170, 552), (160, 553), (178, 571), (193, 577),
                    (182, 589), (164, 585), (164, 599), (193, 613), (202, 623),
                    (187, 625), (214, 633), (198, 648), (225, 635), (234, 603),
                    (235, 632), (255, 635), (242, 643), (260, 662), (243, 665),
                    (275, 688), (0, 712)]
        ImageDraw.Draw(mask).polygon(boundary, fill=255)
        self.bank = mask
        self.hull = self.make_hull()

    def make_hull(self):
        hull = Image.new('RGBA', (119, 48))
        d = ImageDraw.Draw(hull)
        # A clinker-built lake launch, viewed just above the port gunwale.
        d.polygon([(2, 25), (15, 25), (28, 28), (94, 28), (104, 23), (115, 24),
                   (111, 32), (103, 41), (91, 45), (28, 45), (16, 40), (7, 32)],
                  fill='#342c38')
        d.polygon([(7, 27), (22, 28), (35, 30), (86, 30), (104, 25), (110, 25),
                   (104, 33), (90, 36), (30, 36), (15, 32)], fill='#94654b')
        for x in (28, 53, 80):
            d.polygon([(x, 27), (x+6, 27), (x+13, 32), (x+6, 32)], fill='#d7ad75')
        d.line([(4, 26), (17, 28), (32, 31), (88, 31), (106, 25), (113, 25)],
               fill='#e1bd83', width=2)
        return lit(hull, self.light)

    def boat(self, t):
        boat = self.hull.copy()
        for cycle, x, seat, offset in self.passengers:
            frame = scale(cycle.at(t, offset), .5)
            boat.alpha_composite(frame, (x-frame.width//2, seat-frame.height))
        # The near gunwale covers the passengers' feet so they stay seated.
        front = Image.new('RGBA', boat.size)
        d = ImageDraw.Draw(front)
        d.polygon([(3, 26), (19, 31), (33, 33), (88, 33), (106, 29), (114, 25),
                   (110, 33), (99, 41), (86, 44), (30, 44), (17, 39), (8, 32)],
                  fill='#733f37', outline='#392f3a')
        d.line([(4, 27), (20, 32), (33, 34), (87, 34), (105, 30), (113, 26)],
               fill='#f2cb8d', width=2)
        d.line([(15, 35), (30, 39), (87, 39), (101, 36)], fill='#c38352')
        d.line([(26, 41), (35, 43), (84, 43), (93, 41)], fill='#59404b')
        for x in (24, 47, 72, 98):
            d.point((x, 37), fill='#e2ab72')
        d.line((11, 27, 11, 18), fill='#4b3535', width=2)
        d.rectangle((9, 18, 13, 22), fill='#734e3a')
        d.rectangle((10, 19, 12, 21), fill='#ffde86')
        boat.alpha_composite(lit(front, self.light))
        return scale(boat, 2)

    def draw_boat(self, sheet, top, t):
        # Wrap while the entire boat and wake are off camera.
        x = round(self.w + 155 - ((t + .39) % 1) * (self.w + 345))
        y = round(self.h * (.655 + .008 * sin(TAU * (t+.13))) + 1.5 * sin(7*TAU*t))
        boat = self.boat(t)
        left = x - boat.width // 2
        ly = y - top
        reflection = ImageOps.flip(boat).resize((boat.width, 24), PIXEL)
        for row in range(1, 21, 3):
            strip = reflection.crop((0, row, boat.width, row+2))
            strip.putalpha(strip.getchannel('A').point(lambda a: round(a * (.19 - row*.007))))
            sheet.alpha_composite(strip, (left+round(3*sin(28*TAU*t+row)), ly+row-1))
        d = ImageDraw.Draw(sheet)
        for i in range(8):
            p = (4*t + i/8) % 1
            wx = x + round(77 + 90*p)
            wy = ly + round((4 + 10*p) * (1 if i%2 else -.45))
            sample = self.lake.getpixel((max(0, min(self.w-1, wx)), wy+top))
            tint = tuple(round(c+(208-c)*(.30-.24*p)) for c in sample)
            d.line((wx, wy, wx+round(5+12*p), wy), fill=tint, width=2)
        sheet.alpha_composite(boat, (left, ly-90))
        if left < 278:
            box = (0, top, 278, top+sheet.height)
            sheet.paste(self.lake.crop(box), (0, 0), self.bank.crop(box))

    def sky(self, frame, t):
        def place(cycle, x, y, offset):
            sprite = cycle.at(t, offset)
            frame.paste(sprite, (round(x-sprite.width/2), round(y-sprite.height/2)), sprite)
        lead = -60 + ((t+.57) % 1) * (self.w*1.1 + 130)
        for cycle, offset, level, seed in self.flock:
            place(cycle, lead+offset*self.w+4*cos(TAU*(2*t+seed)),
                  self.h*level + 11*sin(TAU*(2*t+seed)) + 2*sin(TAU*(9*t+seed)), seed)
        place(self.gull, self.w+50-((t+.18)%1)*(self.w+100),
              self.h*(.21+.029*sin(TAU*(2*t+.08))), .22)
        place(self.bat, self.w+45-((t+.76)%1)*(self.w+90),
              self.h*(.254+.024*sin(3*TAU*t)) + 3*sin(14*TAU*t), .57)
        # Drifloon drifts in a small arc as the faster fliers sweep across the sky.
        place(self.balloon, self.w*(.78+.075*sin(TAU*t)),
              self.h*(.103+.021*sin(2*TAU*t+.8)), .41)
