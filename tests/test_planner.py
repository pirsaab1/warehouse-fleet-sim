"""Run with:  python -m unittest discover tests"""
import random
import unittest

from warehouse.grid import Grid
from warehouse.planner import cbs, find_conflict, plan_all
from warehouse.sim import Simulation


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.grid = Grid()

    def test_cbs_paths_are_conflict_free(self):
        rng = random.Random(1)
        cells = self.grid.free_cells()
        for _ in range(5):
            pts = rng.sample(cells, 12)
            starts, goals = pts[:6], pts[6:]
            res = cbs(self.grid, starts, goals, node_limit=2000, time_limit=2.0)
            self.assertIsNotNone(res)
            paths, _ = res
            self.assertIsNone(find_conflict(paths))
            for p, s, g in zip(paths, starts, goals):
                self.assertEqual((p[0], p[-1]), (s, g))

    def test_head_on_swap_is_resolved(self):
        a, b = (0, self.grid.h - 1), (6, self.grid.h - 1)
        paths, method, _ = plan_all(self.grid, [a, b], [b, a])
        self.assertIsNone(find_conflict(paths))

    def test_simulation_has_no_collisions(self):
        sim = Simulation(10, seed=3)
        for _ in range(200):
            sim.step()
        self.assertEqual(sim.collisions, 0)
        self.assertGreater(sim.delivered, 0)


if __name__ == "__main__":
    unittest.main()
