"""Top-down 'drone camera' renderer with a labelled grid, zones, rack IDs and legend.

Same interface as the isometric Renderer: draw(alpha, paused, step_ms), size, to_bytes().
resolution=(3840, 2160) fits the grid to a 1080p canvas; resolution=None sizes the window
to the content and uses `cell` pixels per grid cell.
"""
import math
import random

import pygame

UHD = (3840, 2160)
BG, PANEL = (11, 13, 20), (16, 19, 29)
FLOOR_A, FLOOR_B = (58, 62, 74), (62, 66, 79)
GRID_MINOR, GRID_MAJOR = (46, 50, 62), (92, 100, 126)
AXIS = (160, 170, 196)
STATION, STATION_IN, STATION_BASE = (34, 170, 118), (140, 244, 196), (22, 62, 52)
LANE, PICK = (206, 176, 52), (128, 110, 44)
ROOF, ROOF_DK, BEAM = (84, 97, 126), (42, 50, 72), (246, 158, 56)
CARTONS = [(224, 180, 120), (208, 163, 106), (236, 236, 240), (122, 170, 216)]
TAPE = (236, 226, 190)
TEXT, DIM = (225, 230, 240), (130, 138, 156)
HUD_BG, HUD_W = (20, 23, 33), 300
SAMPLE = (110, 200, 255)


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def colname(i):
    s, i = "", i + 1
    while i > 0:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s


def cellname(p):
    return f"{colname(p[0])}{p[1] + 1}"


def put_text(surf, font, txt, color, center, alpha=255):
    s = font.render(txt, True, color)
    if alpha < 255:
        s.set_alpha(alpha)
    surf.blit(s, s.get_rect(center=(int(center[0]), int(center[1]))))
    return s


def carton_top(surf, rect, col, lw):
    pygame.draw.rect(surf, col, rect)
    pygame.draw.line(surf, shade(col, 1.2), rect.topleft, rect.topright, lw)
    pygame.draw.line(surf, shade(col, 1.2), rect.topleft, rect.bottomleft, lw)
    pygame.draw.line(surf, shade(col, .72), rect.bottomleft, rect.bottomright, lw)
    pygame.draw.line(surf, shade(col, .72), rect.topright, rect.bottomright, lw)
    pygame.draw.line(surf, TAPE, (rect.x, rect.centery), (rect.right, rect.centery), lw)


