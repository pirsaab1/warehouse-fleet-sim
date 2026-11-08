"""Lifelong warehouse simulation: robots endlessly fetch items to stations."""
import colorsys
import random
import time
from collections import deque

from .grid import Grid
from .planner import plan_all


class Robot:
    def __init__(self, rid, pos, color):
        self.id, self.pos, self.prev = rid, pos, pos
        self.color = color
        self.goal = pos
        self.carrying = False
        self.path, self.idx = [pos], 0
        self.trail = deque([pos], maxlen=30)
        self.delivered = 0


class Simulation:
    def __init__(self, num_robots=8, width=33, height=21, seed=0,
                 node_limit=400, time_limit=0.25):
        self.rng = random.Random(seed)
        self.grid = Grid(width, height)
        if num_robots > len(self.grid.stations):
            raise ValueError(f"max {len(self.grid.stations)} robots on this map")
        self.node_limit, self.time_limit = node_limit, time_limit
        self.t = 0
        self.delivered = 0
        self.collisions = 0
        self.need_replan = False
        self.method, self.cbs_nodes = "-", 0
        self.replan_ms, self.replan_total, self.replans = 0.0, 0.0, 0
        self.method_counts = {"CBS": 0, "PRIORITIZED": 0, "WAIT": 0}

        zone = [c for c in self.grid.free_cells() if c[1] >= self.grid.h - 3
                and c not in self.grid.stations]
        starts = self.rng.sample(zone, num_robots)
        self.robots = []
        for i, s in enumerate(starts):
            hue = i / max(num_robots, 1)
            rgb = tuple(int(255 * v) for v in colorsys.hsv_to_rgb(hue, 0.65, 1.0))
            self.robots.append(Robot(i, s, rgb))
        for r in self.robots:
            r.goal = self._pick_goal(r)
        self._replan()

    # ------------------------------------------------------------- goals
    def _pick_goal(self, robot):
        taken = {r.goal for r in self.robots if r is not robot}
        taken |= {r.pos for r in self.robots}
        pool = self.grid.stations if robot.carrying else self.grid.pickups
        options = [c for c in pool if c not in taken]
        return self.rng.choice(options)

    # ------------------------------------------------------------ replan
    def _replan(self):
        t0 = time.perf_counter()
        starts = [r.pos for r in self.robots]
        goals = [r.goal for r in self.robots]
        paths, method, nodes = plan_all(self.grid, starts, goals,
                                        self.node_limit, self.time_limit, self.rng)
        for r, p in zip(self.robots, paths):
            r.path, r.idx = p, 0
        self.method, self.cbs_nodes = method, nodes
        self.method_counts[method] += 1
        self.replan_ms = (time.perf_counter() - t0) * 1000
        self.replan_total += self.replan_ms
        self.replans += 1
        self.need_replan = method == "WAIT"        # retry next step if stuck

    # -------------------------------------------------------------- step
    def step(self):
        self.t += 1
        for r in self.robots:
            r.prev = r.pos
            if r.idx < len(r.path) - 1:
                r.idx += 1
                r.pos = r.path[r.idx]
                r.trail.append(r.pos)
        self._check_collisions()

        replan = self.need_replan
        for r in self.robots:
            if r.pos == r.goal:
                if r.carrying:
                    r.delivered += 1
                    self.delivered += 1
                r.carrying = not r.carrying
                r.goal = self._pick_goal(r)
                replan = True
        if replan:
            self._replan()

    def _check_collisions(self):
        cells = [r.pos for r in self.robots]
        self.collisions += len(cells) - len(set(cells))
        for i, a in enumerate(self.robots):
            for b in self.robots[i + 1:]:
                if a.pos == b.prev and b.pos == a.prev and a.pos != a.prev:
                    self.collisions += 1

    # ----------------------------------------------------------- metrics
    @property
    def throughput(self):
        return 100.0 * self.delivered / self.t if self.t else 0.0

    @property
    def avg_replan_ms(self):
        return self.replan_total / self.replans if self.replans else 0.0
