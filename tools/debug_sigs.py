"""What do the clusters that match no known glyph actually look like?"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import Observation  # noqa: E402
from nomai.gridgen import grid_from_message  # noqa: E402
from nomai.oracle import UPSTREAM  # noqa: E402
from nomai.svgparse import parse_svg  # noqa: E402
from nomai.vision import SIGNATURE, decompose  # noqa: E402

SVG = ROOT / "data" / "svg"
manifest = json.loads((SVG / "manifest.json").read_text(encoding="utf-8"))
canonical = set(SIGNATURE.values())

bad = Counter()
for entry in manifest:
    strokes, _ = parse_svg(SVG / entry["file"])
    clusters, connections = decompose(strokes)
    want = Observation.from_grid(
        grid_from_message(entry["message"], entry["base"], UPSTREAM)
    )
    offenders = [c for c in clusters.values() if c.signature not in canonical]
    if not offenders:
        continue
    print(f"{entry['file']}  {entry['message']!r} base={entry['base']} "
          f"hw={entry['handwriting']}")
    print(f"  clusters={len(clusters)} (truth glyphs={len(want.glyphs)})  "
          f"connections={len(connections)} (truth={len(want.connections)})")
    for c in offenders:
        print(f"    unmatched signature {c.signature}")
        bad[c.signature] += 1

print(f"\nunmatched signatures overall: {dict(bad)}")
print(f"canonical signatures: {sorted(canonical)}")
