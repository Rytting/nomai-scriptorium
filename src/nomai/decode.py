"""Replay decoder: observed grid structure -> the message integer X -> text.

The idea in one line: every Oracle question's `k` is a function of the *structure*
(which row each path head is on, which glyphs sit where, the grid coordinate delta of
a connection) -- all of which is visible in the drawing. So we can re-derive the whole
`k` sequence without knowing X, read each answer off the drawing, and rebuild X.

Two things stop it being a straight inversion:

1. `next_column` sorts the two next-points by row *after* asking, so when both path
   heads sit on the same row we cannot tell which question produced which row.
2. A glyph's `allpoints` can contain duplicate points (annotations are built from core
   vertices), so two different answers to a connection question draw the same line.

Both are genuine branches, and both are handled by search rather than guesswork.

X is accumulated forwards, not folded back from the end:

    X = sum_i (a_i - 1) * M_i,   M_0 = 1,  M_{i+1} = M_i * k_i

Forward accumulation matters twice over. Every later term is a multiple of M_n, so
`X mod M_n` is frozen after step n -- and the message is little-endian in `base`, so
the *leading characters* are decided early and prune branches long before the end.
It also sidesteps the Oracle's wrap-around: we never need to know in advance which
question was the last one carrying real message content.
"""
from dataclasses import dataclass
from itertools import product
from typing import Iterator, Optional

from .glyphs import KNOWN_GLYPHS
from .gridgen import (
    Coord,
    GlyphGrid,
    N_GLYPHS,
    Point,
    STARTING_POINT,
    connection_offset,
    connection_pairs,
    dedupe_pairs,
    grid_from_oracle,
    j_choices,
    joint_row_options,
)
from .oracle import STRICT, UPSTREAM, Oracle, decode_int

TOL = 1e-9


@dataclass
class Observation:
    """Exactly what a perfect vision frontend would produce -- nothing more.

    Connection endpoints are *coordinates*, not vertex indices, because resolving a
    coordinate back to an index is ambiguous and that ambiguity is the decoder's
    problem to carry.
    """

    glyphs: dict[Coord, int]
    paths: list[list[Coord]]
    connections: dict[tuple[Coord, Coord], tuple[Point, Point]]

    @property
    def ncols(self) -> int:
        return len(self.paths[0])

    @classmethod
    def from_grid(cls, gg: GlyphGrid) -> "Observation":
        return cls(
            glyphs=dict(gg.glyphs),
            paths=[list(p) for p in gg.paths],
            connections={
                (c.coord1, c.coord2): (c.point1, c.point2) for c in gg.connections
            },
        )


def _unique(seq):
    return list(dict.fromkeys(seq))


def _same_point(a: Point, b: Point) -> bool:
    return abs(a[0] - b[0]) <= TOL and abs(a[1] - b[1]) <= TOL


def _connection_answers(
    obs: Observation, c1: Coord, c2: Coord, dialect: str = UPSTREAM
) -> list[tuple[int, int]]:
    """Candidate (k, answer) for the connection question between c1 and c2.

    More than one when the chosen vertex pair appears twice in the pairs list, which
    happens when a glyph's core and annotation share a vertex.
    """
    pairs = dedupe_pairs(
        connection_pairs(
            KNOWN_GLYPHS[obs.glyphs[c1] - 1],
            KNOWN_GLYPHS[obs.glyphs[c2] - 1],
            connection_offset(c1, c2),
        ),
        dialect,
    )
    pt1, pt2 = obs.connections[(c1, c2)]
    hits = [
        (len(pairs), idx + 1)
        for idx, (a, b) in enumerate(pairs)
        if _same_point(a, pt1) and _same_point(b, pt2)
    ]
    if not hits:
        raise ValueError(
            "connection {}-{}: observed endpoints absent from pairs list".format(c1, c2)
        )
    return hits


