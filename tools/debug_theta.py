"""Compare recovered rotations against the ones the true glyph ids imply."""
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import Observation  # noqa: E402
from nomai.gridgen import grid_from_message  # noqa: E402
from nomai.oracle import UPSTREAM  # noqa: E402
from nomai.svgparse import parse_svg  # noqa: E402
from nomai.vision import (  # noqa: E402
    _angdiff,
    _bfs,
    decompose,
    fit_cluster,
    solve_rotations,
)

SVG = ROOT / "data" / "svg"
manifest = {e["file"]: e for e in json.loads((SVG / "manifest.json").read_text())}

for name in sys.argv[1:] or ["s013.svg", "s007.svg", "s031.svg"]:
    entry = manifest[name]
    msg, base = entry["message"], entry["base"]
    want = Observation.from_grid(grid_from_message(msg, base, UPSTREAM))
    true_by_col = defaultdict(list)
    for (i, j), gid in want.glyphs.items():
        true_by_col[i].append((j, gid))
    for i in true_by_col:
        true_by_col[i].sort()

    strokes, _ = parse_svg(SVG / name)
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

    print(f"\n=== {name}  {msg!r} base={base} hw={entry['handwriting']}")
    print(f"  clusters={len(clusters)} my_ncols={ncols} true_ncols={len(want.paths[0])}")
    print(f"  my column sizes  {Counter(columns.values())}")
    print(f"  true column sizes {Counter(i for i, _ in want.glyphs)}")
    print(f"  {'col':>3} {'my_theta':>9} {'step':>7}  true_gids  theta_of_true_fit")
    prev = None
    for i in range(1, ncols + 1):
        members = [k for k, c in columns.items() if c == i]
        tg = [g for _, g in true_by_col.get(i, [])]
        # what angle would the true glyph ids imply?
        implied = []
        for k in members:
            for f in fits[k]:
                if f.gid in tg:
                    implied.append(round(math.degrees(f.theta), 1))
                    break
        step = "" if prev is None else f"{math.degrees(_angdiff(thetas[i], prev)):>7.1f}"
        print(f"  {i:>3} {math.degrees(thetas[i]):>9.1f} {step:>7}  {tg}  {implied}")
        prev = thetas[i]
