"""Print what the row DP actually sees, next to the truth."""
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
    _bl,
    column_rotation,
    decompose,
    fit_cluster,
)
from collections import defaultdict  # noqa: E402

truth = json.loads(
    (ROOT / "data" / "truth" / "hello_base200000.json").read_text(encoding="utf-8")
)
true_rows = {}
for e in truth["grid"]["glyphs"]:
    true_rows.setdefault(e["i"], []).append(e["j"])
for i in true_rows:
    true_rows[i].sort()

sample = ROOT / "assets" / "samples" / "hello_base200000_seed47.svg"
strokes, _ = parse_svg(sample)
clusters, connections = decompose(strokes)
fits = {k: fit_cluster(c) for k, c in clusters.items()}

adj = defaultdict(set)
for ka, _, kb, _ in connections:
    adj[ka].add(kb)
    adj[kb].add(ka)
root = min(clusters, key=lambda k: fits[k][0].scale)
columns = {k: d + 1 for k, d in _bfs(adj, root).items()}
ncols = max(columns.values())

origins = {k: fits[k][0].origin for k in clusters}
cents = {k: clusters[k].centroid for k in clusters}

thetas = {}
for i in range(1, ncols + 1):
    members = [k for k, c in columns.items() if c == i]
    offset = None
    if len(members) == 2:
        a, b = (origins[m] for m in members)
        offset = (b[0] - a[0], b[1] - a[1])
    thetas[i] = column_rotation([fits[k] for k in members], offset)

delta = 1 / (ncols - 1)
print(f"ncols={ncols}")
print(f"{'col':>3} {'theta':>8} {'gap':>7} {'dj':>3}  true_rows  members(proj, origin-vs-centroid)")
per_col = {}
for i in range(1, ncols + 1):
    s_h = 1 + (i - 1) * delta
    gap = 3 * K * s_h
    u = (-math.sin(thetas[i]), math.cos(thetas[i]))
    members = [k for k, c in columns.items() if c == i]
    members.sort(key=lambda k: origins[k][0] * u[0] + origins[k][1] * u[1])
    per_col[i] = (members, u, gap)
    projs = [origins[k][0] * u[0] + origins[k][1] * u[1] for k in members]
    dj = round((projs[1] - projs[0]) / gap) if len(members) == 2 else 0
    drift = [math.dist(origins[k], cents[k]) for k in members]
    print(f"{i:>3} {math.degrees(thetas[i]):>8.1f} {gap:>7.1f} {dj:>3}  {true_rows[i]}"
          f"  proj={[round(p, 1) for p in projs]} |origin-centroid|={[round(d, 1) for d in drift]}")

print("\nstep cost |bl_step . u| / gap, for the TRUE rows vs each alternative:")
for i in range(2, ncols + 1):
    members, u, gap = per_col[i]
    pm, pu, pgap = per_col[i - 1]
    sx = (math.sin(thetas[i - 1]) + math.sin(thetas[i])) / 2
    cy = (math.cos(thetas[i - 1]) + math.cos(thetas[i])) / 2
    nrm = math.hypot(sx, cy) or 1.0
    umid = (-sx / nrm, cy / nrm)
    prev_bl = _bl(origins[pm[0]], true_rows[i - 1][0], pgap, pu)
    line = []
    for cand in ((1, 2), (2, 3), (1, 3), (1, 1), (2, 2), (3, 3)):
        if len(members) == 1 and cand[0] != cand[1]:
            continue
        if len(members) == 2 and cand[0] == cand[1]:
            continue
        bl = _bl(origins[members[0]], cand[0], gap, u)
        d = (bl[0] - prev_bl[0], bl[1] - prev_bl[1])
        cost = abs(d[0] * umid[0] + d[1] * umid[1]) / gap
        mark = "  <-TRUE" if list(cand) == true_rows[i] else ""
        line.append(f"{cand}={cost:.3f}{mark}")
    print(f"  col {i}: " + "  ".join(line))
