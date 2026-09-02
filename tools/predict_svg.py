"""Predict an SVG's path counts from the grid, and check against the real sample.

If this matches exactly we understand `draw` completely, which is the precondition
for inverting it. From src/NomaiText.jl:

  draw(PolySpec)  -> one stroke path, plus a filled circle on each *non-terminal*
                     vertex (all vertices when closed, points[2:end-1] when open)
  draw(Glyph)     -> core, then annotation if present
  connections     -> one stroke line, plus a filled circle at each end
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.glyphs import KNOWN_GLYPHS  # noqa: E402

SAMPLE = ROOT / "assets" / "samples" / "hello_base200000_seed47.svg"
TRUTH = ROOT / "data" / "truth" / "hello_base200000.json"


def parse_svg(path: Path):
    raw = path.read_text(encoding="utf-8")
    if raw.lstrip().startswith('"'):
        raw = json.loads(raw)  # the API returns a JSON-quoted string
    paths = re.findall(r'<path\s+style="([^"]*)"\s+d="([^"]*)"', raw)
    stroke, filled = [], []
    for style, d in paths:
        pts = [
            (float(x), float(y))
            for x, y in re.findall(r'[ML]\s+([-\d.]+)\s+([-\d.]+)', d)
        ]
        (filled if "stroke:none" in style else stroke).append((d, pts))
    return stroke, filled


def polyspec_counts(ps):
    """(stroke paths, filled circles) contributed by one PolySpec."""
    n = len(ps.points)
    return 1, (n if ps.close else max(0, n - 2))


def predict(truth):
    grid = truth["grid"]
    strokes = circles = 0
    open_2pt = 0
    for entry in grid["glyphs"]:
        g = KNOWN_GLYPHS[entry["glyph"] - 1]
        for ps in (g.core, g.annotation):
            if ps is None:
                continue
            s, c = polyspec_counts(ps)
            strokes += s
            circles += c
            if len(ps.points) == 2:
                open_2pt += 1
    n_conn = len(grid["connections"])
    strokes += n_conn
    circles += 2 * n_conn
    return strokes, circles, n_conn, open_2pt


truth = json.loads(TRUTH.read_text(encoding="utf-8"))
stroke, filled = parse_svg(SAMPLE)
p_stroke, p_circle, n_conn, n_spike = predict(truth)

print(f"sample: {SAMPLE.name}   message={truth['message']!r} base={truth['base']}")
print(f"  glyphs in grid: {len(truth['grid']['glyphs'])}   connections: {n_conn}")
print()
print(f"{'':<18}{'predicted':>10}{'actual':>10}  match")
print(f"{'stroke paths':<18}{p_stroke:>10}{len(stroke):>10}  {p_stroke == len(stroke)}")
print(f"{'filled circles':<18}{p_circle:>10}{len(filled):>10}  {p_circle == len(filled)}")
print(f"{'total <path>':<18}{p_stroke + p_circle:>10}{len(stroke) + len(filled):>10}"
      f"  {p_stroke + p_circle == len(stroke) + len(filled)}")
print()

# Two-point strokes are ambiguous: a connection and a spike annotation look the same.
print(f"two-point strokes: {sum(1 for _, pts in stroke if len(pts) == 2)} actual"
      f"  = {n_conn} connections + {n_spike} spike annotations predicted")
print()
print("stroke point-count histogram (actual):",
      dict(sorted(Counter(len(pts) for _, pts in stroke).items())))
