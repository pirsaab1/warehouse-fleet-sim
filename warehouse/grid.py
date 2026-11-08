"""Warehouse map: shelves, aisles, drop-off stations, BFS distance maps."""
from collections import deque


class Grid:
    def __init__(self, width=33, height=21):
        self.w, self.h = width, height
        self.blocked = set()          # shelf cells
        self.stations = []            # drop-off cells (bottom row)
        self.pickups = []             # free cells next to a shelf
        self._dist_cache = {}
        self._build()

    # ------------------------------------------------------------------ map
    def _build(self):
        # shelf blocks: 2 wide x 4 tall, separated by 2-cell aisles
        for bx in range(3, self.w - 4, 4):
            for by in (2, 8, 14):
                for dx in range(2):
                    for dy in range(4):
                        self.blocked.add((bx + dx, by + dy))
        self.stations = [(x, self.h - 1) for x in range(2, self.w - 2, 2)]
        for x in range(self.w):
            for y in range(self.h - 3):          # keep bottom zone for stations
                if (x, y) in self.blocked:
                    continue
                if any((x + dx, y + dy) in self.blocked
                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    self.pickups.append((x, y))

    def walkable(self, p):
        x, y = p
        return 0 <= x < self.w and 0 <= y < self.h and p not in self.blocked

    def neighbors(self, p):
        x, y = p
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (x + dx, y + dy)
            if self.walkable(q):
                yield q

    def free_cells(self):
        return [(x, y) for x in range(self.w) for y in range(self.h)
                if (x, y) not in self.blocked]

    # ------------------------------------------------------- distance maps
    def dist_map(self, goal):
        """True shortest-path distance from every cell to `goal` (cached)."""
        d = self._dist_cache.get(goal)
        if d is not None:
            return d
        d = {goal: 0}
        q = deque([goal])
        while q:
            cur = q.popleft()
            for nb in self.neighbors(cur):
                if nb not in d:
                    d[nb] = d[cur] + 1
                    q.append(nb)
        self._dist_cache[goal] = d
        return d
