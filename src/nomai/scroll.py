"""A scroll: one drawing holding a conversation.

A scroll is a root spiral and the replies hanging off it, drawn on one sheet. Only the
root is plugged into the wall, so a scroll has exactly one socket however many replies
it holds -- which is why a reply is not marked with a triangle. It is joined to the
spiral it answers by an ordinary connection line with one bead at its midpoint.

The bead is what makes reading a scroll possible without guessing. Nothing else in a
drawing puts a dot in the middle of a two-point stroke: connections dot their ends,
glyphs dot their vertices. So cutting the beaded lines separates the spirals cleanly,
and the ordinary reader then runs on each one completely unchanged.

This mirrors the JavaScript in web/index.html and web/read.js, which is the version
people actually use. The two are kept in step deliberately: this one is the reference,
and it is where a claim about the format gets checked.
"""
import math
from dataclasses import dataclass, field

from .decode import Observation
from .glyphs import KNOWN_GLYPHS
from .render import GLYPH_K as K
from .render import GRID_ROWS as ROWS
from .render import (
    MAX_SCALE,
    SOCKET_R,
    SPIRAL_B,
    SpiralLayout,
    _dot,
    _polyline,
    document,
    spiral_elements,
)
from .svgparse import parse_svg
from .vision import observe_all

Point = tuple[float, float]


@dataclass
class Spiral:
    """One spiral in a scroll: what it says, who said it, and what it answers."""

    grid: object
    parent: int | None = None


@dataclass
class Placement:
    layout: SpiralLayout
    shift: Point
    gap: float = 0.0
    spiral: Spiral | None = None
    seed: int = 47
    # whether this placement was checked and came back; False means it was the best
    # looking of a bad set and shipped on hope
    verified: bool = False
    elements: list = field(default_factory=list)
    drawn: dict = field(default_factory=dict)


# Where along the parent to try, how far out to stand, and what a change of hand or
# coil costs. A reply may wind the other way or coil differently -- a real wall has
# both -- and that is free at the reading end, because every spiral is read on its own
# and the fit recovers winding and tightness for each independently.
SPOTS = (0.92, 0.78, 0.64, 0.5, 0.36, 0.22, 0.99, 0.1)
REACH = (1.0, 1.5, 2.2, 3.2)
# The hand a spiral is written in. Nobody can tell which one was used, so it is free
# to change, and it turns out to matter: for a few grids one jitter pattern moves a
# point far enough that the reader loses the drawing while the next pattern is fine.
# Same bargain as the nonce search in `write` -- try until the output reads.
SEEDS = 8
SEED_STEP = 7919
# The root's angle is free too: the whole scroll turns about its socket, so leaning it
# a little costs nothing and gives a stubborn root somewhere else to stand.
NUDGES = (0.0, 0.21, -0.21, 0.42, -0.42, 0.84, -0.84)
# Angles to re-lay the whole scroll at when a reply could not be placed readably.
# Kept short: each one lays the scroll again, which is the expensive part.
RELAY = (0.35, -0.35, 0.9, -0.9)
PAY_FLIP, PAY_TIGHT = 0.1, 0.04
WANT_ROOM = 6.0


def _tights(b: float) -> list[float]:
    out = [b, min(0.6, b * 1.4), max(0.15, b * 0.72)]
    return list(dict.fromkeys(out))


def attach(parent: Placement, t: float, side: int, reach: float,
           flip: int, tight: float, child_ncols: int) -> Placement:
    """Put a child's tail on its parent at fraction `t`, standing `reach` clear.

    Which way is away from the parent is the normal pointing away from the centre it
    winds into; `side` picks one of the two, so several replies to the same spiral fan
    to alternate sides instead of piling up on one.
    """
    p = parent.layout.point_at(t, 2)
    cx, cy = parent.layout.centre
    out = 1 if (p["x"] - cx) * p["ux"] + (p["y"] - cy) * p["uy"] >= 0 else -1
    nx, ny = p["ux"] * out * side, p["uy"] * out * side
    # clear of the parent's band and no further: the join should read as a connection,
    # which is a short line, not a tether
    gap = (3 * (ROWS - 1) + 1.5) * K * p["scale"] * reach
    at = (p["x"] + nx * gap + parent.shift[0], p["y"] + ny * gap + parent.shift[1])
    # The child's tail tangent must point back at the parent. `tilt` adds straight to
    # that angle -- it is pi/2 at tilt 0 -- so the whole placement is one translation.
    tilt = math.atan2(-ny, -nx) - math.pi / 2
    return Placement(SpiralLayout(child_ncols, tilt, flip, tight), at, gap)


