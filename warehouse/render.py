"""Isometric (2.5D) pygame renderer: open racking, walls, lighting, AGV robots.

1080p-ready: pass resolution=(3840, 2160) (default) and the grid is auto-fitted to the
canvas, with every line width / font / HUD element scaled to match. Pass
resolution=None to get the old behaviour (window sized to the content, `cell` used as-is).
"""
import math
import random

import pygame

UHD = (3840, 2160)

BG_TOP, BG_BOT = (10, 12, 19), (26, 31, 46)
FLOOR_A, FLOOR_B, GRID_LINE = (60, 64, 76), (64, 68, 81), (48, 52, 63)
SLAB_L, SLAB_R = (24, 27, 36), (15, 17, 24)
WALL_A, WALL_B = (66, 74, 98), (48, 54, 74)
STATION, STATION_IN, STATION_BASE = (34, 170, 118), (140, 244, 196), (22, 62, 52)
POST = ((124, 138, 172), (78, 92, 126), (54, 65, 94))
PLANK = ((92, 106, 138), (62, 74, 102), (44, 54, 78))
BEAM = ((246, 158, 56), (196, 124, 40), (150, 96, 30))
CARTONS = [((224, 180, 120), (186, 142, 90), (148, 110, 68)),
           ((208, 163, 106), (170, 128, 80), (134, 98, 60)),
           ((236, 236, 240), (196, 198, 208), (160, 162, 174)),
           ((122, 170, 216), (90, 132, 178), (66, 102, 142))]
TAPE = (236, 226, 190)
LANE = (206, 176, 52)
TEXT, DIM = (225, 230, 240), (130, 138, 156)
HUD_BG, HUD_W = (20, 23, 33), 250
SKY_LOW, SKY_HIGH = (138, 172, 214), (66, 102, 156)


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def box(surf, proj, x0, y0, x1, y1, z0, z1, cols, lw=1):
    """Isometric box; cols = (top, left, right); proj(gx, gy, z) -> screen point."""
    top, left, right = cols
    b1, c1, d1 = proj(x1, y0, z1), proj(x1, y1, z1), proj(x0, y1, z1)
    a1 = proj(x0, y0, z1)
    b0, c0, d0 = proj(x1, y0, z0), proj(x1, y1, z0), proj(x0, y1, z0)
    pygame.draw.polygon(surf, left, [d0, c0, c1, d1])
    pygame.draw.polygon(surf, right, [b0, c0, c1, b1])
    pygame.draw.polygon(surf, top, [a1, b1, c1, d1])
    hi = shade(top, 1.18)                                # lit front edges
    pygame.draw.line(surf, hi, d1, c1, lw)
    pygame.draw.line(surf, hi, c1, b1, lw)
    pygame.draw.line(surf, shade(left, .7), c0, c1, lw)  # dark corner crease


def carton(surf, proj, x0, y0, x1, y1, z0, z1, cols, lw=1):
    box(surf, proj, x0, y0, x1, y1, z0, z1, cols, lw)
    xm = (x0 + x1) / 2                                   # packing tape
    pygame.draw.line(surf, TAPE, proj(xm, y0, z1), proj(xm, y1, z1), lw)
    if int(x0 * 1000 + z0 * 13) % 3 == 0:                # shipping label on right face
        dy, dz = y1 - y0, z1 - z0
        pts = [proj(x1, y0 + dy * .18, z0 + dz * .2), proj(x1, y0 + dy * .55, z0 + dz * .2),
               proj(x1, y0 + dy * .55, z0 + dz * .62), proj(x1, y0 + dy * .18, z0 + dz * .62)]
        pygame.draw.polygon(surf, (244, 244, 246), pts)
        pygame.draw.line(surf, (40, 40, 48), proj(x1, y0 + dy * .24, z0 + dz * .32),
                         proj(x1, y0 + dy * .49, z0 + dz * .32), lw)


