"""SVG drawing -> Observation, without any machine learning.

The samples are vector data, not pixels, so "recognition" here is parsing plus a
closed-form geometric fit. Three properties of `draw` make it tractable:

* `handwrite` perturbs shared points through one `point_map`, so the strokes of a
  glyph -- and the endpoints of a connection -- carry *bit-identical* coordinates.
  Clustering and vertex lookup need no tolerance at all.
* the SVG preserves vertex order, so matching a stroke to a canonical PolySpec is an
  ordered Procrustes fit (closed form), not unordered point-set matching.
* connections only ever join column i to column i+1, so the connection graph is
  layered and a BFS from the innermost glyph recovers the column index exactly.
"""
import math
from collections import defaultdict, deque
from itertools import permutations, product
from dataclasses import dataclass, field

from .glyphs import KNOWN_GLYPHS
from .gridgen import K, MIDLINE, ROWS, j_choices
from .svgparse import Stroke, parse_svg

Point = tuple[float, float]


@dataclass
class Cluster:
    """One glyph: its strokes, before identification."""

    strokes: list[Stroke] = field(default_factory=list)

    @property
    def points(self) -> list[Point]:
        return [p for s in self.strokes for p in s.points]

    @property
    def centroid(self) -> Point:
        pts = self.points
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    @property
    def signature(self) -> tuple:
        return tuple(sorted((len(s.points), s.closed) for s in self.strokes))


class _DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, i, j):
        self.p[self.find(i)] = self.find(j)


def _spike_table():
    """Body signature -> the glyphs that can carry a spike, and where it goes.

    Only two body shapes in the alphabet can: a single four-point open line and a
    closed pentagon. Every other cluster is structurally forbidden from owning a
    two-point stroke, which settles most of the drawing for free.
    """
    table = {}
    for gid, parts in CANONICAL.items():
        spikes = [p for p in parts if len(p[0]) == 2 and not p[1]]
        if not spikes:
            continue
        body = [p for p in parts if not (len(p[0]) == 2 and not p[1])]
        sig = tuple(sorted((len(pts), cl) for pts, cl in body))
        table.setdefault(sig, []).append((body[0], spikes[0][0]))
    return table


_SPIKE_TABLE = None


def _spike_table_cached():
    global _SPIKE_TABLE  # CANONICAL is defined below; build on first use
    if _SPIKE_TABLE is None:
        _SPIKE_TABLE = _spike_table()
    return _SPIKE_TABLE


def spike_residual(body_strokes, stroke) -> float:
    """How well a two-point stroke fits as this glyph's spike; inf if impossible.

    Fit the body to the canonical core, push the canonical spike through the same
    similarity, and measure. The spike's own jitter translation is left free, since
    `handwrite` draws one per PolySpec rather than one per glyph.
    """
    sig = tuple(sorted((len(s.points), s.closed) for s in body_strokes))
    best = math.inf
    for (core_pts, core_closed), spike_pts in _spike_table_cached().get(sig, []):
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


def layering(clusters_sig, connections):
    """Column index per cluster, or None if these connections cannot be a drawing.

    Connections only ever run between consecutive columns, both paths start in the
    same cell, and a column holds at most two glyphs. Rooting the BFS anywhere else
    breaks one of those, so this doubles as a validity test -- which is what lets the
    spike count be inferred instead of guessed.
    """
    adj = defaultdict(set)
    for ka, _, kb, _ in connections:
        if ka == kb:
            return None
        adj[ka].add(kb)
        adj[kb].add(ka)
    for root in clusters_sig:
        dist = _bfs(adj, root)
        if len(dist) != len(clusters_sig):
            continue
        cols = {k: v + 1 for k, v in dist.items()}
        n = max(cols.values())
        sizes = [sum(1 for c in cols.values() if c == i) for i in range(1, n + 1)]
        if sizes[0] != 1 or max(sizes) > 2:
            continue
        if any(abs(cols[ka] - cols[kb]) != 1 for ka, _, kb, _ in connections):
            continue
        return cols
    return None