def centres(grid, layout: SpiralLayout, shift: Point) -> list[Point]:
    """Every glyph's origin -- enough to tell whether two spirals are on top of each
    other without walking every drawn vertex."""
    dx, dy = shift
    out = []
    for coord in grid.glyphs:
        x, y = layout.place(*coord)((0.0, 0.0))
        out.append((x + dx, y + dy))
    return out


def clearance(pts, taken) -> float:
    if not taken:
        return math.inf
    return math.sqrt(min((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                         for p in pts for q in taken))


def choose_spot(laid, parent_idx: int, grid, flip: int, tight: float):
    """Candidate placements for a reply, best first.

    A reply goes anywhere on its parent with room for it, so the spot is the layout's
    problem and not the writer's. This walks the outer end inward -- the turns are
    furthest apart out there, and it is where the parent has just finished speaking.

    Room enough is enough: the reward is capped at `want` and distance is charged for.
    Scoring on clearance alone made the search greedy for space, so a reply that could
    not sit snugly was flung to the far end of the sheet on a long tether.
    """
    parent = laid[parent_idx]
    taken = [q for it in laid for q in centres(it.spiral.grid, it.layout, it.shift)]
    want = WANT_ROOM * K * MAX_SCALE
    ranked = []
    for reach in REACH:
        for tw in _tights(tight):
            for fl in (flip, -flip):
                for t in SPOTS:
                    for side in (1, -1):
                        pl = attach(parent, t, side, reach, fl, tw, grid.ncols)
                        pts = centres(grid, pl.layout, pl.shift)
                        # nothing hangs below the socket: the scroll is plugged into
                        # the wall at its lowest point, and a reply drooping past it
                        # reads as falling off
                        below = max(0.0, max(q[1] for q in pts))
                        pay = (PAY_FLIP if fl != flip else 0.0) \
                            + (PAY_TIGHT if tw != tight else 0.0)
                        score = (min(clearance(pts, taken), want)
                                 - 0.55 * pl.gap - 3 * below - pay * want)
                        ranked.append((score, pl))
    ranked.sort(key=lambda r: -r[0])
    # The shortlist has to be *varied*, not just good. Some grids cannot be read at one
    # winding at all -- no seed, tilt or coil rescues them -- so a shortlist that
    # happens to be eight placements of the same hand leaves such a reply nowhere to
    # go, and it ships unreadable. Keeping the best of every hand and coil alongside
    # the best overall guarantees the option is reachable when verification needs it.
    out, seen = [], set()
    for score, pl in ranked:
        key = (pl.layout.flip, round(pl.layout.b, 3))
        if len(out) < 8 or key not in seen:
            out.append(pl)
            seen.add(key)
        if len(out) >= 14:
            break
    return out


def _same_structure(a: Observation, b: Observation) -> bool:
    return (a.glyphs == b.glyphs
            and [list(p) for p in a.paths] == [list(p) for p in b.paths]
            and set(a.connections) == set(b.connections))


def reads_back(grid, glyphs, handwriting: float, seed: int,
               layout: SpiralLayout) -> bool:
    """Draw this placement on its own and see whether it comes back.

    Letting a reply pick its own coil and hand widens what gets drawn, and for some
    combinations of grid, winding and tightness the reader gets it wrong -- its fit for
    the tightness lands in the wrong minimum and everything after follows. The writer
    is the one who can do something about that, so it checks its own output and moves
    to the next placement if this one does not survive. Same bargain the nonce search
    makes, and it is exact: the recovered structure either matches or it does not.
    """
    els, _ = spiral_elements(grid, glyphs, handwriting, seed, layout)
    vx, vy, w, h = layout.canvas()
    try:
        strokes, _ = parse_svg(document(els, w, h, origin=(vx, vy)))
        want = Observation.from_grid(grid)
        return any(_same_structure(o, want) for o in observe_all(strokes))
    except Exception:  # noqa: BLE001 -- any failure to read is a failure to read
        return False


def _hand(grid, glyphs, handwriting: float, seed0: int, layout: SpiralLayout):
    """A seed this placement reads back at, or None if it never does.

    A drawing with no jitter has only one hand to write in, so there is nothing to
    search: it either reads or it does not.
    """
    if handwriting <= 0:
        return seed0 if reads_back(grid, glyphs, handwriting, seed0, layout) else None
    for k in range(SEEDS):
        s = seed0 + k * SEED_STEP
        if reads_back(grid, glyphs, handwriting, s, layout):
            return s
    return None


def _lay(spirals, tilt0: float, flip: int, tight: float,
         glyphs=None, handwriting: float = 0.0, seed: int = 47, verify: bool = False):
    laid: list[Placement] = []
    for idx, sp in enumerate(spirals):
        seed0 = seed + idx * 101
        if idx == 0:
            # The root was never checked at all, which is how a whole scroll could come
            # out unreadable: the layout may not change its winding or its coil, those
            # being the writer's, but its angle and its hand are nobody's.
            place = Placement(SpiralLayout(sp.grid.ncols, tilt0, flip, tight), (0.0, 0.0))
            place.seed = seed0
            if verify:
                for dt in NUDGES:
                    cand = SpiralLayout(sp.grid.ncols, tilt0 + dt, flip, tight)
                    got = _hand(sp.grid, glyphs, handwriting, seed0, cand)
                    if got is not None:
                        place = Placement(cand, (0.0, 0.0))
                        place.seed = got
                        place.verified = True
                        break
        else:
            cands = choose_spot(laid, sp.parent, sp.grid, flip, tight)
            place = cands[0]
            place.seed = seed0
            if verify:
                for c in cands:
                    got = _hand(sp.grid, glyphs, handwriting, seed0, c.layout)
                    if got is not None:
                        place = c
                        place.seed = got
                        place.verified = True
                        break
        place.spiral = sp
        laid.append(place)
    return laid


def balance_tilt(spirals, flip: int, tight: float) -> float:
    """Turn the whole scroll about its socket so it grows upward.

    That rotation is just the root's own tilt: the layout is anchored on the tail, so
    tilting the root turns everything about the socket, children included. Without it
    a scroll grows off to one side and half the sheet is empty.
    """
    trial = _lay(spirals, 0.0, flip, tight)
    pts = [q for it in trial for q in centres(it.spiral.grid, it.layout, it.shift)]
    if not pts:
        return 0.0
    sx = sum(p[0] for p in pts) / len(pts)
    sy = sum(p[1] for p in pts) / len(pts)
    if sx == 0 and sy == 0:
        return 0.0
    return -math.pi / 2 - math.atan2(sy, sx)


def _nearest_pair(a, b):
    best = None
    for p in a:
        for q in b:
            d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
            if best is None or d < best[0]:
                best = (d, p, q)
    return best


def join_svg(p: Point, q: Point) -> list[str]:
    """The join: an ordinary connection line with one bead at its midpoint."""
    return [_polyline([p, q], False),
            _dot(((p[0] + q[0]) / 2, (p[1] + q[1]) / 2))]


NL = chr(10)


def render_scroll(spirals, glyphs=None, handwriting: float = 0.0, seed: int = 47,
                  flip: int = 1, tight: float = SPIRAL_B) -> str:
    """A list of Spirals -> one SVG holding the whole conversation."""
    glyphs = KNOWN_GLYPHS if glyphs is None else glyphs
    if not spirals:
        raise ValueError("a scroll needs at least one spiral")
    tilt0 = balance_tilt(spirals, flip, tight)
    laid = _lay(spirals, tilt0, flip, tight, glyphs, handwriting, seed, verify=True)
    # The root is settled first, on whether it reads, and the replies then have to fit
    # around whatever it did. If one of them could not find a placement that reads back
    # it has been shipped on hope, and the sheet it was given is the thing to change:
    # lean the root and write it in another hand, and everything downstream moves.
    # Measured over fans, chains and trees of eight to ten spirals this never fires,
    # so it costs nothing where it is not needed -- which is why it is a retry rather
    # than a wider search up front.
    if not all(it.verified for it in laid):
        for k, dt in enumerate(RELAY):
            alt = _lay(spirals, tilt0 + dt, flip, tight, glyphs, handwriting,
                       seed + (k + 1) * SEED_STEP, verify=True)
            if sum(it.verified for it in alt) > sum(it.verified for it in laid):
                laid = alt
            if all(it.verified for it in laid):
                break
    for it in laid:
        it.elements, it.drawn = spiral_elements(
            it.spiral.grid, glyphs, handwriting, it.seed, it.layout, it.shift
        )

    # Grouped by spiral, and every join named, so a reader can put one spiral on the
    # wall without the rest of them -- which is how a conversation is actually found.
    els: list[str] = []
    for idx, it in enumerate(laid):
        els.append(f'<g data-spiral="{idx}">' + NL.join(it.elements) + "</g>")
    # the joins last, so one is never hidden under a glyph
    k = 0
    for idx, it in enumerate(laid):
        if idx == 0:
            continue
        par = laid[it.spiral.parent]
        mine = [p for v in it.drawn.values() for p in v]
        theirs = [p for v in par.drawn.values() for p in v]
        _, a, b = _nearest_pair(theirs, mine)
        els.append(f'<g data-join="{k}">' + NL.join(join_svg(a, b)) + "</g>")
        k += 1

    xs = [p[0] for it in laid for v in it.drawn.values() for p in v]
    ys = [p[1] for it in laid for v in it.drawn.values() for p in v]
    m = 8 * K * MAX_SCALE
    r = SOCKET_R * K * MAX_SCALE
    w = 2 * max(max(xs) + m, m - min(xs))
    y = min(ys) - m
    h = (max(max(ys), 0.0) + 2.2 * r + 0.4 * m) - y
    return document(els, w, h, origin=(-w / 2, y))


# --------------------------------------------------------------- reading one back

def _key(p: Point) -> str:
    return f"{p[0]},{p[1]}"


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


def split_scroll(strokes, dots, eps: float = 0.05):
    """Cut the beaded joins, and what is left is one group per spiral.

    Groups come back in document order -- by the index of their first stroke -- which
    recovers the numbering the parent indices in frame 3 are written against.
    """
    beaded = set()
    for i, s in enumerate(strokes):
        if len(s.points) != 2 or s.closed:
            continue
        mx = (s.points[0][0] + s.points[1][0]) / 2
        my = (s.points[0][1] + s.points[1][1]) / 2
        if any(abs(d[0] - mx) < eps and abs(d[1] - my) < eps for d in dots):
            beaded.add(i)

    keep = [(s, i) for i, s in enumerate(strokes) if i not in beaded]
    dsu = _DSU(len(keep))
    owner: dict[str, int] = {}
    for i, (s, _) in enumerate(keep):
        for p in s.points:
            k = _key(p)
            if k in owner:
                dsu.union(i, owner[k])
            else:
                owner[k] = i

    groups: dict[int, tuple[list, int]] = {}
    for i, (s, orig) in enumerate(keep):
        r = dsu.find(i)
        if r not in groups:
            groups[r] = ([], orig)
        groups[r][0].append(s)
        if orig < groups[r][1]:
            groups[r] = (groups[r][0], orig)

    big = [g for g in groups.values() if len(g[0]) > 2]
    # a stroke touching nothing is a spike whose tip missed; hand it to the nearest
    # group rather than letting it stand as a spiral of its own
    for g in groups.values():
        if len(g[0]) > 2:
            continue
        best = None
        for h in big:
            d = min((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                    for a in g[0] for p in a.points
                    for b in h[0] for q in b.points)
            if best is None or d < best[0]:
                best = (d, h)
        if best is not None:
            best[1][0].extend(g[0])

    out = sorted(big if big else list(groups.values()), key=lambda g: g[1])
    return [g[0] for g in out], [strokes[i] for i in sorted(beaded)]


def join_edges(groups, joins):
    """Which two spirals each join held together, by exact vertex lookup.

    One entry per join, in the same order, so join k's two ends are `edges[k]`, with
    None where an end landed on nothing. The page needs that alignment to show a join
    at the moment the reply it holds appears, and the two implementations are kept the
    same whether or not this one has a use for it.
    """
    owner: dict[str, int] = {}
    for i, g in enumerate(groups):
        for st in g:
            for p in st.points:
                owner[_key(p)] = i
    edges = []
    for j in joins:
        a = owner.get(_key(j.points[0]))
        b = owner.get(_key(j.points[1]))
        edges.append((a, b) if a is not None and b is not None and a != b else None)
    return edges


def check_tree(edges, parents, count: int):
    """The tree the picture shows, against the tree the writer wrote down.

    `parents` comes from frame 3, one entry per spiral, None for a root. Returns
    (ok, why): the parent index is a *check* on the segmentation, not its source.
    """
    adj: dict[int, list[int]] = {}
    for e in edges:
        if e is None:
            continue
        a, b = e
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    roots = [i for i, p in enumerate(parents) if p is None]
    if len(roots) != 1:
        return False, "a scroll has exactly one root"
    seen = {roots[0]: None}
    queue = [roots[0]]
    while queue:
        u = queue.pop(0)
        for v in adj.get(u, []):
            if v not in seen:
                seen[v] = u
                queue.append(v)
    if len(seen) != count:
        return False, "the joins do not reach every spiral"
    for i in range(count):
        if seen.get(i) != parents[i]:
            return False, (f"spiral {i} is drawn on {seen.get(i)} "
                           f"but says it answers {parents[i]}")
    return True, ""


def analyze_scroll(text_or_path):
    """One drawing -> an Observation per spiral, plus the joins that held them.

    A drawing with one spiral takes exactly the path it always did.
    """
    strokes, dots = parse_svg(text_or_path)
    if len(strokes) < 2:
        raise ValueError("no Nomai strokes found in that file")
    groups, joins = split_scroll(strokes, dots)
    return [observe_all(g) for g in groups], join_edges(groups, joins), joins
