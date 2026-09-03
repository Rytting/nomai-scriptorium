"""Pixels back to strokes.

Everything else here reads vector data, where a glyph's points are bit-identical to
the connection that lands on them and clustering needs no tolerance at all. A picture
of a drawing has none of that. This is the bridge: an image in, polylines out, in the
same shape `svgparse` produces, so the reader downstream does not have to know where
its strokes came from.

The route is the classical one -- threshold, thin to a one-pixel skeleton, walk the
skeleton into paths, simplify each path to its corners -- and it works here mainly
because Nomai glyphs are *polylines with sharp corners*. Corners survive thinning and
survive simplification, and they are exactly the vertices the fitter wants.
"""
import math

import numpy as np
from PIL import Image, ImageDraw

Point = tuple[float, float]


# --------------------------------------------------------------------- drawing


def rasterize(strokes, dots, width: int = 1400, supersample: int = 3,
              stroke_px: float = 4.0, dot_px: float = 5.0, pad: float = 0.03):
    """Draw vector strokes into an image, the way a screen or a printer would.

    Supersampled and then reduced, so edges are grey rather than stairs -- which is
    what a real capture looks like, and what the thinning has to survive.
    Returns (image, to_world) where `to_world` maps a pixel back to drawing
    coordinates, so a recovered stroke can be compared with the one that made it.
    """
    pts = [p for s in strokes for p in s.points] + list(dots)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    m = pad * max(x1 - x0, y1 - y0) + 3 * dot_px
    x0, x1, y0, y1 = x0 - m, x1 + m, y0 - m, y1 + m
    scale = width / (x1 - x0)
    height = max(1, int(round((y1 - y0) * scale)))

    k = supersample
    img = Image.new("L", (width * k, height * k), 255)
    d = ImageDraw.Draw(img)
    to_px = lambda p: ((p[0] - x0) * scale * k, (p[1] - y0) * scale * k)  # noqa: E731

    for s in strokes:
        w = [to_px(p) for p in s.points]
        if s.closed:
            w = w + [w[0]]
        d.line(w, fill=0, width=max(1, int(round(stroke_px * scale * k))), joint="curve")
        # round caps, which the SVG has and PIL does not
        r = stroke_px * scale * k / 2
        for p in (w[0], w[-1]):
            d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=0)
    for p in dots:
        q = to_px(p)
        r = dot_px * scale * k
        d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=0)

    img = img.resize((width, height), Image.LANCZOS)
    to_world = lambda q: (q[0] / scale + x0, q[1] / scale + y0)  # noqa: E731
    return img, to_world


# --------------------------------------------------------------------- thinning


_NB = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]


def thin(mask: np.ndarray) -> np.ndarray:
    """Zhang-Suen thinning: ink down to a one-pixel skeleton.

    The filled vertex dots are wider than the strokes they sit on, so the ink bulges
    at every corner. Thinning takes those bulges back to a point, which is the whole
    reason to do it rather than trace outlines: a bulge is where a vertex is.
    """
    img = mask.astype(np.uint8).copy()
    while True:
        changed = False
        for step in (0, 1):
            p = [np.roll(np.roll(img, -dy, 0), -dx, 1) for dy, dx in _NB]
            # neighbours, clockwise from north
            n = sum(p)
            trans = sum(((p[i] == 0) & (p[(i + 1) % 8] == 1)).astype(np.uint8)
                        for i in range(8))
            if step == 0:
                cond = (p[0] * p[2] * p[4] == 0) & (p[2] * p[4] * p[6] == 0)
            else:
                cond = (p[0] * p[2] * p[6] == 0) & (p[0] * p[4] * p[6] == 0)
            kill = (img == 1) & (n >= 2) & (n <= 6) & (trans == 1) & cond
            kill[0, :] = kill[-1, :] = kill[:, 0] = kill[:, -1] = False
            if kill.any():
                img[kill] = 0
                changed = True
        if not changed:
            return img.astype(bool)


# --------------------------------------------------------------------- tracing