class DroneRenderer:
    def __init__(self, sim, cell=26, show_window=True, resolution=UHD):
        pygame.init()
        pygame.font.init()
        self.sim = sim
        g = sim.grid
        self.ui = (resolution[1] / 1080.0) if resolution else 1.0
        ui = self.ui
        self.hud_w = int(HUD_W * ui)
        self.mx, self.top_m, self.bot_m = int(46 * ui), int(64 * ui), int(40 * ui)
        if resolution:
            self.map_w = resolution[0] - self.hud_w
            cell = min((self.map_w - 2 * self.mx) / g.w,
                       (resolution[1] - self.top_m - self.bot_m) / g.h)
        self.cell = cell = max(8, int(cell))
        self.k = max(1.0, cell / 26.0)
        self.lw = max(1, int(self.k))

        mono = "consolas,menlo,dejavusansmono"
        sf = pygame.font.SysFont
        self.font, self.big = sf(mono, int(13 * ui)), sf(mono, int(20 * ui), bold=True)
        self.cam = sf(mono, int(12 * ui))
        self.small = sf(mono, max(9, int(cell * .26)))
        self.tag = sf(mono, max(9, int(cell * .30)), bold=True)
        self.axis = sf(mono, max(9, int(cell * .27)), bold=True)
        fh = self.font.get_height()
        hud_h = int(60 * ui + 9 * (fh + 6 * ui) + 20 * ui + 10 * (fh + 3 * ui)
                    + 30 * ui + 10 * (fh + 5 * ui) + 90 * ui)

        gw_px, gh_px = g.w * cell, g.h * cell
        if resolution:
            self.H = resolution[1]
        else:
            self.map_w = gw_px + 2 * self.mx
            self.H = max(gh_px + self.top_m + self.bot_m, hud_h)
        self.gw_px, self.gh_px = gw_px, gh_px
        self.gx0 = (self.map_w - gw_px) // 2
        self.gy0 = self.top_m + (self.H - self.top_m - self.bot_m - gh_px) // 2
        self.size = (self.map_w + self.hud_w, self.H)

        if show_window:
            try:
                flags = (pygame.SCALED | pygame.RESIZABLE) if resolution else 0
                self.screen = pygame.display.set_mode(self.size, flags)
            except pygame.error:
                self.screen = pygame.display.set_mode(self.size)
            pygame.display.set_caption("Warehouse Fleet Sim - drone view")
        else:
            self.screen = pygame.Surface(self.size)
        self.overlay = pygame.Surface((self.map_w, self.H), pygame.SRCALPHA)
        self._sidx = {c: i + 1 for i, c in enumerate(g.stations)}
        self._blocks = self._find_blocks()
        self._static = self._render_static()
        self._vig = self._make_vignette()
        self._rsh = self._shadow_sprite()

    def to_bytes(self):
        return pygame.image.tostring(self.screen, "RGB")

    def save_png(self, path):
        pygame.image.save(self.screen, path)

    # ------------------------------------------------------------- helpers
    def X(self, gx):
        return self.gx0 + gx * self.cell

    def Y(self, gy):
        return self.gy0 + gy * self.cell

    def gname(self, p):
        return f"S{self._sidx[p]}" if p in self._sidx else cellname(p)

    def _find_blocks(self):
        g, seen, out = self.sim.grid, set(), []
        for c in sorted(g.blocked, key=lambda c: (c[1], c[0])):
            if c in seen:
                continue
            stack, cells = [c], []
            seen.add(c)
            while stack:
                cur = stack.pop()
                cells.append(cur)
                for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    n = (cur[0] + d[0], cur[1] + d[1])
                    if n in g.blocked and n not in seen:
                        seen.add(n)
                        stack.append(n)
            xs, ys = [a for a, _ in cells], [b for _, b in cells]
            out.append((min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1))
        return sorted(out, key=lambda b: (b[1], b[0]))

    @staticmethod
    def _runs(n, occupied):
        out, start = [], None
        for i in range(n + 1):
            free = i < n and i not in occupied
            if free and start is None:
                start = i
            if not free and start is not None:
                out.append((start, i - 1))
                start = None
        return out

    @staticmethod
    def _blur(surf, f=3):
        w, h = surf.get_size()
        small = pygame.transform.smoothscale(surf, (max(1, w // f), max(1, h // f)))
        return pygame.transform.smoothscale(small, (w, h))

    # --------------------------------------------------------- static layer
    def _render_static(self):
        g, c, lw, ui = self.sim.grid, self.cell, self.lw, self.ui
        rng = random.Random(5)
        surf = pygame.Surface(self.size)
        surf.fill(BG)
        pygame.draw.rect(surf, PANEL, (0, 0, self.map_w, self.H))

        for x in range(g.w):                                   # concrete floor
            for y in range(g.h):
                col = shade(FLOOR_A if (x + y) % 2 == 0 else FLOOR_B, rng.uniform(.95, 1.05))
                ox, oy = self.X(x), self.Y(y)
                surf.fill(col, (ox, oy, c, c))
                if (x, y) in g.blocked:
                    continue
                for _ in range(6):
                    surf.fill(shade(col, rng.choice((.88, 1.1))),
                              (int(ox + rng.random() * c), int(oy + rng.random() * c), lw, lw))
                if rng.random() < .3:
                    px, py = ox + rng.random() * c, oy + rng.random() * c
                    pygame.draw.line(surf, shade(col, rng.choice((.86, 1.12))), (px, py),
                                     (px + rng.uniform(-.15, .15) * c, py + rng.uniform(-.1, .1) * c), lw)
        tint = pygame.Surface((self.gw_px, 3 * c), pygame.SRCALPHA)   # drop-off zone tint
        tint.fill((*STATION, 30))
        surf.blit(tint, (self.gx0, self.Y(g.h - 3)))

        for x in range(g.w + 1):                               # labelled grid lines
            major = x % 5 == 0 or x == g.w
            pygame.draw.line(surf, GRID_MAJOR if major else GRID_MINOR, (self.X(x), self.gy0),
                             (self.X(x), self.gy0 + self.gh_px), lw * 2 if major else lw)
        for y in range(g.h + 1):
            major = y % 5 == 0 or y == g.h
            pygame.draw.line(surf, GRID_MAJOR if major else GRID_MINOR, (self.gx0, self.Y(y)),
                             (self.gx0 + self.gw_px, self.Y(y)), lw * 2 if major else lw)

        # zone / aisle names painted on the floor
        vr = self._runs(g.w, {x for x, _ in g.blocked})
        hr = self._runs(g.h, {y for _, y in g.blocked})
        for i, (a, b) in enumerate(vr):
            name = "WEST LANE" if i == 0 else "EAST LANE" if i == len(vr) - 1 else f"AISLE {i}"
            put_text(surf, self.small, name, AXIS, (self.X((a + b + 1) / 2), self.Y(.5)), 170)
        west = (self.X((vr[0][1] + 1) / 2), 0)
        for i, (a, b) in enumerate(hr[1:-1], 1):
            put_text(surf, self.small, f"CROSS-AISLE {i}", AXIS, (west[0], self.Y((a + b + 1) / 2)), 170)
        put_text(surf, self.tag, "DROP-OFF / PACKING ZONE", STATION_IN,
                 (self.X(g.w / 2), self.Y(g.h - 1.5)), 110)

        for p in g.pickups:                                    # pick cells (next to racks)
            pygame.draw.circle(surf, PICK, (self.X(p[0] + .5), self.Y(p[1] + .5)), max(2, int(c * .05)))

        off = int(c * .1)                                      # yellow safety lanes
        for (bx, by, bw, bh) in self._blocks:
            r = pygame.Rect(self.X(bx), self.Y(by), bw * c, bh * c).inflate(2 * off, 2 * off)
            pygame.draw.rect(surf, LANE, r, max(2, int(c * .05)))

        q = 4                                                  # soft rack shadows
        sh = pygame.Surface((self.map_w // q + 2, self.H // q + 2), pygame.SRCALPHA)
        for (bx, by, bw, bh) in self._blocks:
            s = c * .3
            pygame.draw.rect(sh, (0, 0, 0, 120),
                             ((self.X(bx) + s) / q, (self.Y(by) + s) / q, bw * c / q, bh * c / q))
        sh = self._blur(sh, 3)
        surf.blit(pygame.transform.smoothscale(sh, (sh.get_width() * q, sh.get_height() * q)), (0, 0))

        for (sx, sy), i in self._sidx.items():                 # drop-off stations
            r = pygame.Rect(self.X(sx), self.Y(sy), c, c).inflate(-int(c * .08), -int(c * .08))
            pygame.draw.rect(surf, STATION_BASE, r)
            pygame.draw.rect(surf, STATION, r, max(2, int(c * .06)))
            cx, cy = r.centerx, r.centery
            pygame.draw.polygon(surf, STATION_IN, [(cx - c * .17, cy + c * .02),
                                                   (cx + c * .17, cy + c * .02), (cx, cy + c * .26)])
            put_text(surf, self.small, f"S{i}", STATION_IN, (cx, cy - c * .2))

        slots = ((.08, .08, .46, .46), (.54, .08, .92, .46), (.08, .54, .46, .92), (.54, .54, .92, .92))
        for idx, (bx, by, bw, bh) in enumerate(self._blocks):  # rack roofs with cartons
            rect = pygame.Rect(self.X(bx), self.Y(by), bw * c, bh * c)
            pygame.draw.rect(surf, ROOF_DK, rect)
            r2 = random.Random(idx * 31 + 3)
            for cx_ in range(bx, bx + bw):
                for cy_ in range(by, by + bh):
                    cr = pygame.Rect(self.X(cx_), self.Y(cy_), c, c)
                    pygame.draw.rect(surf, ROOF, cr.inflate(-2 * lw, -2 * lw))
                    for (a, b, c2, d) in slots:
                        if r2.random() < .8:
                            carton_top(surf, pygame.Rect(int(cr.x + a * c), int(cr.y + b * c),
                                                         max(3, int((c2 - a) * c)), max(3, int((d - b) * c))),
                                       r2.choice(CARTONS), lw)
            pygame.draw.rect(surf, BEAM, rect, max(2, int(c * .07)))
            pygame.draw.line(surf, shade(BEAM, 1.2), rect.topleft, rect.topright, max(2, int(c * .07)))
            lbl = self.tag.render(f"R{idx + 1:02d}", True, TEXT)
            plate = lbl.get_rect(center=rect.center).inflate(int(c * .3), int(c * .16))
            pygame.draw.rect(surf, (12, 14, 22), plate)
            pygame.draw.rect(surf, BEAM, plate, lw)
            surf.blit(lbl, lbl.get_rect(center=rect.center))

        for x in range(g.w):                                   # coordinate axes, all four sides
            for yy in (self.gy0 - int(20 * ui), self.gy0 + self.gh_px + int(20 * ui)):
                put_text(surf, self.axis, colname(x), AXIS, (self.X(x + .5), yy))
        for y in range(g.h):
            for xx in (self.gx0 - int(24 * ui), self.gx0 + self.gw_px + int(24 * ui)):
                put_text(surf, self.axis, str(y + 1), AXIS, (xx, self.Y(y + .5)))

        bl, o, w = int(c * .9), int(6 * ui), max(2, int(2 * ui))   # camera frame brackets
        x0, y0, x1, y1 = self.gx0 - o, self.gy0 - o, self.gx0 + self.gw_px + o, self.gy0 + self.gh_px + o
        for (x, y, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            pygame.draw.line(surf, (235, 235, 245), (x, y), (x + sx * bl, y), w)
            pygame.draw.line(surf, (235, 235, 245), (x, y), (x, y + sy * bl), w)
        return surf

    def _make_vignette(self):
        sw, sh = 40, 26
        small = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for i in range(sw):
            for j in range(sh):
                dx, dy = (i + .5) / sw * 2 - 1, (j + .5) / sh * 2 - 1
                d = min(1.0, math.hypot(dx, dy) / 1.3)
                small.set_at((i, j), (0, 0, 0, int(max(0.0, d - .5) / .5 * 90)))
        return pygame.transform.smoothscale(small, (self.map_w, self.H))

    def _shadow_sprite(self):
        R = self.cell * .36
        size = int(R * 2.8)
        spr = pygame.Surface((size, size), pygame.SRCALPHA)
        for i in range(8):
            f = 1 - i / 8
            pygame.draw.circle(spr, (0, 0, 0, int(14 + i * 10)), (size // 2, size // 2), int(R * 1.25 * f) + 1)
        return spr

    # ----------------------------------------------------------------- draw
    def draw(self, alpha, paused=False, step_ms=None):
        sim, c, g = self.sim, self.cell, self.sim.grid
        scr, ov, ui = self.screen, self.overlay, self.ui
        scr.blit(self._static, (0, 0))
        ov.fill((0, 0, 0, 0))
        wl = max(2, int(c * .05))

        robots = []
        for r in sim.robots:
            px = r.prev[0] + (r.pos[0] - r.prev[0]) * alpha
            py = r.prev[1] + (r.pos[1] - r.prev[1]) * alpha
            mv = (r.pos[0] - r.prev[0], r.pos[1] - r.prev[1])
            if mv != (0, 0):
                r.heading = mv
            robots.append((px, py, r))
            col = r.color
            cx, cy = self.X(px + .5), self.Y(py + .5)
            ov.blit(self._rsh, (cx - self._rsh.get_width() / 2 + .07 * c,
                                cy - self._rsh.get_height() / 2 + .1 * c))
            route = [(cx, cy)] + [(self.X(p[0] + .5), self.Y(p[1] + .5)) for p in r.path[r.idx + 1:]]
            if len(route) > 1:
                pygame.draw.lines(ov, (*col, 110), False, route, wl)
            tr = list(r.trail)
            for i in range(1, len(tr)):
                a = int(130 * i / len(tr))
                pygame.draw.line(ov, (*col, a), (self.X(tr[i - 1][0] + .5), self.Y(tr[i - 1][1] + .5)),
                                 (self.X(tr[i][0] + .5), self.Y(tr[i][1] + .5)), max(3, int(c * .09)))
            gr = pygame.Rect(self.X(r.goal[0]), self.Y(r.goal[1]), c, c).inflate(-int(c * .2), -int(c * .2))
            pygame.draw.rect(ov, (*col, 45), gr)
            pygame.draw.rect(ov, (*col, 240), gr, wl)
        scr.blit(ov, (0, 0))

        for px, py, r in robots:                               # goal name tags
            gx, gy = r.goal
            lbl = self.small.render(self.gname(r.goal), True, r.color)
            tag = lbl.get_rect(center=(int(self.X(gx + .5)), int(self.Y(gy) - c * .16))).inflate(int(c * .2), int(c * .08))
            pygame.draw.rect(scr, (12, 14, 22), tag)
            pygame.draw.rect(scr, r.color, tag, self.lw)
            scr.blit(lbl, lbl.get_rect(center=tag.center))

        for px, py, r in robots:
            self._draw_robot(r, px, py)

        scr.blit(self._vig, (0, 0))
        info = (f"DRONE CAM-01   ALT 42 m   GRID {g.w}x{g.h}   1 CELL = 1 m   "
                f"T+{sim.t // 60:02d}:{sim.t % 60:02d}")
        scr.blit(self.cam.render(info, True, DIM), (self.gx0, int(14 * ui)))
        if sim.t % 2 == 0:
            pygame.draw.circle(scr, (235, 64, 64), (self.gx0 + self.gw_px - int(48 * ui), int(22 * ui)), int(6 * ui))
        scr.blit(self.cam.render("REC", True, (235, 64, 64)), (self.gx0 + self.gw_px - int(36 * ui), int(14 * ui)))
        self._draw_hud(paused)

    def _draw_robot(self, r, px, py):
        c, col, scr = self.cell, r.color, self.screen
        cx, cy = self.X(px + .5), self.Y(py + .5)
        R = c * .36
        rim = max(2, int(c * .05))
        pygame.draw.circle(scr, (26, 29, 40), (cx, cy), R)
        pygame.draw.circle(scr, (74, 81, 100), (cx, cy), R, rim)
        pygame.draw.circle(scr, col, (cx, cy), R * .86, max(2, int(c * .07)))
        pygame.draw.circle(scr, shade(col, .8), (cx, cy), R * .7)
        top = tuple(min(255, int(v * 1.1 + 22)) for v in col)
        pygame.draw.circle(scr, top, (cx - R * .06, cy - R * .06), R * .58)
        hx, hy = getattr(r, "heading", (0, 1))
        bx, by = cx + hx * R * .55, cy + hy * R * .55
        pygame.draw.polygon(scr, (255, 255, 255),
                            [(cx + hx * R * 1.05, cy + hy * R * 1.05),
                             (bx - hy * R * .22, by + hx * R * .22), (bx + hy * R * .22, by - hx * R * .22)])
        if r.carrying:
            s = int(c * .46)
            carton_top(scr, pygame.Rect(int(cx - s / 2), int(cy - s / 2), s, s), CARTONS[0], self.lw)
            pygame.draw.line(scr, TAPE, (cx, cy - s / 2), (cx, cy + s / 2), self.lw)
        put_text(scr, self.tag, str(r.id), (14, 14, 22), (cx, cy))

    # ------------------------------------------------------------------ HUD
    def _draw_hud(self, paused):
        sim, ui, scr = self.sim, self.ui, self.screen
        x0 = self.map_w + int(18 * ui)
        fh = self.font.get_height()
        pygame.draw.rect(scr, HUD_BG, pygame.Rect(self.map_w, 0, self.hud_w, self.H))
        pygame.draw.line(scr, (44, 50, 70), (self.map_w, 0), (self.map_w, self.H), max(1, int(2 * ui)))
        y = int(14 * ui)
        scr.blit(self.big.render("FLEET SIM", True, TEXT), (x0, y))
        y += int(34 * ui)
        pygame.draw.line(scr, STATION, (x0, y - int(6 * ui)), (x0 + int(64 * ui), y - int(6 * ui)), max(2, int(3 * ui)))
        y += int(6 * ui)
        rows = [("Robots", str(len(sim.robots))), ("Step", str(sim.t)), ("Delivered", str(sim.delivered)),
                ("Throughput", f"{sim.throughput:.1f}/100"), ("Collisions", str(sim.collisions)),
                ("Planner", sim.method), ("CBS nodes", str(sim.cbs_nodes)),
                ("Replan", f"{sim.replan_ms:.1f} ms"), ("Avg replan", f"{sim.avg_replan_ms:.1f} ms")]
        for kk, v in rows:
            col = (255, 120, 120) if (kk == "Collisions" and sim.collisions) else TEXT
            scr.blit(self.font.render(kk, True, DIM), (x0, y))
            scr.blit(self.font.render(v, True, col), (x0 + int(130 * ui), y))
            y += fh + int(6 * ui)
        y += int(8 * ui)
        line = (x0, y), (self.map_w + self.hud_w - int(18 * ui), y)
        pygame.draw.line(scr, (44, 50, 70), *line, max(1, int(ui)))
        y += int(10 * ui)
        scr.blit(self.font.render("ROBOT   TASK  TARGET  DONE", True, DIM), (x0, y))
        y += fh + int(4 * ui)
        rad = int(6 * ui)
        for r in sim.robots[:10]:
            pygame.draw.circle(scr, r.color, (x0 + rad, y + fh // 2), rad)
            task = "DROP" if r.carrying else "PICK"
            scr.blit(self.font.render(f"R{r.id:<3}", True, TEXT), (x0 + int(18 * ui), y))
            scr.blit(self.font.render(task, True, STATION_IN if r.carrying else TEXT), (x0 + int(76 * ui), y))
            scr.blit(self.font.render(self.gname(r.goal), True, r.color), (x0 + int(134 * ui), y))
            scr.blit(self.font.render(f"{r.delivered:>3}", True, TEXT), (x0 + int(214 * ui), y))
            y += fh + int(3 * ui)
        y += int(10 * ui)
        scr.blit(self.font.render("LEGEND", True, DIM), (x0, y))
        y += fh + int(6 * ui)
        s = int(16 * ui)
        items = [("rack", "Rack (R01...)"), ("pick", "Pick cell"), ("lane", "Safety lane"),
                 ("station", "Drop-off station"), ("robot", "Robot, empty"), ("pkg", "Robot + package"),
                 ("route", "Planned route"), ("trail", "Trail"), ("goal", "Goal + target tag")]
        for kind, text in items:
            ix, iy = x0, y
            if kind == "rack":
                pygame.draw.rect(scr, ROOF_DK, (ix, iy, s, s))
                pygame.draw.rect(scr, BEAM, (ix, iy, s, s), max(1, int(2 * ui)))
            elif kind == "pick":
                pygame.draw.circle(scr, PICK, (ix + s // 2, iy + s // 2), max(2, int(3 * ui)))
            elif kind == "lane":
                pygame.draw.line(scr, LANE, (ix, iy + s // 2), (ix + s, iy + s // 2), max(2, int(3 * ui)))
            elif kind == "station":
                pygame.draw.rect(scr, STATION_BASE, (ix, iy, s, s))
                pygame.draw.rect(scr, STATION, (ix, iy, s, s), max(1, int(2 * ui)))
            elif kind in ("robot", "pkg"):
                pygame.draw.circle(scr, (26, 29, 40), (ix + s // 2, iy + s // 2), s // 2)
                pygame.draw.circle(scr, SAMPLE, (ix + s // 2, iy + s // 2), s // 2, max(1, int(2 * ui)))
                if kind == "pkg":
                    h = s // 2
                    pygame.draw.rect(scr, CARTONS[0], (ix + s // 2 - h // 2, iy + s // 2 - h // 2, h, h))
            elif kind == "route":
                pygame.draw.line(scr, shade(SAMPLE, .7), (ix, iy + s // 2), (ix + s, iy + s // 2), max(1, int(2 * ui)))
            elif kind == "trail":
                pygame.draw.line(scr, shade(SAMPLE, .45), (ix, iy + s // 2), (ix + s, iy + s // 2), max(2, int(4 * ui)))
            elif kind == "goal":
                pygame.draw.rect(scr, SAMPLE, (ix, iy, s, s), max(1, int(2 * ui)))
            scr.blit(self.font.render(text, True, TEXT), (x0 + s + int(10 * ui), y))
            y += fh + int(5 * ui)

        hints = ["SPACE  pause", "+ / -  speed", "R      reset"]
        yy = self.H - int(12 * ui) - len(hints) * (fh + int(2 * ui))
        if paused:
            scr.blit(self.font.render("PAUSED", True, (255, 200, 90)), (x0, yy - fh - int(6 * ui)))
        for t in hints:
            scr.blit(self.font.render(t, True, DIM), (x0, yy))
            yy += fh + int(2 * ui)