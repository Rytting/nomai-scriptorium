"""Port of NomaiText.jl's src/glyphgrid.jl -- the only place the Oracle is consumed.

Layout/typesetting is deliberately not ported: `ask!` appears nowhere in
grid_layout.jl, so the spiral is pure presentation and carries no message content.
"""
import math
from dataclasses import dataclass, field

from .glyphs import KNOWN_GLYPHS, K, ROWS
from .oracle import STRICT, UPSTREAM, Oracle, encode

MIDLINE = 1 + ROWS // 2
DEFAULT_SPACING = 4 * K
STARTING_POINT = (1, MIDLINE)
N_GLYPHS = len(KNOWN_GLYPHS)

Coord = tuple[int, int]
Point = tuple[float, float]


def j_choices(j: int) -> tuple[int, ...]:
    if j == 1:
        return (1, 2)
    if j == ROWS:
        return (ROWS - 1, ROWS)
    return (j - 1, j, j + 1)


def joint_row_options(heads) -> list[tuple[int, int]]:
    """Every achievable *sorted* pair of next rows, in a canonical order.

    The strict dialect asks this as one question instead of asking each path
    separately and sorting afterwards. The reachable set of drawings is identical --
    upstream sorts precisely so paths cannot cross, and every element here is already
    sorted -- but the answer is now recoverable from the drawing, because the drawn
    pair *is* the answer rather than an order-destroyed shadow of two answers.
    """
    c0, c1 = j_choices(heads[0][1]), j_choices(heads[1][1])
    return sorted({tuple(sorted((v0, v1))) for v0 in c0 for v1 in c1})


def connection_pairs(glyph_a, glyph_b, offset, thresh: float = 0.01):
    """Port of `_shortest_connection!` with the Oracle call removed.

    `best` is updated inside the loop and the tie test straddles that update, so the
    result depends on iteration order and can retain pairs that a plain argmin would
    drop. Reproduce verbatim -- `len(pairs)` is the `k` of the Oracle question, so a
    "cleaner" implementation silently desynchronises the whole replay.
    """
    best = math.inf
    pairs: list[tuple[Point, Point]] = []
    ox, oy = offset
    for a in glyph_a.allpoints:
        for b in glyph_b.allpoints:
            d = math.hypot(a[0] - (b[0] + ox), a[1] - (b[1] + oy))
            if d <= best - thresh:
                pairs.clear()
                pairs.append((a, b))
            elif d < best + thresh:
                pairs.append((a, b))
            best = min(d, best)
    return pairs


def connection_offset(coord1: Coord, coord2: Coord) -> Point:
    return (
        DEFAULT_SPACING * (coord2[0] - coord1[0]),
        DEFAULT_SPACING * (coord2[1] - coord1[1]),
    )


@dataclass(frozen=True)
class Connection:
    coord1: Coord
    point1: Point
    coord2: Coord
    point2: Point


@dataclass
class GlyphGrid:
    glyphs: dict[Coord, int] = field(default_factory=dict)  # coord -> 1-based glyph id
    paths: list[list[Coord]] = field(default_factory=lambda: [[], []])
    connections: list[Connection] = field(default_factory=list)

    @property
    def ncols(self) -> int:
        return max((i for i, _ in self.glyphs), default=0)


def _unique(seq):
    return list(dict.fromkeys(seq))


def _next_point(oracle: Oracle, head: Coord) -> Coord:
    i, j = head
    choices = j_choices(j)
    return (i + 1, oracle.ask_options(choices))


def dedupe_pairs(pairs, dialect: str):
    """Strict drops duplicate vertex pairs before asking.

    A glyph's `allpoints` repeats points whose annotation was built from a core
    vertex, so upstream can offer the same (a, b) twice: two different answers, one
    identical line on the page. Deduplicating makes the answer readable again.
    """
    return list(dict.fromkeys(pairs)) if dialect == STRICT else pairs


def _connect(
    gg: GlyphGrid, oracle: Oracle, c1: Coord, c2: Coord, dialect: str
) -> None:
    pairs = dedupe_pairs(
        connection_pairs(
            KNOWN_GLYPHS[gg.glyphs[c1] - 1],
            KNOWN_GLYPHS[gg.glyphs[c2] - 1],
            connection_offset(c1, c2),
        ),
        dialect,
    )
    a, b = pairs[oracle.ask(len(pairs)) - 1]
    gg.connections.append(Connection(c1, a, c2, b))


def next_column(gg: GlyphGrid, oracle: Oracle, dialect: str = UPSTREAM) -> None:
    if not gg.glyphs:
        gg.glyphs[STARTING_POINT] = oracle.ask(N_GLYPHS)
        for path in gg.paths:
            path.append(STARTING_POINT)
        return

    heads = [path[-1] for path in gg.paths]
    if dialect == STRICT:
        rows = oracle.ask_options(joint_row_options(heads))
        col = heads[0][0] + 1
        next_pts = [(col, rows[0]), (col, rows[1])]  # already sorted
    else:
        next_pts = [_next_point(oracle, head) for head in heads]
        next_pts.sort(key=lambda c: c[1])  # prevent path crossings
    for path, pt in zip(gg.paths, next_pts):
        path.append(pt)

    for loc in _unique(next_pts):
        gg.glyphs[loc] = oracle.ask(N_GLYPHS)

    for head, new_pt in _unique(list(zip(heads, next_pts))):
        _connect(gg, oracle, head, new_pt, dialect)


def grid_from_oracle(oracle: Oracle, dialect: str = UPSTREAM) -> GlyphGrid:
    gg = GlyphGrid()
    while not oracle.completed:
        next_column(gg, oracle, dialect)
    return gg


def grid_from_message(
    message: str, base: int = 256, dialect: str = UPSTREAM, nonce: int = 1
) -> GlyphGrid:
    """Low level. For STRICT prefer `codec.write`, which picks a nonce that makes
    the resulting drawing uniquely readable; a fixed nonce does not guarantee it."""
    return grid_from_oracle(Oracle(encode(message, base, dialect, nonce)), dialect)