def decompose(strokes: list[Stroke]):
    """Split strokes into glyph clusters and connection lines.

    Strokes of three points or more are glyph parts, grouped by *exact* shared
    coordinates -- annotations are built from core vertices and `handwrite` perturbs
    shared points through one map, so no distance threshold is needed.

    Two-point strokes are the hard part: a spike annotation and a connection line are
    the same shape. Measurement (tools/calibrate_spike.py) says the two populations
    *overlap* in fit residual -- at handwriting 0.3 the worst real spike scores 2.03
    while the best non-spike scores 0.89 -- so no cutoff separates them, adaptive or
    otherwise. What the same measurement shows is that ranking by residual is
    perfect: across 60 drawings the real spikes were always exactly the lowest N.

    So rank, and let the drawing itself supply N. Taking one spike too many steals a
    real connection, and the connection graph stops being a layered chain; taking one
    too few leaves a stroke that spans no columns. Scanning N from the top down and
    keeping the first arrangement that still forms a valid layering turns a threshold
    problem into a search with an exact test.
    """
    two = [i for i, s in enumerate(strokes) if len(s.points) > 1 and len(s.points) == 2]
    body = [i for i, s in enumerate(strokes) if len(s.points) > 2]

    owner: dict[Point, list[int]] = defaultdict(list)
    for i in body:
        for p in strokes[i].points:
            owner[p].append(i)
    dsu = _DSU(len(strokes))
    for idxs in owner.values():
        for a in idxs[1:]:
            dsu.union(idxs[0], a)

    base_strokes: dict[int, list[Stroke]] = {}
    for i in body:
        base_strokes.setdefault(dsu.find(i), []).append(strokes[i])

    keys = list(base_strokes)
    centroids = {
        k: (
            sum(p[0] for st in v for p in st.points)
            / sum(len(st.points) for st in v),
            sum(p[1] for st in v for p in st.points)
            / sum(len(st.points) for st in v),
        )
        for k, v in base_strokes.items()
    }
    home = {p: dsu.find(i) for i in body for p in strokes[i].points}
    canonical = set(SIGNATURE.values())

    def nearest(pt: Point) -> int:
        return min(
            keys,
            key=lambda k: (centroids[k][0] - pt[0]) ** 2
            + (centroids[k][1] - pt[1]) ** 2,
        )

    # rank every plausible (stroke, host) pairing, best fit first
    ranked = []
    for i in two:
        a, b = strokes[i].points
        for h in {x for x in (home.get(a), home.get(b)) if x is not None}:
            r = spike_residual(base_strokes[h], strokes[i])
            if r < math.inf:
                ranked.append((r, i, h))
    ranked.sort()
    chain, used_stroke, used_host = [], set(), set()
    for r, i, h in ranked:
        if i in used_stroke or h in used_host:
            continue
        chain.append((i, h))
        used_stroke.add(i)
        used_host.add(h)

    def build(n_spikes):
        roots = {k: Cluster(list(v)) for k, v in base_strokes.items()}
        spiked = set()
        for i, h in chain[:n_spikes]:
            roots[h].strokes.append(strokes[i])
            spiked.add(i)
        if any(cl.signature not in canonical for cl in roots.values()):
            return None
        owned = {p: k for k, cl in roots.items() for st in cl.strokes for p in st.points}
        conns = []
        for i in two:
            if i in spiked:
                continue
            a, b = strokes[i].points
            if a not in owned or b not in owned:
                # a connection always ends on a glyph vertex, so a loose end means a
                # spike is still sitting in the connection pile -- this n is too low
                return None
            conns.append((owned[a], a, owned[b], b))
        return roots, conns

    # Scan upward and stop at the first arrangement that works. Too few spikes leaves
    # a connection endpoint nobody owns; too many steals a real connection. Scanning
    # downward instead accepts over-assignment, because when the two paths merge the
    # graph carries cycles and losing a redundant edge still layers fine.
    for n in range(len(chain) + 1):
        built = build(n)
        if built and layering({k: None for k in built[0]}, built[1]) is not None:
            return built
    fallback = {k: Cluster(list(v)) for k, v in base_strokes.items()}
    owned = {p: k for k, cl in fallback.items() for st in cl.strokes for p in st.points}
    return fallback, [
        (owned.get(strokes[i].points[0]) or nearest(strokes[i].points[0]),
         strokes[i].points[0],
         owned.get(strokes[i].points[1]) or nearest(strokes[i].points[1]),
         strokes[i].points[1])
        for i in two
    ]


