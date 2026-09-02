"""Does the connection-graph BFS recover the column structure of the real sample?

Truth for hello@200000: 7 columns, 13 glyphs, 12 connections, with a known number
of glyphs per column.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.svgparse import parse_svg  # noqa: E402
from nomai.vision import column_index, decompose  # noqa: E402

truth = json.loads(
    (ROOT / "data" / "truth" / "hello_base200000.json").read_text(encoding="utf-8")
)
per_col_true = Counter(e["i"] for e in truth["grid"]["glyphs"])
print(f"truth: {truth['grid']['ncols']} columns, "
      f"glyphs per column {[per_col_true[i] for i in range(1, truth['grid']['ncols'] + 1)]}")
print(f"truth paths: {truth['grid']['paths']}")

for sample in sorted((ROOT / "assets" / "samples").glob("*.svg")):
    strokes, circles = parse_svg(sample)
    clusters, connections = decompose(strokes)
    col = column_index(clusters, connections)
    ncols = max(col.values())
    per_col = Counter(col.values())
    got = [per_col[i] for i in range(1, ncols + 1)]
    ok_cols = ncols == truth["grid"]["ncols"]
    ok_shape = got == [per_col_true[i] for i in range(1, truth["grid"]["ncols"] + 1)]
    print(f"\n{sample.name}")
    print(f"  clusters={len(clusters)} connections={len(connections)} "
          f"unreached={len(clusters) - len(col)}")
    print(f"  columns={ncols}  glyphs per column {got}")
    print(f"  matches truth: columns={ok_cols}  shape={ok_shape}")
    # every connection must span consecutive columns
    spans = Counter(abs(col[kb] - col[ka]) for ka, _, kb, _ in connections)
    print(f"  connection column spans: {dict(spans)}  (all should be 1)")
