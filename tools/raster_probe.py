"""Rasterise a drawing, then try to get its geometry back out of the pixels.

Nothing about reading is attempted. The question is narrower and comes first: does the
shape survive a trip through pixels? Two numbers answer it -- how far a true vertex is
from the nearest recovered corner, and how far a recovered corner is from any true
vertex. The first says whether anything was lost, the second whether anything was
invented.
"""
import pathlib
import sys
import time

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.codec import write  # noqa: E402
from nomai.glyphs import KNOWN_GLYPHS  # noqa: E402
from nomai.oracle import STRICT  # noqa: E402
from nomai.raster import rasterize, simplify, thin, trace  # noqa: E402
from nomai.render import SpiralLayout, render_grid  # noqa: E402
from nomai.svgparse import parse_svg  # noqa: E402

OUT = ROOT / "data" / "raster"
OUT.mkdir(parents=True, exist_ok=True)

CASES = [("hi", 900), ("hi", 1600),
         ("Come to the Ash Twin Project", 1800),
         ("Come to the Ash Twin Project", 2600)]

for msg, width in CASES:
    grid = write(msg, 256, STRICT)
    strokes, dots = parse_svg(render_grid(grid, KNOWN_GLYPHS, 0.0, 47))

    t0 = time.time()
    img, to_world = rasterize(strokes, dots, width=width)
    sk = thin(np.array(img) < 128)
    paths = trace(sk)
    polys = [simplify([to_world((x, y)) for y, x in p], 3.0) for p in paths]
    dt = time.time() - t0

    truth = np.array([v for s in strokes for v in s.points])
    rec = np.array([q for p in polys for q in p])
    lost = [float(np.min(np.hypot(rec[:, 0] - v[0], rec[:, 1] - v[1]))) for v in truth]
    made = [float(np.min(np.hypot(truth[:, 0] - q[0], truth[:, 1] - q[1]))) for q in rec]

    layout = SpiralLayout(grid.ncols)
    origins = np.array([layout.place(*c)((0.0, 0.0)) for c in grid.glyphs])
    owner = [int(np.argmin(np.hypot(origins[:, 0] - q[0], origins[:, 1] - q[1])))
             for q in rec]
    per = np.bincount(owner, minlength=len(origins))
    sizes = [len(KNOWN_GLYPHS[v - 1].allpoints) for v in grid.glyphs.values()]

    print(f"{msg[:22]!r:24} {width:>5}px -> {img.size[0]}x{img.size[1]}  [{dt:.1f}s]")
    print(f"    strokes {len(strokes):>3} -> pieces {len(polys):>3}      "
          f"vertices {len(truth):>3} -> corners {len(rec):>3}")
    print(f"    lost : true vertex to nearest corner   median {np.median(lost):5.2f}"
          f"  worst {max(lost):6.2f}")
    print(f"    made : corner to nearest true vertex   median {np.median(made):5.2f}"
          f"  worst {max(made):6.2f}")
    print(f"    corners per glyph {per.min()}..{per.max()}   "
          f"(glyphs really have {min(sizes)}..{max(sizes)})")

    stem = msg[:12].replace(" ", "_")
    img.save(OUT / f"{stem}_{width}.png")
    Image.fromarray(np.where(sk, 0, 255).astype(np.uint8)).save(
        OUT / f"{stem}_{width}_skeleton.png")

print("\nGlyph features are 20-40 units across, so the medians above are the part that")
print("works. The counts are the part that does not: the drawing is one connected")
print("graph, and cutting it at every junction returns fragments, not strokes.")