def _bfs(adj, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in dist:
                dist[v] = dist[u] + 1
                q.append(v)
    return dist


def column_index(clusters, connections) -> dict[int, int]:
    """1-based column for every cluster, from the connection graph.

    Connections only run between consecutive columns, so BFS distance from the
    column-1 glyph is the column offset. Finding that glyph is the whole problem:
    the two paths share only their starting cell and never link to each other, so
    the graph is typically a simple *path* with column 1 in the middle, not at an
    end. Rooting at an end silently turns 7 columns into 13.

    So every cluster is tried as root and filtered on two facts that hold by
    construction -- column 1 holds exactly one glyph (both paths start at
    STARTING_POINT) and no column holds more than two -- then the survivors are
    ordered by whether column spacing grows along the chain. Spacing tracks glyph
    scale, which climbs from 1 to 2 as the spiral winds outward, so growth is the
    reading direction; rooting at an end instead makes spacing fall and then rise.
    """
    adj = defaultdict(set)
    for ka, _, kb, _ in connections:
        adj[ka].add(kb)
        adj[kb].add(ka)

    cents = {k: c.centroid for k, c in clusters.items()}
    best = None
    for root in clusters:
        dist = _bfs(adj, root)
        if len(dist) != len(clusters):
            continue
        cols = {k: v + 1 for k, v in dist.items()}
        n = max(cols.values())
        sizes = [sum(1 for c in cols.values() if c == i) for i in range(1, n + 1)]
        if sizes[0] != 1 or max(sizes) > 2:
            continue
        if any(abs(cols[ka] - cols[kb]) != 1 for ka, _, kb, _ in connections):
            continue
        means = []
        for i in range(1, n + 1):
            pts = [cents[k] for k, c in cols.items() if c == i]
            means.append(
                (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
            )
        gaps = [math.dist(means[i], means[i + 1]) for i in range(len(means) - 1)]
        rising = sum(1 for a, b in zip(gaps, gaps[1:]) if b > a)
        score = (rising - (len(gaps) - 1 - rising), -n)
        if best is None or score > best[0]:
            best = (score, cols)

    if best is None:
        raise ValueError("no cluster works as a column-1 glyph")
    return best[1]


def procrustes(src, dst):
    """Best similarity src -> dst with correspondence given.

    A planar similarity is multiplication by a complex number, so this is one
    least-squares solve: no iteration, no initial guess.
    """
    n = len(src)
    a = [complex(*p) for p in src]
    b = [complex(*p) for p in dst]
    ma, mb = sum(a) / n, sum(b) / n
    a = [z - ma for z in a]
    b = [z - mb for z in b]
    denom = sum(abs(z) ** 2 for z in a)
    if denom == 0:
        return None
    w = sum(bz * az.conjugate() for az, bz in zip(a, b)) / denom
    resid = math.sqrt(sum(abs(bz - w * az) ** 2 for az, bz in zip(a, b)) / n)
    return abs(w), math.atan2(w.imag, w.real), resid, mb - w * ma


def canonical_parts(gid: int):
    g = KNOWN_GLYPHS[gid - 1]
    parts = [(g.core.points, g.core.close)]
    if g.annotation is not None:
        parts.append((g.annotation.points, g.annotation.close))
    return parts


CANONICAL = {gid: canonical_parts(gid) for gid in range(1, len(KNOWN_GLYPHS) + 1)}
SIGNATURE = {
    gid: tuple(sorted((len(pts), cl) for pts, cl in parts))
    for gid, parts in CANONICAL.items()
}


def _assignments(cluster_strokes, parts):
    """Ways to pair a cluster's strokes with a canonical glyph's parts."""
    n = len(parts)
    if n != len(cluster_strokes):
        return
    for perm in permutations(range(n)):
        if all(
            len(cluster_strokes[perm[i]].points) == len(parts[i][0])
            and cluster_strokes[perm[i]].closed == parts[i][1]
            for i in range(n)
        ):
            yield perm


def _resid_fixed(w: complex, src, dst) -> float:
    """Residual of src -> dst under a *given* similarity, translation free."""
    n = len(src)
    a = [complex(*p) for p in src]
    b = [complex(*p) for p in dst]
    ma, mb = sum(a) / n, sum(b) / n
    return math.sqrt(
        sum(abs((bz - mb) - w * (az - ma)) ** 2 for az, bz in zip(a, b)) / n
    )


@dataclass(frozen=True)
class Fit:
    resid: float
    gid: int
    scale: float
    theta: float
    perm: tuple          # cluster stroke index -> canonical part index
    rots: tuple          # cyclic start offset chosen for each canonical part
    origin: Point        # where the glyph's local origin landed on the page

    def __lt__(self, other):
        return self.resid < other.resid


def fit_cluster(cluster: Cluster) -> list[Fit]:
    """Fit a glyph to every candidate, best residual first.

    Geometry comes from the *core* alone. `handwrite` draws its jitter translation
    once per PolySpec rather than once per glyph, so a glyph's annotation sits a
    fraction of a unit from where a single shared similarity would put it -- small,
    but enough to spoil a joint fit and throw the scale off by the width of a whole
    column. The annotation is therefore scored under the core's similarity with its
    own translation free, which is exactly how it was drawn.
    """
    out: list[Fit] = []
    sig = cluster.signature
    for gid, parts in CANONICAL.items():
        if SIGNATURE[gid] != sig:
            continue
        for perm in _assignments(cluster.strokes, parts):
            core_pts, core_closed = parts[0]
            for r in (range(len(core_pts)) if core_closed else [0]):
                src = core_pts[r:] + core_pts[:r]
                fit = procrustes(src, cluster.strokes[perm[0]].points)
                if fit is None:
                    continue
                scale, theta, resid, shift = fit
                w = complex(math.cos(theta), math.sin(theta)) * scale
                rots = [r]
                total = resid
                for pi in range(1, len(parts)):
                    pts, closed = parts[pi]
                    obs = cluster.strokes[perm[pi]].points
                    best_rr, best_res = 0, math.inf
                    for rr in (range(len(pts)) if closed else [0]):
                        res = _resid_fixed(w, pts[rr:] + pts[:rr], obs)
                        if res < best_res:
                            best_rr, best_res = rr, res
                    rots.append(best_rr)
                    total += best_res
                out.append(Fit(total, gid, scale, theta, tuple(perm), tuple(rots),
                               (shift.real, shift.imag)))
    out.sort()
    return out


def vertex_map(cluster: Cluster, fit: Fit) -> dict[Point, int]:
    """Drawn coordinate -> index into the canonical glyph's `allpoints`.

    Connection endpoints are bit-identical to the glyph vertices they attach to, so
    this lookup is exact -- no nearest-vertex search, no tolerance.
    """
    parts = CANONICAL[fit.gid]
    base = 0
    out: dict[Point, int] = {}
    for pi, (pts, _) in enumerate(parts):
        r = fit.rots[pi]
        order = list(range(r, len(pts))) + list(range(r))
        obs = cluster.strokes[fit.perm[pi]].points
        for slot, canon_idx in enumerate(order):
            out.setdefault(obs[slot], base + canon_idx)
        base += len(pts)
    return out


def _angdiff(a: float, b: float) -> float:
    return abs(math.atan2(math.sin(a - b), math.cos(a - b)))


def column_rotation(fits_in_column: list[list[Fit]], offset=None,
                    margin: float = 1.0) -> float:
    """The rotation shared by every glyph in a column.

    Glyph fits alone are not enough. A glyph pins the angle only up to its own
    confusable set (60/72/90/180 degrees apart), and when both glyphs in a column
    come from the same family, rotating the whole column by 90 degrees and relabelling
    both glyphs is exactly as consistent -- a degeneracy no amount of cross-checking
    between them can break.

    The geometry breaks it. `transform` offsets a glyph from the bottom line along
    `(-sin, cos)` of the very same angle, so when a column holds two glyphs the
    direction of the line between their centres *is* the rotation, independent of
    which glyphs they are. That fixes it modulo 180 degrees, and the glyph fits pick
    the half.
    """
    def cost(angle):
        return sum(
            min(_angdiff(f.theta, angle) for f in fits if f.resid <= fits[0].resid + margin)
            for fits in fits_in_column
        )

    if offset is not None:
        dx, dy = offset
        base = math.atan2(-dx, dy)
        return min((base, base + math.pi), key=cost)

    seeds = [
        f.theta for fits in fits_in_column for f in fits
        if f.resid <= fits[0].resid + margin
    ]
    return min(seeds, key=cost) if seeds else 0.0


def _bl(center: Point, j: int, row_gap: float, u: Point) -> Point:
    """The bottom-line point a glyph implies, given its row.

    transform() places a glyph at `bottomline + (j - ROWS) * 3K * scale_here * u`,
    so undoing the row offset recovers a point on the spiral itself. Every glyph in
    a column must imply the same one, and the sequence must stay smooth.
    """
    d = (j - ROWS) * row_gap
    return (center[0] - d * u[0], center[1] - d * u[1])


def _row_states(n_members: int, dj: int):
    if n_members == 1:
        return [(j, j) for j in range(1, ROWS + 1)]
    if dj >= 2:
        return [(1, ROWS)]
    return [(1, 2), (2, 3)]


def assign_rows(columns, centers, thetas, ncols):
    """Rows for every glyph, by dynamic programming over the columns.

    Within a column the *gap* between two glyphs gives their row difference
    outright, but not the absolute rows. Column 1 anchors it -- both paths start at
    STARTING_POINT, so it is row MIDLINE -- and from there each column is
    constrained by path continuity (a path moves at most one row per column) and
    scored by how smoothly the implied bottom line continues. Guessing a row wrong
    displaces that line by a full row gap, which dwarfs the spiral's own curvature.
    """
    delta = 1 / (ncols - 1) if ncols > 1 else 0.0
    per_col, gaps, us = {}, {}, {}
    for i in range(1, ncols + 1):
        scale_here = 1 + (i - 1) * delta
        gaps[i] = 3 * K * scale_here
        us[i] = (-math.sin(thetas[i]), math.cos(thetas[i]))
        members = [k for k, c in columns.items() if c == i]
        members.sort(key=lambda k: centers[k][0] * us[i][0] + centers[k][1] * us[i][1])
        per_col[i] = members

    states = {1: [(MIDLINE, MIDLINE)]}
    for i in range(2, ncols + 1):
        members = per_col[i]
        if len(members) == 1:
            dj = 0
        else:
            lo, hi = centers[members[0]], centers[members[1]]
            proj = (hi[0] - lo[0]) * us[i][0] + (hi[1] - lo[1]) * us[i][1]
            dj = max(1, round(proj / gaps[i]))
        states[i] = _row_states(len(members), dj)

    def reachable(prev, cur):
        (a, b), (c, d) = prev, cur
        return (c in j_choices(a) and d in j_choices(b)) or (
            d in j_choices(a) and c in j_choices(b)
        )

    def bl_of(i, state):
        return _bl(centers[per_col[i][0]], state[0], gaps[i], us[i])

    def step_cost(i, prev, cur):
        """How far the bottom line strays sideways between two columns.

        The bottom line is the spiral, so from one column to the next it advances
        essentially along the tangent -- and the tangent is the column rotation,
        which the glyph offsets already gave us. Its sideways component is therefore
        near zero for the right rows, while getting a row wrong displaces the line by
        a whole row gap. Second differences of position, which is what this used to
        score, are blind to a row error that persists over several columns.
        """
        p0, p1 = bl_of(i - 1, prev), bl_of(i, cur)
        d = (p1[0] - p0[0], p1[1] - p0[1])
        sx = (math.sin(thetas[i - 1]) + math.sin(thetas[i])) / 2
        cy = (math.cos(thetas[i - 1]) + math.cos(thetas[i])) / 2
        norm = math.hypot(sx, cy) or 1.0
        u = (-sx / norm, cy / norm)
        return abs(d[0] * u[0] + d[1] * u[1]) / gaps[i]

    best = {states[1][0]: (0.0, None)}
    trace = []
    for i in range(2, ncols + 1):
        nxt = {}
        for prev, (cost, _) in best.items():
            for cur in states[i]:
                if not reachable(prev, cur):
                    continue
                total = cost + step_cost(i, prev, cur)
                if cur not in nxt or total < nxt[cur][0]:
                    nxt[cur] = (total, prev)
        if not nxt:
            raise ValueError(f"no row assignment survives at column {i}")
        trace.append(nxt)
        best = nxt

    chain = {}
    cur = min(best, key=lambda s: best[s][0])
    for i in range(ncols, 1, -1):
        chain[i] = cur
        cur = trace[i - 2][cur][1]
    chain[1] = states[1][0]

    rows = {}
    for i in range(1, ncols + 1):
        lo, hi = chain[i]
        members = per_col[i]
        rows[members[0]] = lo
        rows[members[-1]] = hi
    return rows, per_col


def solve_rotations(columns, centers, fits, ncols, turn_weight: float = 3.0):
    """The drawing rotation of every column.

    Two independent sources, neither sufficient alone:

    * A column holding two glyphs gives the angle from the direction between their
      origins, independent of which glyphs they are -- but only modulo 180 degrees.
      Resolving that per column from the glyph fits cannot work, because glyphs 1/3,
      8/10, 13/15 and 29/31 are each other rotated by exactly 180.
    * A glyph fit gives the angle modulo its own confusable family (60, 72, 90 or
      180 degrees), and the residual says how well it really fits.

    What ties them together is the spiral: its tangent turns gradually, so the true
    sequence is smooth. This picks one candidate per column by shortest path,
    trading fit residual against how sharply the angle would have to turn. Columns
    where both paths merged offer no geometric anchor at all -- some drawings have
    none anywhere -- and there smoothness plus residual carries the whole load.

    Angles are accumulated unwrapped. Interpolating wrapped ones puts the midpoint of
    176 and -145 degrees at 16 rather than 196, which is a clean 180-degree error in
    every single-glyph column.
    """
    members = {
        i: [k for k, c in columns.items() if c == i] for i in range(1, ncols + 1)
    }

    def fit_cost(i, angle):
        total = 0.0
        for k in members[i]:
            cands = fits[k]
            near = [f for f in cands if f.resid <= cands[0].resid + 1.0]
            total += min(f.resid + 2.0 * _angdiff(f.theta, angle) for f in near)
        return total

    options = {}
    for i in range(1, ncols + 1):
        ms = members[i]
        if len(ms) == 2:
            (ax, ay), (bx, by) = centers[ms[0]], centers[ms[1]]
            base = math.atan2(-(bx - ax), by - ay)
            angles = [base, base + math.pi]
        else:
            seen, angles = [], []
            cands = fits[ms[0]]
            for f in cands:
                if f.resid <= cands[0].resid + 1.0 and all(
                    _angdiff(f.theta, a) > 0.02 for a in seen
                ):
                    seen.append(f.theta)
                    angles.append(f.theta)
        options[i] = [(a, fit_cost(i, a)) for a in angles] or [(0.0, 0.0)]

    # shortest path over the columns, unwrapping as we go
    best = {a: (c, None, a) for a, c in options[1]}
    trace = []
    for i in range(2, ncols + 1):
        nxt = {}
        for a, c in options[i]:
            for prev_a, (pc, _, prev_un) in best.items():
                delta = math.atan2(math.sin(a - prev_un), math.cos(a - prev_un))
                total = pc + c + turn_weight * abs(delta)
                if a not in nxt or total < nxt[a][0]:
                    nxt[a] = (total, prev_a, prev_un + delta)
        trace.append(nxt)
        best = nxt

    chain = {}
    cur = min(best, key=lambda a: best[a][0])
    for i in range(ncols, 1, -1):
        _cost, prev_a, unwrapped = trace[i - 2][cur]
        chain[i] = unwrapped
        cur = prev_a
    chain[1] = cur  # column 1 is its own unwrapped value
    return chain


def analyze(path) -> "Observation":
    """A NomaiText SVG -> the Observation the replay decoder consumes."""
    from .decode import Observation

    strokes, _circles = parse_svg(path)
    clusters, connections = decompose(strokes)
    fits = {k: fit_cluster(c) for k, c in clusters.items()}
    empty = [k for k, f in fits.items() if not f]
    if empty:
        raise ValueError(f"{len(empty)} cluster(s) match no known glyph")

    adj = defaultdict(set)
    for ka, _, kb, _ in connections:
        adj[ka].add(kb)
        adj[kb].add(ka)
    root = min(clusters, key=lambda k: fits[k][0].scale)
    columns = {k: d + 1 for k, d in _bfs(adj, root).items()}
    if len(columns) != len(clusters):
        raise ValueError("connection graph is not connected")
    ncols = max(columns.values())

    # Where the glyph sits is its fitted local *origin*, not the centroid of its
    # ink: `transform` translates the origin onto the page, and a glyph's canonical
    # points are not centred on it -- a three-point hexagon arc sits tens of units
    # off. That bias is the same order as a row gap, which is enough to misread a row.
    centers = {k: fits[k][0].origin for k in clusters}
    thetas = solve_rotations(columns, centers, fits, ncols)

    chosen = {}
    for k, cands in fits.items():
        near = [f for f in cands if f.resid <= cands[0].resid + 1.0]
        chosen[k] = min(near, key=lambda f: (_angdiff(f.theta, thetas[columns[k]]), f.resid))

    rows, _per_col = assign_rows(columns, centers, thetas, ncols)

    coord = {k: (columns[k], rows[k]) for k in clusters}
    glyphs = {coord[k]: chosen[k].gid for k in clusters}

    paths = [[], []]
    for i in range(1, ncols + 1):
        js = sorted(rows[k] for k in clusters if columns[k] == i)
        paths[0].append((i, js[0]))
        paths[1].append((i, js[-1]))

    vmaps = {k: vertex_map(clusters[k], chosen[k]) for k in clusters}
    conns = {}
    for ka, pa, kb, pb in connections:
        if columns[ka] > columns[kb]:
            ka, pa, kb, pb = kb, pb, ka, pa
        ga = KNOWN_GLYPHS[chosen[ka].gid - 1].allpoints
        gb = KNOWN_GLYPHS[chosen[kb].gid - 1].allpoints
        conns[(coord[ka], coord[kb])] = (ga[vmaps[ka][pa]], gb[vmaps[kb][pb]])

    return Observation(glyphs=glyphs, paths=paths, connections=conns)
