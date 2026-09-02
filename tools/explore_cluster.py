"""Two structural shortcuts, checked before building on them.

1. A glyph's annotation is built from its core's vertices, and `handwrite` perturbs
   shared points through one `point_map` -- so the strokes of a single glyph should
   share *exactly equal* coordinates. If so, clustering needs no distance threshold.
   (Glyph 33's pentagon annotation is the exception: it is positioned, not derived.)

2. A connection joins two different clusters; a spike annotation stays inside one.
   That separates the two-point strokes without relying on a length cutoff.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.svgparse import parse_svg  # noqa: E402

TRUTH = json.loads(
    (ROOT / "data" / "truth" / "hello_base200000.json").read_text(encoding="utf-8")
)


class DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, i, j):
        self.p[self.find(i)] = self.find(j)


for sample in sorted((ROOT / "assets" / "samples").glob("*.svg")):
    strokes, circles = parse_svg(sample)
    print(f"\n=== {sample.name}")

    # Connection endpoints are themselves glyph vertices, so they chain every glyph
    # into one component. Hold the two-point strokes out of the merge and assign
    # them afterwards by which components their endpoints land in.
    two = [i for i, st in enumerate(strokes) if len(st.points) == 2]
    body = [i for i, st in enumerate(strokes) if len(st.points) > 2]

    owner = defaultdict(list)
    for idx in body:
        for p in strokes[idx].points:
            owner[p].append(idx)
    dsu = DSU(len(strokes))
    for p, idxs in owner.items():
        for a in idxs[1:]:
            dsu.union(idxs[0], a)

    groups = defaultdict(list)
    for idx in body:
        groups[dsu.find(idx)].append(idx)
    print(f"  glyph clusters from strokes with >2 points: {len(groups)}")
    print(f"    cluster sizes: {sorted((len(v) for v in groups.values()), reverse=True)}")

    # where does each vertex live?
    home = {}
    for root, idxs in groups.items():
        for idx in idxs:
            for p in strokes[idx].points:
                home[p] = root

    # A spike tip is a brand new point, and a connection may land *on* a spike tip,
    # so an exact vertex lookup leaves both cases unresolved. Fall back to the
    # nearest cluster centroid: a spike stays inside its own glyph, a connection
    # reaches across to another one.
    centroid = {}
    for root, idxs in groups.items():
        pts = [p for idx in idxs for p in strokes[idx].points]
        centroid[root] = (sum(x for x, _ in pts) / len(pts),
                          sum(y for _, y in pts) / len(pts))

    def where(pt):
        if pt in home:
            return home[pt]
        return min(centroid,
                   key=lambda r: (centroid[r][0] - pt[0]) ** 2
                   + (centroid[r][1] - pt[1]) ** 2)

    spikes, conns = [], []
    for i in two:
        a, b = strokes[i].points
        (spikes if where(a) == where(b) else conns).append(i)
    print(f"  two-point strokes: {len(two)} -> {len(conns)} connections, "
          f"{len(spikes)} spikes")
    print(f"    spike lengths:      {[round(strokes[i].length, 1) for i in spikes]}")
    print(f"    connection lengths: {sorted(round(strokes[i].length, 1) for i in conns)}")

    n_glyphs = len(TRUTH["grid"]["glyphs"])
    n_conn = len(TRUTH["grid"]["connections"])
    print(f"  truth for this message: {n_glyphs} glyphs, {n_conn} connections")
