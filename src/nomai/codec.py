"""Public read/write API.

    write(message, base)   -> GlyphGrid          (strict dialect, uniquely readable)
    read(observation)      -> list of readings   (either dialect)
    write_scroll(turns)    -> SVG                (a conversation on one sheet)
    read_scroll(svg)       -> list of records + whether the tree checks out

Use STRICT for messages we write ourselves: the drawing has exactly one reading and
decoding is a linear replay. Use UPSTREAM to read anything produced by
evanfields/NomaiText.jl or nomai-writing.com -- those drawings are genuinely
ambiguous, so `read` returns candidates ranked by a character prior, not an answer.
"""
from .decode import Observation, decode_backward, decode_strict
from .gridgen import GlyphGrid, grid_from_oracle
from .oracle import STRICT, UPSTREAM, Oracle, encode

MAX_NONCE = 64


def write(message: str, base: int = 256, dialect: str = STRICT,
          signature: str | None = None, parent: int | None = None) -> GlyphGrid:
    """Message -> drawing. In STRICT, guarantees the drawing has exactly one reading.

    Rival readings are a deterministic function of X, so the encoder can simply check
    its own output: try nonces until the produced drawing decodes back to exactly one
    reading, and that reading is the message. Costs a few regenerations at write time
    and buys a hard guarantee at read time.
    """
    if dialect != STRICT:
        return grid_from_oracle(Oracle(encode(message, base, dialect)), dialect)
    want = f"{signature}: {message}" if signature else message
    for nonce in range(1, MAX_NONCE + 1):
        x = encode(message, base, STRICT, nonce, signature, parent)
        gg = grid_from_oracle(Oracle(x), STRICT)
        readings = decode_strict(Observation.from_grid(gg), bases=(base,))
        if len(readings) == 1 and readings[0][2] == want:
            return gg
    raise RuntimeError(
        f"no nonce below {MAX_NONCE} yields a uniquely readable drawing for "
        f"{message!r} at base {base}"
    )


def read(obs: Observation, bases=(256, 200_000), dialect: str = STRICT):
    """Drawing -> readings. STRICT returns exactly one; UPSTREAM returns candidates."""
    if dialect == STRICT:
        return read_strict(obs, bases)
    return decode_backward(obs, bases=bases, dialect=UPSTREAM)


def read_strict(candidates, bases=(256, 200_000)):
    """Exactly one reading, from whichever candidate reading of the rows works.

    `candidates` is what `vision.observe_all` returns: one Observation normally, and
    more only when the row assignment is genuinely undecided -- which happens on
    drawings too small for the geometry to settle it. A wrong row placement fails
    loudly, usually with a connection landing on no vertex, and that is the signal
    wanted rather than an error to pass on.
    """
    if isinstance(candidates, Observation):
        candidates = [candidates]
    for cand in candidates:
        try:
            got = decode_strict(cand, bases=bases)
        except Exception:  # noqa: BLE001
            continue
        if len(got) == 1:
            return got
    return []


def read_drawing(text_or_path, bases=(256, 200_000)):
    """An SVG holding one spiral -> its reading, or an empty list."""
    from .svgparse import parse_svg
    from .vision import observe_all

    strokes, _dots = parse_svg(text_or_path)
    return read_strict(observe_all(strokes), bases)


def write_scroll(turns, base: int = 256, handwriting: float = 0.0, seed: int = 47,
                 flip: int = 1, tight: float = 0.29) -> str:
    """A conversation -> one SVG holding all of it.

    `turns` is a list of `(text, signature or None, parent index or None)`, in the
    order they were written; exactly one of them is a root. Only the root is plugged
    into the wall, and each reply records which spiral it answers so that a reader can
    check the tree it sees against the tree that was written.
    """
    from .glyphs import KNOWN_GLYPHS
    from .scroll import Spiral, render_scroll

    if not turns:
        raise ValueError("a scroll needs at least one spiral")
    roots = [i for i, (_, _, p) in enumerate(turns) if p is None]
    if len(roots) != 1 or roots[0] != 0:
        raise ValueError("a scroll has exactly one root, and it comes first")
    spirals = [Spiral(write(t, base, STRICT, s or None, p), p) for t, s, p in turns]
    return render_scroll(spirals, KNOWN_GLYPHS, handwriting, seed, flip, tight)


def read_scroll(text_or_path, base: int = 256):
    """One SVG -> `(records, tree_ok, why)`.

    Each record is `(signature or None, text, parent or None)`, numbered in the order
    the spirals were written. `tree_ok` says whether the way they are drawn agrees
    with what each one claims to answer -- the parent index is a check on the
    segmentation, never its source.
    """
    from .decode import x_to_record
    from .scroll import analyze_scroll, check_tree

    obs, edges, _joins = analyze_scroll(text_or_path)
    records = []
    for cands in obs:
        got = read_strict(cands, bases=(base,))
        records.append(
            x_to_record(got[0][1], base, False, STRICT) if len(got) == 1 else None
        )
    if len(records) == 1:
        return records, True, ""
    parents = [r[2] if r else None for r in records]
    ok, why = check_tree(edges, parents, len(records))
    return records, ok, why
