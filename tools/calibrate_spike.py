"""Is there a rule that separates spikes from connections, and what does it key on?

No per-stroke labels are available without the pipeline that is failing, so this
uses the one number the truth does give for free: how many spikes a drawing has
(glyphs 23-28 are the spike-bearing ones). Rank every (stroke, candidate host) pair
by how well it fits as that glyph's spike; if a rule exists, the true spikes are
exactly the top N, and there is a gap between the Nth and the (N+1)th.

Reports that gap next to the drawing's own jitter level, measured as the median core
fit residual -- if the boundary tracks jitter rather than sitting still, the rule
needs an adaptive tolerance, not a constant.
"""
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import Observation  # noqa: E402
from nomai.gridgen import grid_from_message  # noqa: E402
from nomai.oracle import UPSTREAM  # noqa: E402
from nomai.svgparse import parse_svg  # noqa: E402
from nomai.vision import CANONICAL, _DSU, _resid_fixed, procrustes  # noqa: E402

SPIKE_GIDS = {gid for gid, parts in CANONICAL.items()
              if any(len(p[0]) == 2 and not p[1] for p in parts)}

SPIKE_TABLE = {}
for gid, parts in CANONICAL.items():
    sp = [p for p in parts if len(p[0]) == 2 and not p[1]]
    if not sp:
        continue
    body = [p for p in parts if not (len(p[0]) == 2 and not p[1])]
    sig = tuple(sorted((len(pts), cl) for pts, cl in body))
    SPIKE_TABLE.setdefault(sig, []).append((body[0], sp[0][0]))


def core_fit(body_strokes):
    """Best residual and scale of the cluster's body against any canonical part."""
    best = (math.inf, 1.0)
    for st in body_strokes:
        for parts in CANONICAL.values():
            for pts, closed in parts:
                if len(pts) != len(st.points) or closed != st.closed:
                    continue
                for r in (range(len(pts)) if closed else [0]):
                    fit = procrustes(pts[r:] + pts[:r], st.points)
                    if fit and fit[2] < best[0]:
                        best = (fit[2], fit[0])
    return best


def spike_resid(body_strokes, stroke):
    sig = tuple(sorted((len(s.points), s.closed) for s in body_strokes))
    best = math.inf
    for (core_pts, core_closed), spike_pts in SPIKE_TABLE.get(sig, []):
        for bs in body_strokes:
            if len(bs.points) != len(core_pts) or bs.closed != core_closed:
                continue
            for r in (range(len(core_pts)) if core_closed else [0]):
                fit = procrustes(core_pts[r:] + core_pts[:r], bs.points)
                if fit is None:
                    continue
                scale, theta, _res, _sh = fit
                w = complex(math.cos(theta), math.sin(theta)) * scale
                for pts in (stroke.points, stroke.points[::-1]):
                    best = min(best, _resid_fixed(w, spike_pts, pts))
    return best


SVG = ROOT / "data" / "svg"
manifest = json.loads((SVG / "manifest.json").read_text(encoding="utf-8"))
rows = []
for entry in manifest:
    want = Observation.from_grid(
        grid_from_message(entry["message"], entry["base"], UPSTREAM)
    )
    n_spikes = sum(1 for g in want.glyphs.values() if g in SPIKE_GIDS)

    strokes, _ = parse_svg(SVG / entry["file"])
    two = [i for i, s in enumerate(strokes) if len(s.points) == 2]
    body = [i for i, s in enumerate(strokes) if len(s.points) > 2]
    owner = defaultdict(list)
    for i in body:
        for p in strokes[i].points:
            owner[p].append(i)
    dsu = _DSU(len(strokes))
    for idxs in owner.values():
        for a in idxs[1:]:
            dsu.union(idxs[0], a)
    groups = defaultdict(list)
    for i in body:
        groups[dsu.find(i)].append(strokes[i])
    home = {p: dsu.find(i) for i in body for p in strokes[i].points}

    jitter = statistics.median([core_fit(g)[0] for g in groups.values()] or [0.0])
    cand = []
    for i in two:
        a, b = strokes[i].points
        for h in {x for x in (home.get(a), home.get(b)) if x is not None}:
            r = spike_resid(groups[h], strokes[i])
            if r < math.inf:
                cand.append(r)
    cand.sort()
    if len(cand) <= n_spikes or n_spikes == 0:
        continue
    rows.append((entry["handwriting"], entry["base"], n_spikes, jitter,
                 cand[n_spikes - 1], cand[n_spikes]))

print(f"{'hw':>4} {'n':>4} {'jitter':>8} {'last spike':>11} {'first other':>12} "
      f"{'gap':>8} {'last/jitter':>12}")
print("-" * 66)
for hw in (0.0, 0.3, 0.6):
    sub = [r for r in rows if r[0] == hw]
    for _hw, _b, n, j, last, nxt in sorted(sub, key=lambda r: -r[4])[:6]:
        ratio = last / j if j > 1e-9 else float("inf")
        print(f"{hw:>4} {n:>4} {j:>8.2f} {last:>11.2f} {nxt:>12.2f} "
              f"{nxt - last:>8.2f} {ratio:>12.1f}")
    if sub:
        print(f"     -> worst 'last spike' at hw={hw}: "
              f"{max(r[4] for r in sub):.2f}   "
              f"lowest 'first other': {min(r[5] for r in sub):.2f}")