def _crossings(sk: np.ndarray) -> np.ndarray:
    """How many separate arms leave each skeleton pixel.

    Counting neighbours does not work: a skeleton that steps diagonally has pixels
    with three or four eight-neighbours while being a perfectly ordinary piece of
    line, which reported six hundred junctions in a drawing that has none. The
    crossing number -- transitions from empty to ink around the ring -- collapses
    those adjacent neighbours into the one arm they actually are.
    """
    p = [np.roll(np.roll(sk, -dy, 0), -dx, 1).astype(np.uint8) for dy, dx in _NB]
    c = sum(((p[i] == 0) & (p[(i + 1) % 8] == 1)).astype(np.uint8) for i in range(8))
    return c * sk


def trace(sk: np.ndarray):
    """Walk a skeleton into paths, split wherever three or more lines meet.

    Junctions are where a connection touches a glyph, and where a spike leaves its
    core, so cutting there gives back roughly the pieces the SVG had -- and the
    pieces that are wrong are wrong in ways the reader can already survive.
    """
    arms = _crossings(sk)
    nodes = sk & ((arms == 1) | (arms >= 3))
    used = set()
    paths = []

    def neighbours(y, x):
        """Four-connected first: on a diagonal staircase both a straight and a
        diagonal step are available, and taking the straight one keeps the walk on
        the line instead of cutting a corner off it."""
        straight = [(y + dy, x + dx) for dy, dx in ((-1, 0), (0, 1), (1, 0), (0, -1))
                    if sk[y + dy, x + dx]]
        diag = [(y + dy, x + dx) for dy, dx in ((-1, 1), (1, 1), (1, -1), (-1, -1))
                if sk[y + dy, x + dx]]
        return straight + diag

    def walk(start, first):
        """Follow the line from one node to the next.

        Every step consumes an edge that has not been walked before, which is what
        makes this terminate. Refusing only to step back the way you came does not:
        a closed loop carrying no node sends the walk round it forever, and the path
        grows until the machine runs out of memory. It did.
        """
        path = [start, first]
        used.add(frozenset((start, first)))
        cur, prev = first, start
        while not nodes[cur]:
            nxt = [q for q in neighbours(*cur)
                   if q != prev and frozenset((cur, q)) not in used]
            if not nxt:
                break
            step = nxt[0]
            used.add(frozenset((cur, step)))
            path.append(step)
            cur, prev = step, cur
            if cur == start:
                break
        return path

    ys, xs = np.nonzero(nodes)
    for y, x in zip(ys, xs):
        for q in neighbours(y, x):
            if frozenset(((y, x), q)) in used:
                continue
            paths.append(walk((y, x), q))

    # closed loops touch no node at all
    seen = np.zeros(sk.shape, bool)
    for p in paths:
        for y, x in p:
            seen[y, x] = True
    ys, xs = np.nonzero(sk & ~seen)
    for y, x in zip(ys, xs):
        if seen[y, x]:
            continue
        loop = [(y, x)]
        seen[y, x] = True
        cur = (y, x)
        while True:
            nxt = [q for q in neighbours(*cur) if not seen[q]]
            if not nxt:
                break
            cur = nxt[0]
            seen[cur] = True
            loop.append(cur)
        if len(loop) > 6:
            paths.append(loop + [loop[0]])
    return paths


# --------------------------------------------------------------------- corners


def simplify(path, eps: float):
    """Douglas-Peucker: keep the corners, drop everything between them."""
    if len(path) < 3:
        return list(path)
    a, b = path[0], path[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    best, at = -1.0, 0
    for i in range(1, len(path) - 1):
        p = path[i]
        if n == 0:
            d = math.hypot(p[0] - a[0], p[1] - a[1])
        else:
            d = abs(dy * (p[0] - a[0]) - dx * (p[1] - a[1])) / n
        if d > best:
            best, at = d, i
    if best <= eps:
        return [a, b]
    return simplify(path[: at + 1], eps)[:-1] + simplify(path[at:], eps)
