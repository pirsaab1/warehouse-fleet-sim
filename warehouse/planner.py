"""Space-time A*, Conflict-Based Search (CBS) and a prioritized fallback."""
import heapq
import itertools
import random
import time

MOVES = ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))   # wait + 4-connected
MAX_T = 200


class Constraints:
    """Per-agent constraints used by space-time A*.

    vertex : {(cell, t)}           agent may not be at `cell` at time t
    edge   : {(a, b, t)}           agent may not move a->b between t and t+1
    blocked: {cell: t_from}        cell is occupied forever from t_from on
    """

    def __init__(self):
        self.vertex, self.edge, self.blocked = set(), set(), {}


def plan_single(grid, start, goal, cons, max_t=MAX_T):
    """Shortest collision-free (w.r.t. `cons`) path as a list of cells."""
    dist = grid.dist_map(goal)
    if start not in dist or goal in cons.blocked:
        return None
    goal_free_after = max((t for (p, t) in cons.vertex if p == goal), default=-1)
    counter = itertools.count()
    open_ = [(dist[start], 0, next(counter), start)]
    parent = {(start, 0): None}
    while open_:
        _, t, _, pos = heapq.heappop(open_)
        if pos == goal and t > goal_free_after:
            path, node = [], (pos, t)
            while node is not None:
                path.append(node[0])
                node = parent[node]
            return path[::-1]
        if t >= max_t:
            continue
        for dx, dy in MOVES:
            nxt = (pos[0] + dx, pos[1] + dy)
            if not grid.walkable(nxt) or (nxt, t + 1) in parent:
                continue
            if (nxt, t + 1) in cons.vertex or (pos, nxt, t) in cons.edge:
                continue
            if nxt in cons.blocked and t + 1 >= cons.blocked[nxt]:
                continue
            f = t + 1 + dist[nxt]
            if f > max_t:
                continue
            parent[(nxt, t + 1)] = (pos, t)
            heapq.heappush(open_, (f, t + 1, next(counter), nxt))
    return None


# ------------------------------------------------------------------- CBS
def _at(path, t):
    return path[min(t, len(path) - 1)]


def find_conflict(paths):
    horizon = max(len(p) for p in paths)
    n = len(paths)
    for t in range(horizon):
        seen = {}
        for i in range(n):
            a = _at(paths[i], t)
            if a in seen:
                return ("v", seen[a], i, a, t)
            seen[a] = i
        for i in range(n):
            for j in range(i + 1, n):
                a, b = _at(paths[i], t), _at(paths[j], t)
                if a == _at(paths[j], t + 1) and b == _at(paths[i], t + 1):
                    return ("e", i, j, a, b, t)
    return None


def _constraints_for(cons_list, agent):
    c = Constraints()
    for a, kind, data in cons_list:
        if a != agent:
            continue
        (c.vertex if kind == "v" else c.edge).add(data)
    return c


def cbs(grid, starts, goals, node_limit=400, time_limit=0.25):
    """Optimal (sum-of-costs) CBS. Returns (paths, expansions) or None."""
    n = len(starts)
    paths = [plan_single(grid, starts[i], goals[i], Constraints()) for i in range(n)]
    if any(p is None for p in paths):
        return None
    tie = itertools.count()
    cost = sum(len(p) - 1 for p in paths)
    heap = [(cost, next(tie), (), paths)]
    t0, expansions = time.perf_counter(), 0
    while heap:
        if expansions >= node_limit or time.perf_counter() - t0 > time_limit:
            return None
        _, _, cons, paths = heapq.heappop(heap)
        conflict = find_conflict(paths)
        if conflict is None:
            return paths, expansions
        expansions += 1
        if conflict[0] == "v":
            _, i, j, cell, t = conflict
            branches = [(i, "v", (cell, t)), (j, "v", (cell, t))]
        else:
            _, i, j, a, b, t = conflict
            branches = [(i, "e", (a, b, t)), (j, "e", (b, a, t))]
        for agent, kind, data in branches:
            new_cons = cons + ((agent, kind, data),)
            p = plan_single(grid, starts[agent], goals[agent],
                            _constraints_for(new_cons, agent))
            if p is None:
                continue
            new_paths = list(paths)
            new_paths[agent] = p
            heapq.heappush(heap, (sum(len(q) - 1 for q in new_paths),
                                  next(tie), new_cons, new_paths))
    return None


# ------------------------------------------------- prioritized (fallback)
def prioritized(grid, starts, goals, order):
    cons = Constraints()
    paths = [None] * len(starts)
    for i in order:
        p = plan_single(grid, starts[i], goals[i], cons)
        if p is None:
            return None
        paths[i] = p
        for t, cell in enumerate(p):
            cons.vertex.add((cell, t))
        for t in range(len(p) - 1):
            if p[t] != p[t + 1]:
                cons.edge.add((p[t + 1], p[t], t))
        cons.blocked[p[-1]] = len(p) - 1
    return paths


def plan_all(grid, starts, goals, node_limit=400, time_limit=0.25, rng=None):
    """CBS first; prioritized planning if CBS runs out of budget; else wait."""
    rng = rng or random
    res = cbs(grid, starts, goals, node_limit, time_limit)
    if res is not None:
        return res[0], "CBS", res[1]
    order = list(range(len(starts)))
    for attempt in range(4):
        if attempt:
            rng.shuffle(order)
        paths = prioritized(grid, starts, goals, order)
        if paths is not None:
            return paths, "PRIORITIZED", 0
    return [[s] for s in starts], "WAIT", 0
