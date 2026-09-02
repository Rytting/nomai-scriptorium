"""Dump every two-point stroke that decompose could not place, with the evidence."""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import Observation  # noqa: E402
from nomai.gridgen import grid_from_message  # noqa: E402
from nomai.oracle import UPSTREAM  # noqa: E402
from nomai.svgparse import parse_svg  # noqa: E402
from nomai.vision import decompose  # noqa: E402

SVG = ROOT / "data" / "svg"
manifest = json.loads((SVG / "manifest.json").read_text(encoding="utf-8"))

shown = 0
for entry in manifest:
    strokes, _ = parse_svg(SVG / entry["file"])
    clusters, connections = decompose(strokes)
    owned = {p for cl in clusters.values() for st in cl.strokes for p in st.points}
    bad = [(ka, pa, kb, pb) for ka, pa, kb, pb in connections
           if pa not in owned or pb not in owned]
    if not bad:
        continue
    want = Observation.from_grid(
        grid_from_message(entry["message"], entry["base"], UPSTREAM)
    )
    shown += 1
    if shown > 3:
        continue
    cents = {k: cl.centroid for k, cl in clusters.items()}
    sizes = {k: max(math.dist(cents[k], p) for st in cl.strokes for p in st.points)
             for k, cl in clusters.items()}
    print(f"\n=== {entry['file']}  {entry['message']!r} base={entry['base']} "
          f"hw={entry['handwriting']}")
    print(f"  clusters={len(clusters)} (truth {len(want.glyphs)})  "
          f"connections={len(connections)} (truth {len(want.connections)})")
    for ka, pa, kb, pb in bad:
        loose, host = (pa, kb) if pa not in owned else (pb, ka)
        ranked = sorted(cents, key=lambda k: math.dist(cents[k], loose))[:3]
        print(f"  loose endpoint {tuple(round(v, 1) for v in loose)}  "
              f"stroke length={math.dist(pa, pb):.1f}  host cluster={host}")
        for k in ranked:
            print(f"      cluster {k:>3}: centre distance={math.dist(cents[k], loose):>7.1f}"
                  f"  radius={sizes[k]:>6.1f}  strokes={len(clusters[k].strokes)}"
                  f"  sig={clusters[k].signature}"
                  f"{'   <- host' if k == host else ''}")

print(f"\nsamples with unplaced endpoints: {shown}/{len(manifest)}")
