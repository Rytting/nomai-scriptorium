"""Is the layout path a plain logarithmic spiral, and can it be refitted from a drawing?

`draw_spiral` builds its path with Luxor's `spiral(164, .29, log=true, period=p)`,
adjusting the period until the path is long enough. If the curve really is
r = a * exp(b * theta), a Python renderer needs no Luxor at all -- and the exponent
should come out near 0.29 whatever the message.

Recovers the bottom line from the drawing (glyph origin minus its row offset), finds
the centre that makes log(r) linear in theta, and reports the fit.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.gridgen import K, ROWS  # noqa: E402
from nomai.svgparse import parse_svg  # noqa: E402
from nomai.vision import (  # noqa: E402
    _bfs,
    decompose,
    fit_cluster,
    solve_rotations,
)
from collections import defaultdict  # noqa: E402


def bottom_line(path):
    strokes, _ = parse_svg(path)
    clusters, connections = decompose(strokes)
    fits = {k: fit_cluster(c) for k, c in clusters.items()}
    adj = defaultdict(set)
    for ka, _, kb, _ in connections:
        adj[ka].add(kb)
        adj[kb].add(ka)
    root = min(clusters, key=lambda k: fits[k][0].scale)
    columns = {k: d + 1 for k, d in _bfs(adj, root).items()}
    ncols = max(columns.values())
    centers = {k: fits[k][0].origin for k in clusters}
    thetas = solve_rotations(columns, centers, fits, ncols)
    delta = 1 / (ncols - 1) if ncols > 1 else 0.0

    pts = []
    for i in range(1, ncols + 1):
        members = [k for k, c in columns.items() if c == i]
        u = (-math.sin(thetas[i]), math.cos(thetas[i]))
        gap = 3 * K * (1 + (i - 1) * delta)
        # take the member furthest along +u as the one nearest row ROWS
        m = max(members, key=lambda k: centers[k][0] * u[0] + centers[k][1] * u[1])
        # its row is unknown here, so just record the point and the axis
        pts.append((centers[m], u, gap))
    return pts, ncols


def fit_log_spiral(points):
    """Find the centre that makes log(r) most linear in unwrapped theta."""
    best = None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    cx0, cy0 = sum(xs) / len(xs), sum(ys) / len(ys)
    step = 400.0
    cx, cy = cx0, cy0
    for _ in range(60):
        cands = [(cx + dx * step, cy + dy * step)
                 for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        scored = []
        for ccx, ccy in cands:
            th, lr = [], []
            prev = None
            for x, y in points:
                a = math.atan2(y - ccy, x - ccx)
                if prev is not None:
                    a = prev + math.atan2(math.sin(a - prev), math.cos(a - prev))
                prev = a
                r = math.hypot(x - ccx, y - ccy)
                if r <= 0:
                    break
                th.append(a)
                lr.append(math.log(r))
            if len(th) != len(points):
                continue
            n = len(th)
            mt, ml = sum(th) / n, sum(lr) / n
            den = sum((t - mt) ** 2 for t in th)
            if den <= 0:
                continue
            b = sum((t - mt) * (l - ml) for t, l in zip(th, lr)) / den
            resid = math.sqrt(
                sum((l - ml - b * (t - mt)) ** 2 for t, l in zip(th, lr)) / n
            )
            scored.append((resid, ccx, ccy, b, math.exp(ml - b * mt)))
        if not scored:
            break
        scored.sort()
        if best is None or scored[0][0] < best[0]:
            best = scored[0]
        if scored[0][1] == cx and scored[0][2] == cy:
            step /= 2
        cx, cy = scored[0][1], scored[0][2]
    return best


SVG = ROOT / "data" / "svg"
manifest = json.loads((SVG / "manifest.json").read_text(encoding="utf-8"))
print(f"{'file':>9} {'cols':>5} {'b (exponent)':>13} {'a':>10} {'log-r rms':>10}")
print("-" * 52)
shown = 0
for entry in manifest:
    if entry["handwriting"] != 0.0 or shown >= 10:
        continue
    try:
        pts, ncols = bottom_line(SVG / entry["file"])
    except Exception as exc:  # noqa: BLE001
        print(f"{entry['file']:>9}  {type(exc).__name__}")
        continue
    if ncols < 5:
        continue
    shown += 1
    fit = fit_log_spiral([p[0] for p in pts])
    if fit is None:
        print(f"{entry['file']:>9} {ncols:>5}   no fit")
        continue
    resid, cx, cy, b, a = fit
    print(f"{entry['file']:>9} {ncols:>5} {b:>13.4f} {a:>10.1f} {resid:>10.4f}")