class Renderer:
    def __init__(self, sim, cell=26, show_window=True, resolution=UHD):
        pygame.init()
        pygame.font.init()
        self.sim = sim
        g = sim.grid

        if resolution:
            W, Hres = resolution
            self.ui = Hres / 1080.0                       # HUD / font scale (2.0 at 1080p)
            self.hud_w = int(HUD_W * self.ui)
            cell = self._fit_cell(g.w, g.h, W - self.hud_w, Hres)
        else:
            self.ui, self.hud_w = 1.0, HUD_W
        self.cell = cell
        self.k = k = cell / 26.0                          # world-space pixel scale
        self.lw1 = self._w(1)

        self.hw = cell * 0.65                 # half tile width
        self.hh = self.hw * 0.5               # half tile height
        self.shelf_h = self.hh * 3.6
        self.carton_h = self.hh * 0.8
        self.wall_h = self.shelf_h * 1.35
        self.slab = int(10 * k)

        ui = self.ui
        self.font = pygame.font.SysFont("consolas,menlo,dejavusansmono", int(13 * ui))
        self.big = pygame.font.SysFont("consolas,menlo,dejavusansmono", int(20 * ui), bold=True)
        self.lfont = pygame.font.SysFont("consolas,menlo,dejavusansmono", max(9, int(cell * .5)), bold=True)
        fh = self.font.get_height()
        n = min(len(sim.robots), 10)
        hud_h = int(48 * ui + 9 * (fh + 6 * ui) + 10 * ui + n * (fh + 3 * ui) + 110 * ui)

        top, cw, need_h = self._geometry(g.w, g.h, cell)
        top, need_h = int(top), int(need_h)
        if resolution:
            self.H = Hres
            self.map_w = W - self.hud_w
        else:
            self.map_w = int(cw)
            self.H = max(need_h, hud_h)
        self.ox = g.h * self.hw + 10 * k + (self.map_w - cw) / 2
        self.oy = top + (self.H - need_h) // 2
        self.size = (self.map_w + self.hud_w, self.H)

        if show_window:
            try:
                flags = (pygame.SCALED | pygame.RESIZABLE) if resolution else 0
                self.screen = pygame.display.set_mode(self.size, flags)
            except pygame.error:
                self.screen = pygame.display.set_mode(self.size)
            pygame.display.set_caption("Warehouse Fleet Sim - CBS multi-robot planning")
        else:
            self.screen = pygame.Surface(self.size)
        self.overlay = pygame.Surface((self.map_w, self.H), pygame.SRCALPHA)
        self._glows = {}
        self._rsh = None
        self._static = self._render_static()
        self._shelves = self._build_shelves()
        self._vig = self._make_vignette()

    # ------------------------------------------------------------ layout
    @staticmethod
    def _geometry(gw, gh, cell):
        k = cell / 26.0
        hw = cell * 0.65
        hh = hw * 0.5
        shelf_h = hh * 3.6
        carton_h = hh * 0.8
        wall_h = shelf_h * 1.35
        top = max(shelf_h + carton_h, wall_h) + 8 * k
        cw = (gw + gh) * hw + 20 * k
        need_h = top + (gw + gh) * hh + 10 * k + 10 * k
        return top, cw, need_h

    @classmethod
    def _fit_cell(cls, gw, gh, avail_w, avail_h):
        lo, hi = 6.0, 400.0
        for _ in range(32):
            mid = (lo + hi) / 2
            _, cw, nh = cls._geometry(gw, gh, mid)
            if cw <= avail_w * 0.97 and nh <= avail_h * 0.97:
                lo = mid
            else:
                hi = mid
        return lo

    def _w(self, n):
        return max(1, int(round(n * self.k)))

    def to_bytes(self):
        return pygame.image.tostring(self.screen, "RGB")

    def save_png(self, path):
        pygame.image.save(self.screen, path)

    # ------------------------------------------------------------ geometry
    def P(self, gx, gy, z=0.0):
        return (self.ox + (gx - gy) * self.hw, self.oy + (gx + gy) * self.hh - z)

    def tile(self, x, y, inset=0.0):
        i = inset
        return [self.P(x + i, y + i), self.P(x + 1 - i, y + i),
                self.P(x + 1 - i, y + 1 - i), self.P(x + i, y + 1 - i)]

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _blur(surf, f=3):
        w, h = surf.get_size()
        small = pygame.transform.smoothscale(surf, (max(1, w // f), max(1, h // f)))
        return pygame.transform.smoothscale(small, (w, h))

    @staticmethod
    def _radial(rx, ry, col, steps=28):
        """Black-background radial gradient sprite meant for BLEND_RGB_ADD."""
        spr = pygame.Surface((int(rx * 2) + 2, int(ry * 2) + 2), 0, 32)
        spr.fill((0, 0, 0))
        cx, cy = rx + 1, ry + 1
        for i in range(steps):
            f = 1 - i / steps
            t = (1 - f) ** 1.6
            pygame.draw.ellipse(spr, tuple(int(v * t) for v in col),
                                (cx - rx * f, cy - ry * f, 2 * rx * f, 2 * ry * f))
        return spr

    # --------------------------------------------------------- static layer
    def _render_static(self):
        g = self.sim.grid
        rng = random.Random(5)
        W, H = self.size
        surf = pygame.Surface(self.size)
        for y in range(H):
            t = y / H
            pygame.draw.line(surf, tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT)),
                             (0, y), (W, y))
        # platform slab
        r, b, l = self.P(g.w, 0), self.P(g.w, g.h), self.P(0, g.h)
        s = self.slab
        pygame.draw.polygon(surf, SLAB_L, [l, b, (b[0], b[1] + s), (l[0], l[1] + s)])
        pygame.draw.polygon(surf, SLAB_R, [b, r, (r[0], r[1] + s), (b[0], b[1] + s)])
        pygame.draw.lines(surf, (58, 64, 84), False, [l, b, r], self.lw1)
        self._walls(surf)

        # polished concrete: per-tile variation, scuffs and fine speckle
        for x in range(g.w):
            for y in range(g.h):
                base = FLOOR_A if (x + y) % 2 == 0 else FLOOR_B
                col = shade(base, rng.uniform(0.94, 1.05))
                poly = self.tile(x, y)
                pygame.draw.polygon(surf, col, poly)
                pygame.draw.polygon(surf, GRID_LINE, poly, self.lw1)
                if (x, y) in g.blocked:
                    continue
                if rng.random() < 0.35:
                    px, py = self.P(x + rng.random(), y + rng.random())
                    dx, dy = rng.uniform(-5, 5) * self.k, rng.uniform(-2, 2) * self.k
                    pygame.draw.line(surf, shade(col, rng.choice((0.86, 1.12))),
                                     (px, py), (px + dx, py + dy), self.lw1)
                for _ in range(5):
                    px, py = self.P(x + rng.random(), y + rng.random())
                    surf.fill(shade(col, rng.choice((0.88, 1.1))), (px, py, self.lw1, self.lw1))
        # expansion joints every 4 tiles
        jc = shade(GRID_LINE, .62)
        for i in range(0, g.w + 1, 4):
            pygame.draw.line(surf, jc, self.P(i, 0), self.P(i, g.h), self._w(2))
        for j in range(0, g.h + 1, 4):
            pygame.draw.line(surf, jc, self.P(0, j), self.P(g.w, j), self._w(2))

        self._lighting(surf)
        self._shadows(surf)

        # yellow safety lanes along rack bases
        off = 0.1
        lw = self._w(2)
        for (x, y) in g.blocked:
            if (x, y + 1) not in g.blocked and g.walkable((x, y + 1)):
                pygame.draw.line(surf, LANE, self.P(x, y + 1 + off), self.P(x + 1, y + 1 + off), lw)
            if (x + 1, y) not in g.blocked and g.walkable((x + 1, y)):
                pygame.draw.line(surf, LANE, self.P(x + 1 + off, y), self.P(x + 1 + off, y + 1), lw)
            if (x - 1, y) not in g.blocked and g.walkable((x - 1, y)):
                pygame.draw.line(surf, LANE, self.P(x - off, y), self.P(x - off, y + 1), lw)
            if (x, y - 1) not in g.blocked and g.walkable((x, y - 1)):
                pygame.draw.line(surf, LANE, self.P(x, y - off), self.P(x + 1, y - off), lw)
        # drop-off stations
        for sx, sy in g.stations:
            pygame.draw.polygon(surf, STATION_BASE, self.tile(sx, sy, 0.04))
            pygame.draw.polygon(surf, STATION, self.tile(sx, sy, 0.04), self._w(3))
            pygame.draw.polygon(surf, STATION_IN, [self.P(sx + .3, sy + .3), self.P(sx + .7, sy + .3),
                                                   self.P(sx + .5, sy + .72)])
        return surf

    def _lighting(self, surf):
        """Ceiling light pools, window light shafts and station glow (additive, soft)."""
        g, q = self.sim.grid, 4
        W, H = self.size
        w, h = W // q + 1, H // q + 1
        add = pygame.BLEND_RGB_ADD
        lm = pygame.Surface((w, h), 0, 32)
        lm.fill((0, 0, 0))

        pool = self._radial(self.hw * 6 / q, self.hh * 6 / q, (36, 34, 26))
        for gx in range(3, g.w, 7):
            for gy in range(3, g.h, 7):
                cx, cy = self.P(gx + .5, gy + .5)
                lm.blit(pool, (cx / q - pool.get_width() / 2, cy / q - pool.get_height() / 2),
                        special_flags=add)
        if g.stations:
            glow = self._radial(self.hw * 2.4 / q, self.hh * 2.4 / q, (10, 46, 32))
            for sx, sy in g.stations:
                cx, cy = self.P(sx + .5, sy + .5)
                lm.blit(glow, (cx / q - glow.get_width() / 2, cy / q - glow.get_height() / 2),
                        special_flags=add)

        # sunlight falling through the high windows
        shafts = pygame.Surface((w, h), 0, 32)
        shafts.fill((0, 0, 0))

        def cl(a, m):
            return max(0.0, min(float(m), a))

        def quad(pts):
            sp = [self.P(cl(a, g.w), cl(b, g.h)) for a, b in pts]
            pygame.draw.polygon(shafts, (24, 26, 20), [(x / q, y / q) for x, y in sp])

        for i in range(2, g.w - 4, 7):
            quad([(i + .5, .5), (i + 4.5, .5), (i + 9, 9), (i + 5, 9)])
        for j in range(2, g.h - 4, 7):
            quad([(.5, j + .5), (.5, j + 4.5), (9, j + 9), (9, j + 5)])
        shafts = self._blur(shafts, 3)
        lm.blit(shafts, (0, 0), special_flags=add)

        mask = pygame.Surface((w, h), 0, 32)                 # keep light on the floor only
        mask.fill((0, 0, 0))
        pygame.draw.polygon(mask, (255, 255, 255),
                            [(x / q, y / q) for x, y in (self.P(0, 0), self.P(g.w, 0),
                                                        self.P(g.w, g.h), self.P(0, g.h))])
        lm.blit(mask, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        surf.blit(pygame.transform.smoothscale(lm, (w * q, h * q)), (0, 0), special_flags=add)

    def _shadows(self, surf):
        """Soft rack shadows (light from upper-left), wall-base occlusion, oil stains."""
        g, q = self.sim.grid, 4
        W, H = self.size
        w, h = W // q + 1, H // q + 1
        sh = pygame.Surface((w, h), pygame.SRCALPHA, 32)

        def poly(pts, a):
            pygame.draw.polygon(sh, (0, 0, 0, a), [(px / q, py / q) for px, py in
                                                   (self.P(min(x, g.w), min(y, g.h)) for x, y in pts)])

        for (x, y) in g.blocked:
            poly([(x, y), (x + 1, y), (x + 3, y + .3), (x + 3, y + 1.3), (x + 2, y + 1.3), (x, y + 1)], 78)
        poly([(0, 0), (g.w, 0), (g.w, .7), (0, .7)], 55)
        poly([(0, 0), (.7, 0), (.7, g.h), (0, g.h)], 55)
        rng = random.Random(11)
        for x in range(g.w):
            for y in range(g.h):
                if (x, y) not in g.blocked and rng.random() < 0.04:
                    cx, cy = self.P(x + rng.uniform(.25, .75), y + rng.uniform(.25, .75))
                    rx, ry = self.hw * rng.uniform(.3, .7) / q, self.hh * rng.uniform(.3, .7) / q
                    pygame.draw.ellipse(sh, (0, 0, 0, 40), (cx / q - rx, cy / q - ry, 2 * rx, 2 * ry))
        sh = self._blur(sh, 3)
        surf.blit(pygame.transform.smoothscale(sh, (w * q, h * q)), (0, 0))

    def _window(self, surf, along_x, u, f, wdt=4):
        g, P, Hw = self.sim.grid, self.P, self.wall_h
        pt = (lambda a, z: P(a, 0, z)) if along_x else (lambda a, z: P(0, a, z))
        z0, z1 = Hw * .55, Hw * .84
        n = 8
        for s in range(n):
            za = z0 + (z1 - z0) * s / n
            zb = z0 + (z1 - z0) * (s + 1) / n + 1
            t = s / (n - 1)
            c = tuple(int(a + (b - a) * t) for a, b in zip(SKY_LOW, SKY_HIGH))
            pygame.draw.polygon(surf, shade(c, f), [pt(u, za), pt(u + wdt, za), pt(u + wdt, zb), pt(u, zb)])
        frame = shade((150, 176, 210), f)
        pygame.draw.polygon(surf, frame, [pt(u, z0), pt(u + wdt, z0), pt(u + wdt, z1), pt(u, z1)], self._w(2))
        pygame.draw.line(surf, frame, pt(u + wdt / 2, z0), pt(u + wdt / 2, z1), self.lw1)
        pygame.draw.line(surf, frame, pt(u, (z0 + z1) / 2), pt(u + wdt, (z0 + z1) / 2), self.lw1)

    def _walls(self, surf):
        g, P, Hw = self.sim.grid, self.P, self.wall_h
        n = 18                                   # vertical gradient: dark at the floor, lighter up high
        for s in range(n):
            za, zb = Hw * s / n, Hw * (s + 1) / n + 1
            f = 0.64 + 0.42 * s / (n - 1)
            pygame.draw.polygon(surf, shade(WALL_A, f), [P(0, 0, za), P(g.w, 0, za), P(g.w, 0, zb), P(0, 0, zb)])
            pygame.draw.polygon(surf, shade(WALL_B, f), [P(0, 0, za), P(0, g.h, za), P(0, g.h, zb), P(0, 0, zb)])
        for i in range(0, g.w + 1, 4):                                   # ribs
            pygame.draw.line(surf, shade(WALL_A, 0.8), P(i, 0), P(i, 0, Hw), self.lw1)
        for j in range(0, g.h + 1, 4):
            pygame.draw.line(surf, shade(WALL_B, 0.8), P(0, j), P(0, j, Hw), self.lw1)
        for i in range(2, g.w - 4, 7):                                   # high windows
            self._window(surf, True, i, 1.0)
        for j in range(2, g.h - 4, 7):
            self._window(surf, False, j, .85)
        for pts, c in (([P(0, 0), P(g.w, 0), P(g.w, 0, Hw * .07), P(0, 0, Hw * .07)], LANE),
                       ([P(0, 0), P(0, g.h), P(0, g.h, Hw * .07), P(0, 0, Hw * .07)], shade(LANE, .8))):
            pygame.draw.polygon(surf, c, pts)                            # hazard base band
        pygame.draw.line(surf, (150, 160, 190), P(0, 0, Hw), P(g.w, 0, Hw), self._w(2))
        pygame.draw.line(surf, (120, 130, 160), P(0, 0, Hw), P(0, g.h, Hw), self._w(2))

    # ---------------------------------------------------------------- racks
    def _build_shelves(self):
        g, hw, hh = self.sim.grid, self.hw, self.hh
        H = self.shelf_h
        lw = self.lw1
        sw = int(2 * hw) + 4
        lox, loy = hw + 2, H + self.carton_h + 4
        sh = int(loy + 2 * hh) + 6

        def lp(gx, gy, z=0.0):
            return (lox + (gx - gy) * hw, loy + (gx + gy) * hh - z)

        def post(spr, x0, y0):
            box(spr, lp, x0, y0, x0 + .07, y0 + .07, 0, H, POST, lw)

        slots = ((.08, .08, .46, .46), (.54, .08, .92, .46),
                 (.08, .54, .46, .92), (.54, .54, .92, .92))
        items = []
        for (x, y) in sorted(g.blocked, key=lambda c: c[0] + c[1]):
            rng = random.Random(x * 977 + y * 131 + 7)
            spr = pygame.Surface((sw, sh), pygame.SRCALPHA)
            pygame.draw.polygon(spr, (20, 23, 34), [lp(0, 0, 0), lp(1, 0, 0), lp(1, 0, H), lp(0, 0, H)])
            pygame.draw.polygon(spr, (26, 30, 44), [lp(0, 0, 0), lp(0, 1, 0), lp(0, 1, H), lp(0, 0, H)])
            post(spr, 0, 0)
            pt = H * 0.05
            for zt in (H * .08, H * .38, H * .68):
                box(spr, lp, 0, 0, 1, 1, zt - pt, zt, PLANK, lw)
                for (a, b, c, d) in slots:
                    if rng.random() < 0.72:
                        ch = H * rng.uniform(0.14, 0.25)
                        carton(spr, lp, a, b, c, d, zt, zt + ch, rng.choice(CARTONS), lw)
                box(spr, lp, 0, .94, 1, 1, zt - pt, zt + pt * .7, BEAM, lw)
                box(spr, lp, .94, 0, 1, 1, zt - pt, zt + pt * .7, BEAM, lw)
            box(spr, lp, 0, 0, 1, 1, H - pt, H, PLANK, lw)
            for (a, b, c, d) in slots[::3]:
                if rng.random() < 0.5:
                    carton(spr, lp, a, b, c, d, H, H + self.carton_h * rng.uniform(.5, 1.0),
                           rng.choice(CARTONS), lw)
            box(spr, lp, 0, .94, 1, 1, H - pt, H + pt * .7, BEAM, lw)
            box(spr, lp, .94, 0, 1, 1, H - pt, H + pt * .7, BEAM, lw)
            post(spr, .93, 0)
            post(spr, 0, .93)
            post(spr, .93, .93)
            px, py = self.P(x, y)
            items.append((x + y + 1.0, 0, spr, px - lox, py - loy))
        return items

    def _make_vignette(self):
        sw, sh = 40, 26
        small = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for i in range(sw):
            for j in range(sh):
                dx, dy = (i + .5) / sw * 2 - 1, (j + .5) / sh * 2 - 1
                d = min(1.0, math.hypot(dx, dy) / 1.3)
                small.set_at((i, j), (0, 0, 0, int(max(0.0, d - 0.45) / 0.55 * 130)))
        return pygame.transform.smoothscale(small, (self.map_w, self.H))

    def _glow(self, col):
        spr = self._glows.get(col)
        if spr is None:
            rx, ry = self.hw * 1.5, self.hh * 1.5
            spr = pygame.Surface((int(rx * 2), int(ry * 2)), pygame.SRCALPHA)
            for k in range(7):
                f = 1 - k / 7
                pygame.draw.ellipse(spr, (*col, 10 + k * 9),
                                    (rx - rx * f, ry - ry * f, 2 * rx * f, 2 * ry * f))
            self._glows[col] = spr
        return spr

    def _robot_shadow(self):
        if self._rsh is None:
            rx, ry = self.hw * .78, self.hh * .78
            spr = pygame.Surface((int(rx * 2) + 4, int(ry * 2) + 4), pygame.SRCALPHA)
            for k in range(8):
                f = 1 - k / 8
                pygame.draw.ellipse(spr, (0, 0, 0, int(16 + k * 11)),
                                    (rx + 2 - rx * f, ry + 2 - ry * f, 2 * rx * f, 2 * ry * f))
            self._rsh = spr
        return self._rsh

    # ----------------------------------------------------------------- draw
    def draw(self, alpha, paused=False, step_ms=None):
        sim, hw, hh, k = self.sim, self.hw, self.hh, self.k
        self.screen.blit(self._static, (0, 0))
        ov = self.overlay
        ov.fill((0, 0, 0, 0))
        rsh = self._robot_shadow()

        robots = []
        for r in sim.robots:
            px = r.prev[0] + (r.pos[0] - r.prev[0]) * alpha
            py = r.prev[1] + (r.pos[1] - r.prev[1]) * alpha
            mv = (r.pos[0] - r.prev[0], r.pos[1] - r.prev[1])
            if mv != (0, 0):
                r.heading = mv
            robots.append((px, py, r))
            col = r.color
            cx, cy = self.P(px + .5, py + .5)
            g_ = self._glow(col)
            self.screen.blit(g_, (cx - g_.get_width() / 2, cy - g_.get_height() / 2))
            route = [(cx, cy)] + [self.P(p[0] + .5, p[1] + .5) for p in r.path[r.idx + 1:]]
            if len(route) > 1:
                pygame.draw.lines(ov, (*col, 90), False, route, self._w(2))
            tr = list(r.trail)
            for i in range(1, len(tr)):
                a = int(140 * i / len(tr))
                pygame.draw.line(ov, (*col, a), self.P(tr[i - 1][0] + .5, tr[i - 1][1] + .5),
                                 self.P(tr[i][0] + .5, tr[i][1] + .5), self._w(3))
            gx, gy = r.goal
            pygame.draw.polygon(ov, (*col, 235), self.tile(gx, gy, 0.14), self._w(2))
            pygame.draw.line(ov, (*col, 150), self.P(gx + .5, gy + .5),
                             self.P(gx + .5, gy + .5, hh * 3.5), self._w(2))
            ov.blit(rsh, (cx - rsh.get_width() / 2 + 3 * k, cy - rsh.get_height() / 2 + 2 * k))
        self.screen.blit(ov, (0, 0))

        order = list(self._shelves)
        order += [(px + py + 1.0, 1, r, px, py) for px, py, r in robots]
        order.sort(key=lambda it: (it[0], it[1]))
        for it in order:
            if it[1] == 0:
                self.screen.blit(it[2], (it[3], it[4]))
            else:
                self._draw_robot(it[2], it[3], it[4])

        self.screen.blit(self._vig, (0, 0))
        self._draw_hud(paused)

    def _draw_robot(self, r, px, py):
        """Drive unit: dark cylinder, glowing LED band, coloured lift plate, optional carton."""
        hw, hh, col, scr = self.hw, self.hh, r.color, self.screen
        lw = self.lw1
        cx, cy = self.P(px + .5, py + .5)
        rx, ry = 0.40 * hw * 1.414, 0.40 * hh * 1.414
        h = hh * 0.85
        pygame.draw.ellipse(scr, (28, 31, 42), (cx - rx, cy - ry, 2 * rx, 2 * ry))
        pygame.draw.rect(scr, (66, 72, 90), (cx - rx, cy - h, 2 * rx, h))
        pygame.draw.rect(scr, (92, 99, 120), (cx - rx, cy - h, rx * .3, h))          # rim light
        pygame.draw.rect(scr, (46, 51, 66), (cx + rx * .35, cy - h, rx * .65, h))    # shaded side
        pygame.draw.rect(scr, (24, 27, 36), (cx - rx, cy - h * .14, 2 * rx, h * .14))  # bumper
        pygame.draw.rect(scr, col, (cx - rx, cy - h * .62, 2 * rx, max(2, h * .2)))
        pygame.draw.ellipse(scr, shade(col, .72), (cx - rx, cy - h - ry, 2 * rx, 2 * ry))
        lr, lry = rx * .78, ry * .78
        lid_h = hh * 0.22
        pygame.draw.ellipse(scr, shade(col, .55), (cx - lr, cy - h - lid_h - lry, 2 * lr, 2 * lry))
        pygame.draw.rect(scr, shade(col, .55), (cx - lr, cy - h - lid_h, 2 * lr, lid_h))
        top = tuple(min(255, int(v * 1.1 + 22)) for v in col)
        pygame.draw.ellipse(scr, top, (cx - lr, cy - h - lid_h - lry, 2 * lr, 2 * lry))
        pygame.draw.ellipse(scr, shade(top, 1.15), (cx - lr, cy - h - lid_h - lry, 2 * lr, 2 * lry), lw)
        hx, hy = getattr(r, "heading", (0, 1))
        sx, sy = (hx - hy), (hx + hy) * 0.5
        pygame.draw.circle(scr, (255, 255, 255),
                           (cx + sx * rx * .55, cy - h - lid_h + sy * ry * .55), max(2, self._w(2)))
        z = h + lid_h
        if r.carrying:
            ph = hh * 1.0
            carton(scr, self.P, px + .3, py + .3, px + .7, py + .7, z, z + ph, CARTONS[0], lw)
            z += ph
        label = self.lfont.render(str(r.id), True, (14, 14, 22))
        lx, ly = self.P(px + .5, py + .5, z)
        scr.blit(label, label.get_rect(center=(lx, ly)))

    # ------------------------------------------------------------------ HUD
    def _draw_hud(self, paused):
        sim, ui = self.sim, self.ui
        x0 = self.map_w + int(18 * ui)
        fh = self.font.get_height()
        pygame.draw.rect(self.screen, HUD_BG, pygame.Rect(self.map_w, 0, self.hud_w, self.H))
        pygame.draw.line(self.screen, (44, 50, 70), (self.map_w, 0), (self.map_w, self.H), max(1, int(2 * ui)))
        y = int(14 * ui)
        self.screen.blit(self.big.render("FLEET SIM", True, TEXT), (x0, y))
        y += int(34 * ui)
        pygame.draw.line(self.screen, STATION, (x0, y - int(6 * ui)), (x0 + int(64 * ui), y - int(6 * ui)),
                         max(2, int(3 * ui)))
        y += int(6 * ui)
        rows = [("Robots", str(len(sim.robots))), ("Step", str(sim.t)),
                ("Delivered", str(sim.delivered)),
                ("Throughput", f"{sim.throughput:.1f}/100"),
                ("Collisions", str(sim.collisions)), ("Planner", sim.method),
                ("CBS nodes", str(sim.cbs_nodes)),
                ("Replan", f"{sim.replan_ms:.1f} ms"),
                ("Avg replan", f"{sim.avg_replan_ms:.1f} ms")]
        for kk, v in rows:
            col = (255, 120, 120) if (kk == "Collisions" and sim.collisions) else TEXT
            self.screen.blit(self.font.render(kk, True, DIM), (x0, y))
            self.screen.blit(self.font.render(v, True, col), (x0 + int(112 * ui), y))
            y += fh + int(6 * ui)
        y += int(8 * ui)
        pygame.draw.line(self.screen, (44, 50, 70), (x0, y), (self.map_w + self.hud_w - int(18 * ui), y),
                         max(1, int(ui)))
        y += int(10 * ui)
        rad = int(7 * ui)
        for r in sim.robots[:10]:
            pygame.draw.circle(self.screen, r.color, (x0 + rad, y + fh // 2), rad)
            self.screen.blit(self.font.render(f"R{r.id}  {r.delivered:>2} done", True, TEXT),
                             (x0 + int(24 * ui), y))
            y += fh + int(3 * ui)
        hints = ["SPACE  pause", "+ / -  speed", "R      reset"]
        yy = self.H - int(12 * ui) - len(hints) * (fh + int(2 * ui))
        if paused:
            self.screen.blit(self.font.render("PAUSED", True, (255, 200, 90)), (x0, yy - fh - int(6 * ui)))
        for t in hints:
            self.screen.blit(self.font.render(t, True, DIM), (x0, yy))
            yy += fh + int(2 * ui)