"""Why does one drawing read at one winding and not the other?

The suspicion is the tightness fit: the reader sweeps `b` and takes the lowest
residual, and for a few drawings that lands in the wrong minimum. This walks the
residual for a failing drawing so we can see whether the truth is a minimum the search
missed, or not a minimum at all.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.codec import write  # noqa: E402
from nomai.decode import decode_strict  # noqa: E402
from nomai.glyphs import KNOWN_GLYPHS  # noqa: E402
from nomai.oracle import STRICT  # noqa: E402
from nomai.render import SpiralLayout, render_grid  # noqa: E402
from nomai.svgparse import parse_svg  # noqa: E402
from nomai.vision import (  # noqa: E402
    assign_rows,
    decompose,
    fit_cluster,
    layering,
    procrustes,
    solve_rotations,
)

CASES = [
    ("Come to the Ash Twin Project", "Poke", 0.29),
    ("a", "", 0.2),
    ("c", "", 0.2),
]
BASE = 256


def landscape(svg_text, ncols_hint=None):
    """Residual of the global placement over (flip, b), before any refinement."""
    strokes, _ = parse_svg(svg_text)
    clusters, conns = decompose(strokes)
    fits = {k: fit_cluster(c) for k, c in clusters.items()}
    keys = sorted(clusters, key=lambda k: fits[k][0].scale)
    columns = None
    for root in keys:
        columns = layering({k: None for k in keys}, conns) if False else None
        break
    # replicate analyze's rooting search
    from nomai.vision import layering as _layering
    for root in keys:
        cand = _layering(keys, conns)
        if cand:
            columns = cand
            break
    if columns is None:
        return None
    ncols = max(columns.values())
    centers = {k: fits[k][0].origin for k in clusters}
    thetas = solve_rotations(columns, centers, fits, ncols)
    rows = assign_rows(columns, centers, thetas, ncols)[0]
    ks = [k for k in centers if k in columns and k in rows]
    obs = [centers[k] for k in ks]
    out = []
    for f in (1, -1):
        for i in range(10, 62):
            b = round(0.01 * i, 3)
            cand = SpiralLayout(ncols, 0.0, f, b)
            got = procrustes([cand.place(columns[k], rows[k])((0.0, 0.0)) for k in ks],
                             obs)
            if got is not None:
                out.append((got[2], f, b))
    out.sort()
    return ncols, out


for msg, sig, tight in CASES:
    grid = write(msg, BASE, STRICT, sig or None)
    for flip in (1, -1):
        svg = render_grid(grid, KNOWN_GLYPHS, 0.15, 47, 0.0, flip, tight)
        try:
            got = decode_strict(__import__("nomai.vision", fromlist=["analyze"])
                                .analyze(svg), bases=(BASE,))
            reads = len(got) == 1 and got[0][2] == (f"{sig}: {msg}" if sig else msg)
        except Exception as exc:  # noqa: BLE001
            reads = f"{type(exc).__name__}"
        land = landscape(svg)
        if land is None:
            print(f"{msg[:14]!r:18} sig={sig!r:8} flip={flip:>2} b={tight}  "
                  f"reads={reads}  (no layering)")
            continue
        ncols, out = land
        best = out[0]
        truth = min(r for r in out if r[1] == flip and abs(r[2] - tight) < 0.006)
        rank = [i for i, r in enumerate(out) if r == truth][0]
        print(f"{msg[:14]!r:18} sig={sig!r:8} flip={flip:>2} b={tight} cols={ncols:>3} "
              f" reads={str(reads):<6}")
        print(f"    best fit   : resid {best[0]:8.3f}  flip {best[1]:>2}  b {best[2]}")
        print(f"    the truth  : resid {truth[0]:8.3f}  flip {truth[1]:>2}  b {truth[2]}"
              f"   ranked #{rank + 1} of {len(out)}")
