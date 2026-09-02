"""Do the fitted glyph scales fall into clean per-column groups?

Two glyphs in one column are drawn at the same scale (k_i + 1) by construction, and
scale rises strictly with the column index. If the fits are clean, the columns can be
read straight off the scales -- no graph reasoning needed.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.svgparse import parse_svg
from nomai.vision import decompose, fit_cluster

truth = json.loads(
    (ROOT / "data" / "truth" / "hello_base200000.json").read_text(encoding="utf-8")
)
per_col = Counter(e["i"] for e in truth["grid"]["glyphs"])
ncols = truth["grid"]["ncols"]
print(f"truth: {ncols} columns, sizes {[per_col[i] for i in range(1, ncols + 1)]}")

for sample in sorted((ROOT / "assets" / "samples").glob("*.svg")):
    strokes, _ = parse_svg(sample)
    clusters, connections = decompose(strokes)
    print(f"\n=== {sample.name}")
    rows = []
    for key, cl in clusters.items():
        cands = fit_cluster(cl)
        if not cands:
            print(f"  cluster {key}: NO CANDIDATE  signature={cl.signature}")
            continue
        resid, gid, scale, theta = cands[0]
        n_tied = sum(1 for c in cands if c[0] < resid + 0.05)
        rows.append((scale, resid, gid, n_tied, key))
    for scale, resid, gid, n_tied, key in sorted(rows):
        print(f"  scale={scale:>6.3f}  resid={resid:>6.3f}  best_gid={gid:>2}"
              f"  tied_candidates={n_tied}")
