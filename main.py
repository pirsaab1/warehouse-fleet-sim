"""Warehouse Fleet Sim - entry point.

  python main.py                        drone view window (1080p canvas, auto-scaled)
  python main.py --view iso             isometric 3D view
  python main.py --robots 12            more robots
  python main.py --res 1080p            smaller canvas (1080p | 1440p | 1080p | native)
  python main.py --save demo.gif        render a GIF (no window needed)
  python main.py --bench 500            headless benchmark
"""
import argparse
import os
import time

from warehouse.sim import Simulation

RES = {"1080p": (3840, 2160), "1440p": (2560, 1440), "1080p": (1920, 1080), "native": None}


def parse():
    ap = argparse.ArgumentParser(description="Multi-robot warehouse simulator (CBS)")
    ap.add_argument("--robots", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--view", choices=["drone", "iso"], default="drone")
    ap.add_argument("--res", choices=list(RES), default=None,
                    help="canvas size (default: 1080p for the window, native for --save)")
    ap.add_argument("--cell", type=int, default=None,
                    help="pixels per cell (used with --res native)")
    ap.add_argument("--step-ms", type=int, default=160, help="ms per simulation step")
    ap.add_argument("--save", metavar="FILE.gif", help="export a GIF and exit")
    ap.add_argument("--steps", type=int, default=120, help="steps to record for --save")
    ap.add_argument("--bench", type=int, metavar="STEPS", help="headless benchmark")
    return ap.parse_args()


def make_renderer(args, sim, show_window=True):
    res = args.res or ("native" if args.save else "1080p")
    cell = args.cell or (20 if args.save else 26)
    if args.view == "drone":
        from warehouse.render_drone import DroneRenderer as R
    else:
        from warehouse.render import Renderer as R
    return R(sim, cell=cell, show_window=show_window, resolution=RES[res])


def bench(args):
    sim = Simulation(args.robots, seed=args.seed)
    t0 = time.perf_counter()
    for _ in range(args.bench):
        sim.step()
    wall = time.perf_counter() - t0
    mc = sim.method_counts
    print(f"robots={args.robots} steps={args.bench} delivered={sim.delivered} "
          f"throughput={sim.throughput:.2f}/100 steps collisions={sim.collisions}")
    print(f"replans={sim.replans} avg={sim.avg_replan_ms:.1f} ms "
          f"CBS={mc['CBS']} PRIORITIZED={mc['PRIORITIZED']} WAIT={mc['WAIT']} "
          f"wall={wall:.1f}s")


def save_gif(args):
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    from PIL import Image
    sim = Simulation(args.robots, seed=args.seed)
    rend = make_renderer(args, sim, show_window=False)
    frames, sub = [], 3
    for s in range(args.steps):
        sim.step()
        for k in range(sub):
            rend.draw((k + 1) / sub)
            frames.append(Image.frombytes("RGB", rend.size, rend.to_bytes())
                          .convert("P", palette=Image.ADAPTIVE, colors=96))
        print(f"\rrecording {s + 1}/{args.steps}", end="")
    frames[0].save(args.save, save_all=True, append_images=frames[1:],
                   duration=max(args.step_ms // sub, 20), loop=0, optimize=True)
    print(f"\nsaved {args.save}")


def run_window(args):
    import pygame
    sim = Simulation(args.robots, seed=args.seed)
    rend = make_renderer(args, sim)
    clock = pygame.time.Clock()
    step_ms, acc, paused = args.step_ms, 0.0, False
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                pygame.quit()
                return
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_SPACE:
                    paused = not paused
                elif e.key in (pygame.K_UP, pygame.K_PLUS, pygame.K_EQUALS):
                    step_ms = max(30, int(step_ms * 0.8))
                elif e.key in (pygame.K_DOWN, pygame.K_MINUS):
                    step_ms = min(800, int(step_ms * 1.25))
                elif e.key == pygame.K_r:
                    sim = Simulation(args.robots, seed=args.seed + sim.t + 1)
                    rend.sim = sim
        dt = clock.tick(60)
        if not paused:
            acc += dt
            while acc >= step_ms:
                acc -= step_ms
                sim.step()
        rend.draw(min(acc / step_ms, 1.0) if not paused else 1.0,
                  paused=paused, step_ms=step_ms)
        pygame.display.flip()


if __name__ == "__main__":
    a = parse()
    if a.bench:
        bench(a)
    elif a.save:
        save_gif(a)
    else:
        run_window(a)
#python main.py for the drone view or python main.py --view iso for the 3D view”,