def column_options(
    obs: Observation, col: int, dialect: str = UPSTREAM
) -> list[list[tuple[int, int]]]:
    """All candidate (k, answer) sequences for one column, in Oracle-question order.

    Under STRICT this always returns exactly one sequence: the dialect closes both
    branching leaks, so there is nothing to search.
    """
    if col == 1:
        return [[(N_GLYPHS, obs.glyphs[STARTING_POINT])]]

    heads = [p[col - 2] for p in obs.paths]
    nexts = [p[col - 1] for p in obs.paths]  # already row-sorted by the generator

    # Questions 1 and 2: next row for each path head, asked in path order. The
    # generator sorted the answers afterwards, so recover the pre-sort pairing.
    rows = (nexts[0][1], nexts[1][1])
    if dialect == STRICT:
        opts = joint_row_options(heads)
        pair = tuple(sorted(rows))
        row_options = [[(len(opts), opts.index(pair) + 1)]] if pair in opts else []
    else:
        choices = [j_choices(h[1]) for h in heads]
        row_options = []
        for perm in _unique([rows, (rows[1], rows[0])]):
            if perm[0] in choices[0] and perm[1] in choices[1]:
                row_options.append(
                    [
                        (len(choices[0]), choices[0].index(perm[0]) + 1),
                        (len(choices[1]), choices[1].index(perm[1]) + 1),
                    ]
                )
    if not row_options:
        raise ValueError(
            "column {}: no legal row assignment for {} -> {}".format(col, heads, nexts)
        )

    # Then one glyph question per distinct new location, in sorted order.
    glyph_asks = [(N_GLYPHS, obs.glyphs[loc]) for loc in _unique(nexts)]

    # Then one connection question per distinct (head, next) pair.
    conn_slots = [
        _connection_answers(obs, head, npt, dialect)
        for head, npt in _unique(list(zip(heads, nexts)))
    ]

    out = []
    for rows_seq in row_options:
        for conns in product(*conn_slots):
            out.append(rows_seq + glyph_asks + list(conns))
    return out


