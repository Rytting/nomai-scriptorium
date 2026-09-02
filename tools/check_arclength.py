"""Would an exact arc-length walk put the glyphs where Luxor puts them?

`transform` places column i at path fraction k_i = cumulative(i) / total, a fraction
of *arc length*. Luxor measures that length on a discretised copy of the spiral; a
Python renderer would use the closed form, which for r = a*exp(b*theta) is

    s(theta) = sqrt(1 + b^2) * (a / b) * (exp(b*theta) - exp(b*theta0))

So: recover the bottom line from a real drawing, fit the spiral to it, compute each
column's exact arc-length fraction, and compare with the k_i the formula demands. If
they agree, the two renderers would agree too, and the only difference left is where
the period-doubling loop happens to stop.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.gridgen import K, ROWS  # noqa: E402
from nomai.vision import analyze  # noqa: E402
from fit_spiral import fit_log_spiral  # noqa: E402

SVG = ROOT / "data" / "svg"
manifest = json.loads((SVG / "manifest.json").read_text(encoding="utf-8"))


def bottom_line_points(path):
    """One point per column, on the spiral itself (row ROWS has zero offset)."""
    obs = analyze(path)
    ncols = obs.ncols
    delta = 1 / (ncols - 1) if ncols > 1 else 0.0
    # analyze() already solved rows and rotations; redo the small part we need
    from collections import defaultdict

    from nomai.svgparse import parse_svg
    from nomai.vision import _bfs, decompose, fit_cluster, solve_rotations

    strokes, _ = parse_svg(path)
    clusters, connections = decompose(strokes)
    fits = {k: fit_cluster(c) for k, c in clusters.items()}
    adj = defaultdict(set)
    for ka, _, kb, _ in connections:
        adj[ka].add(kb)
        adj[kb].add(ka)
    root = min(clusters, key=lambda k: fits[k][0].scale)
    columns = {k: d + 1 for k, d in _bfs(adj, root).items()}
    centers = {k: fits[k][0].origin for k in clusters}
    thetas = solve_rotations(columns, centers, fits, ncols)

    row_of = {}
    for (i, j) in obs.glyphs:
        row_of.setdefault(i, []).append(j)

    pts = []
    for i in range(1, ncols + 1):
        members = [k for k, c in columns.items() if c == i]
        u = (-math.sin(thetas[i]), math.cos(thetas[i]))
        members.sort(key=lambda k: centers[k][0] * u[0] + centers[k][1] * u[1])
        js = sorted(row_of[i])
        gap = 3 * K * (1 + (i - 1) * delta)
        c = centers[members[-1]]
        d = (js[-1] - ROWS) * gap
        pts.append((c[0] - d * u[0], c[1] - d * u[1]))
    return pts, ncols


def wanted_fractions(ncols):
    d = 1 / (ncols - 1)
    total = (ncols - 1) + 0.5 * (ncols - 1) ** 2 * d
    return [((i - 1) + 0.5 * (i - 1) ** 2 * d) / total for i in range(1, ncols + 1)]


print(f"{'file':>9} {'cols':>5} {'b':>8} {'max |k error|':>14} {'as columns':>11}")
print("-" * 52)
shown = 0
for entry in manifest:
    if entry["handwriting"] != 0.0 or shown >= 8:
        continue
    try:
        pts, ncols = bottom_line_points(SVG / entry["file"])
    except Exception as exc:  # noqa: BLE001
        continue
    if ncols < 8:
        continue
    fit = fit_log_spiral(pts)
    if fit is None:
        continue
    shown += 1
    _resid, cx, cy, b, a = fit
    th, prev = [], None
    for x, y in pts:
        ang = math.atan2(y - cy, x - cx)
        if prev is not None:
            ang = prev + math.atan2(math.sin(ang - prev), math.cos(ang - prev))
        prev = ang
        th.append(ang)
    s = [math.exp(b * t) for t in th]          # arc length up to a constant factor
    span = s[-1] - s[0]
    got = [(v - s[0]) / span for v in s]
    want = wanted_fractions(ncols)
    err = max(abs(g - w) for g, w in zip(got, want))
    print(f"{entry['file']:>9} {ncols:>5} {b:>8.3f} {err:>14.4f} {err * (ncols - 1):>11.2f}")