def _frozen_codepoints(x: int, m: int, base: int) -> list[int]:
    """The leading codepoints that `x mod m` genuinely determines.

    Knowing `X mod m` pins `X mod d` for every *divisor* d of m -- not for every
    d <= m. Since m is a product of the Oracle's k values (33, 3, 2, connection
    counts) it is seldom a multiple of a power of `base`, so this filter is weak by
    construction and usually returns nothing. That is the honest answer: an earlier
    version tested `base**(t+1) <= m`, which is unsound, and it silently discarded
    the true branch on every message longer than two characters.
    """
    out = []
    p = base
    while m % p == 0:
        out.append((x // (p // base)) % base)
        p *= base
    return out


def _plausible(cp: int, strict: bool) -> bool:
    if cp <= 0 or cp > 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
        return False
    if not strict:
        return True
    ch = chr(cp)
    return ch.isprintable() or ch in "\n\t"


def candidate_xs(
    obs: Observation,
    base: Optional[int] = None,
    strict: bool = True,
    dialect: str = UPSTREAM,
) -> Iterator[int]:
    """Every X consistent with the observation, before verification.

    Candidates are taken only from the final column. `grid_from_oracle` re-checks
    `completed` at column boundaries only, so the Oracle always runs dry inside the
    last column it draws -- the true X is a prefix sum ending somewhere in there and
    nowhere else.

    Pass `base` to enable frozen-leading-character pruning. It rarely fires (see
    `_frozen_codepoints`); the search is bounded by the branchy columns, not by it.
    """
    seen: set[int] = set()
    ncols = obs.ncols

    def walk(col: int, x: int, m: int) -> Iterator[int]:
        for seq in column_options(obs, col, dialect):
            x2, m2 = x, m
            if col == ncols:
                for k, answer in seq:
                    x2 += (answer - 1) * m2
                    m2 *= k
                    if x2 not in seen:
                        seen.add(x2)
                        yield x2
                continue
            for k, answer in seq:
                x2 += (answer - 1) * m2
                m2 *= k
            if base is not None and not all(
                _plausible(cp, strict) for cp in _frozen_codepoints(x2, m2, base)
            ):
                continue
            yield from walk(col + 1, x2, m2)

    return walk(1, 0, 1)


def _plan(obs: Observation, dialect: str = UPSTREAM):
    """Per-column (start index, k vector, candidate answer vectors) plus M_0..M_N.

    Every option within a column carries the same k vector -- the two ambiguous row
    questions only arise when both path heads share a row, and then their `j_choices`
    (hence their k) are identical, while a connection question's k is `len(pairs)`
    regardless of which tied pair was chosen. So the whole M sequence is fixed before
    any branching, which is what lets the backward walk compute interval widths.
    """
    cols = []
    ks: list[int] = []
    pos = 0
    for col in range(1, obs.ncols + 1):
        opts = column_options(obs, col, dialect)
        kvec = tuple(k for k, _ in opts[0])
        for o in opts:
            if tuple(k for k, _ in o) != kvec:
                raise AssertionError(f"column {col}: k vector varies across branches")
        cols.append((pos, kvec, [tuple(a for _, a in o) for o in opts]))
        ks.extend(kvec)
        pos += len(kvec)
    M = [1]
    for k in ks:
        M.append(M[-1] * k)
    return cols, M


def _digits_desc(x: int, base: int) -> list[int]:
    out = []
    while x > 0:
        x, r = divmod(x, base)
        out.append(r)
    return out[::-1]


def _pinned_tail(suffix: int, width: int, base: int) -> list[int]:
    """Codepoints the interval [suffix, suffix + width) already determines.

    Returned in message order. These are always the message's *trailing* characters:
    the base-`base` digits are little-endian in message order, so the digits an
    interval pins down first are the most significant ones, i.e. the end of the text.
    Which characters get pinned, and in what order, is forced by how fast `width`
    shrinks -- it is not a choice.
    """
    lo = _digits_desc(suffix, base)
    hi = _digits_desc(suffix + width - 1, base)
    if len(lo) != len(hi):
        return []  # the message's length is not even settled yet
    out = []
    for a, b in zip(lo, hi):
        if a != b:
            break
        out.append(a)
    return out[::-1]


def _prune(states, width: int, base: int, strict: bool, beam: int) -> list[int]:
    scored = []
    for suffix in states:
        tail = _pinned_tail(suffix, width, base)
        if not tail:
            scored.append((1.0, suffix))  # nothing readable yet, do not penalise
            continue
        if any(not _plausible(cp, strict) for cp in tail):
            continue
        scored.append((text_score("".join(chr(c) for c in tail)), suffix))
    scored.sort(key=lambda t: -t[0])
    return [s for _, s in scored[:beam]]


def decode_backward(
    obs: Observation,
    bases=(256, 200_000),
    beam: int = 400,
    strict: bool = True,
    dialect: str = UPSTREAM,
) -> list[tuple[int, int, str]]:
    """Same branch tree as `decode`, walked from the last question to the first.

    Forward, the partial sum only gives `X mod M_j`, a congruence -- which pins no
    base-`base` digit, so nothing is readable until the walk ends and every branch
    must be carried to the bottom. Backward, the partial sum is a *suffix*, and the
    unknown prefix is bounded by M_j, so X sits in an interval of width M_j. An
    interval does pin the top digits, and those are the message's trailing
    characters. Same tree, same branches, same count -- only the moment the
    information arrives changes, and that is enough to prune all the way down.

    This is a beam search, so unlike `decode` it can miss. Keep `beam` generous.
    """
    cols, M = _plan(obs, dialect)
    results = []
    for base in bases:
        # Seed from the final column, where the Oracle always runs dry. Each ask in
        # it is a hypothesis about where that happened (upstream todo.md item 5).
        start, _, answers = cols[-1]
        frontier: set[int] = set()
        for avec in answers:
            suffix = 0
            for off, a in enumerate(avec):
                suffix += (a - 1) * M[start + off]
                frontier.add(suffix)
        states = _prune(frontier, M[start], base, strict, beam)

        for ci in range(len(cols) - 2, -1, -1):
            start, _, answers = cols[ci]
            nxt: set[int] = set()
            for suffix in states:
                for avec in answers:
                    s2 = suffix
                    for off, a in enumerate(avec):
                        s2 += (a - 1) * M[start + off]
                    nxt.add(s2)
            states = _prune(nxt, M[start], base, strict, beam)

        for x in states:  # width is M[0] == 1 here, so x is X exactly
            text = x_to_text(x, base, strict=strict, dialect=dialect)
            if text is not None and verify(x, obs, dialect):
                results.append((base, x, text))
    results.sort(key=lambda r: -text_score(r[2]))
    return results


def verify(x: int, obs: Observation, dialect: str = UPSTREAM) -> bool:
    """Regenerate from X and require an exact structural match."""
    if x <= 0:
        return False
    gg = grid_from_oracle(Oracle(x), dialect)
    if gg.glyphs != obs.glyphs or [list(p) for p in gg.paths] != obs.paths:
        return False
    ours = Observation.from_grid(gg).connections
    if set(ours) != set(obs.connections):
        return False
    # Endpoints are compared with a tolerance: they are drawn coordinates, so an
    # exact float match is not something a vision frontend could ever deliver.
    return all(
        _same_point(a1, b1) and _same_point(a2, b2)
        for key, (a1, a2) in ours.items()
        for (b1, b2) in [obs.connections[key]]
    )


def x_to_codepoints(x: int, base: int) -> list[int]:
    out = []
    while x > 0:
        x, r = divmod(x, base)
        out.append(r)
    return out


def x_to_record(x: int, base: int, strict: bool = False, dialect: str = UPSTREAM):
    """(signature, body, parent) -- the last two None for an upstream integer."""
    got = decode_int(x, base, dialect)
    if got is None:
        return None
    sig_cps, body_cps, parent = got if dialect == STRICT else (None, got, None)
    if not body_cps:
        return None
    for cp in list(body_cps) + list(sig_cps or []):
        if not _plausible(cp, strict):
            return None
    sig = "".join(chr(c) for c in sig_cps) if sig_cps else None
    return sig, "".join(chr(c) for c in body_cps), parent


def x_to_text(
    x: int, base: int, strict: bool = False, dialect: str = UPSTREAM
) -> Optional[str]:
    """The reading as one line, signed ones rendered the way the game shows them."""
    rec = x_to_record(x, base, strict, dialect)
    if rec is None:
        return None
    sig, body, _ = rec
    return f"{sig}: {body}" if sig else body


# Codepoint ranges real messages actually live in. Printability alone is far too
# weak a prior at base 200000, where essentially every candidate decodes to some
# printable CJK string; without this the right answer routinely ranks below garbage.
_COMMON_RANGES = (
    (0x20, 0x7E),  # ASCII printable
    (0xA0, 0x24F),  # Latin-1 supplement, Latin extended A/B
    (0x3040, 0x30FF),  # hiragana, katakana
    (0x4E00, 0x9FFF),  # CJK unified ideographs (common block only)
    (0xFF01, 0xFF5E),  # fullwidth forms
)


_PUNCT = set(".,!?;:'\"-()[]{}/")


def _char_weight(ch: str) -> float:
    """Tiers, not a binary in-range test.

    "Printable ASCII" alone is too coarse: it scores 'hi' and '&i' identically, and
    then the ranking falls back to insertion order and picks whichever the search
    happened to reach first. Letters and spaces have to outrank stray symbols.
    """
    cp = ord(ch)
    if ch == " " or (0x20 < cp < 0x7F and ch.isalnum()):
        return 1.0
    if ch in _PUNCT:
        return 0.8
    if 0x20 <= cp <= 0x7E:
        return 0.4  # remaining ASCII printable: @ # $ % & ^ ~ ...
    if any(lo <= cp <= hi for lo, hi in _COMMON_RANGES):
        return 0.5
    return 0.0


def text_score(text: str) -> float:
    """1.0 for clean prose, ~0.5 for common CJK, ~0 for exotic planes."""
    if not text:
        return -1.0
    return sum(_char_weight(ch) for ch in text) / len(text)


def decode(
    obs: Observation,
    bases=(256, 200_000),
    strict: bool = True,
    dialect: str = UPSTREAM,
) -> list[tuple[int, int, str]]:
    """Return every (base, X, text) consistent with the drawing.

    A list, not a single answer, and that is not a shortcoming of the decoder: the
    drawing does not record where the Oracle ran out of state, so every X that
    exhausts anywhere inside the final column draws identically. Upstream's todo.md
    item 5 describes exactly this and proposes a sentinel glyph to fix it, unbuilt.
    Typically 100+ integers survive `verify`; requiring the *whole* decoded text to
    be printable is what narrows it back down to one.
    """
    results = []
    for base in bases:
        for x in candidate_xs(obs, base=base, strict=strict, dialect=dialect):
            text = x_to_text(x, base, strict=strict, dialect=dialect)
            if text is None:
                continue
            if verify(x, obs, dialect):
                results.append((base, x, text))
    results.sort(key=lambda r: -text_score(r[2]))
    return results


def decode_strict(
    obs: Observation, bases=(256, 200_000), strict: bool = False
) -> list[tuple[int, int, str]]:
    """Decode a STRICT-dialect drawing by linear replay -- no search at all.

    STRICT leaves nothing to guess: `column_options` returns exactly one sequence per
    column, so there is a single answer sequence and a single X per termination
    hypothesis. The leading length digit then rules out all but one of those, which
    is why this needs no beam, no character prior and no ranking.

    `strict` here is only the printable-character filter; leave it off to see exactly
    what the drawing says.
    """
    cols, M = _plan(obs, STRICT)
    for start, _, answers in cols:
        if len(answers) != 1:
            raise ValueError(
                f"column at ask {start} has {len(answers)} readings -- "
                "this drawing is not in the strict dialect"
            )
    seq = [
        (k, a)
        for (_, kvec, answers) in cols
        for k, a in zip(kvec, answers[0])
    ]
    last_start = cols[-1][0]
    x, cands = 0, []
    for i, (k, a) in enumerate(seq):
        x += (a - 1) * M[i]
        if i >= last_start:
            cands.append(x)

    results = []
    for base in bases:
        for c in dict.fromkeys(cands):
            text = x_to_text(c, base, strict=strict, dialect=STRICT)
            if text is not None and verify(c, obs, STRICT):
                results.append((base, c, text))
    return results
