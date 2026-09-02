"""Draw Nomai glyphs to SVG, without Luxor.

Mirrors what `draw` does in NomaiText.jl, which we know exactly -- predicting a real
drawing's element counts from the grid matched it at 107 of 107:

  a PolySpec  -> one stroked polyline, plus a filled dot on each *non-terminal*
                 vertex (all of them when the polygon is closed, points[2:-1] when
                 it is open)
  a Glyph     -> its core, then its annotation if it has one
  a connection-> one stroked line, plus a filled dot at each end

The vertex dots are a constant size on the page: upstream divides the radius by the
current canvas scale, so scaling a glyph up does not scale its dots.
"""
import math

Point = tuple[float, float]

BACKGROUND = "rgb(98.039216%,92.156863%,84.313725%)"  # antiquewhite
INK = "rgb(6.27451%,30.588235%,54.509804%)"  # dodgerblue4
STROKE_WIDTH = 4
DOT_RADIUS = 5


def similarity(scale: float = 1.0, rotation: float = 0.0,
               translate: Point = (0.0, 0.0)):
    """A placement: world = scale * rot(rotation) * local + translate."""
    w = complex(math.cos(rotation), math.sin(rotation)) * scale
    t = complex(*translate)
    return lambda p: (lambda z: (z.real, z.imag))(w * complex(*p) + t)


def _fmt(v: float) -> str:
    return f"{v:.6f}".rstrip("0").rstrip(".")


def _polyline(points, closed: bool) -> str:
    d = "M " + " L ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in points)
    if closed:
        d += f" Z M {_fmt(points[0][0])} {_fmt(points[0][1])}"
    return (
        f'<path fill="none" stroke-width="{STROKE_WIDTH}" stroke-linecap="round" '
        f'stroke-linejoin="round" stroke="{INK}" stroke-opacity="1" d="{d} "/>'
    )


def _dot(pt: Point, radius: float = DOT_RADIUS) -> str:
    x, y = pt
    k = radius * 0.5523  # cubic bezier circle constant
    d = (
        f"M {_fmt(x + radius)} {_fmt(y)} "
        f"C {_fmt(x + radius)} {_fmt(y + k)} {_fmt(x + k)} {_fmt(y + radius)} "
        f"{_fmt(x)} {_fmt(y + radius)} "
        f"C {_fmt(x - k)} {_fmt(y + radius)} {_fmt(x - radius)} {_fmt(y + k)} "
        f"{_fmt(x - radius)} {_fmt(y)} "
        f"C {_fmt(x - radius)} {_fmt(y - k)} {_fmt(x - k)} {_fmt(y - radius)} "
        f"{_fmt(x)} {_fmt(y - radius)} "
        f"C {_fmt(x + k)} {_fmt(y - radius)} {_fmt(x + radius)} {_fmt(y - k)} "
        f"{_fmt(x + radius)} {_fmt(y)} Z"
    )
    return f'<path fill-rule="nonzero" fill="{INK}" fill-opacity="1" d="{d}"/>'


def polyspec_svg(points, closed: bool, place) -> list[str]:
    world = [place(p) for p in points]
    out = [_polyline(world, closed)]
    dotted = world if closed else world[1:-1]
    out.extend(_dot(p) for p in dotted)
    return out


def glyph_svg(glyph, place) -> list[str]:
    out = polyspec_svg(glyph.core.points, glyph.core.close, place)
    if glyph.annotation is not None:
        out.extend(polyspec_svg(glyph.annotation.points, glyph.annotation.close, place))
    return out


def connection_svg(a: Point, b: Point) -> list[str]:
    return [_polyline([a, b], False), _dot(a), _dot(b)]


def document(elements, width: float, height: float, origin: Point = (0.0, 0.0)) -> str:
    ox, oy = origin
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_fmt(width)}" '
        f'height="{_fmt(height)}" viewBox="{_fmt(ox)} {_fmt(oy)} '
        f'{_fmt(width)} {_fmt(height)}">\n'
        f'<rect x="{_fmt(ox)}" y="{_fmt(oy)}" width="{_fmt(width)}" '
        f'height="{_fmt(height)}" fill="{BACKGROUND}" fill-opacity="1"/>\n'
        + "\n".join(elements)
        + "\n</svg>\n"
    )


# --- spiral layout -------------------------------------------------------------
# Mirrors draw_spiral / PathGridLayout.transform. The curve itself is our own: a
# logarithmic spiral r = a*exp(b*theta), walked by exact arc length rather than by
# Luxor's discretised path. Same family, same constants from the source, but the
# points along it are computed in closed form.

SPIRAL_A = 164.0
SPIRAL_B = 0.29
# the scroll socket the drawing is anchored in; see the page for how it is drawn
SOCKET_R = 1.5
MAX_SCALE = 2.0
GLYPH_K = 20.0
GRID_ROWS = 3


def arc_length(theta: float, a: float = SPIRAL_A, b: float = SPIRAL_B) -> float:
    return math.hypot(1.0, b) * (a / b) * (math.exp(b * theta) - 1.0)


def theta_at_length(length: float, a: float = SPIRAL_A, b: float = SPIRAL_B) -> float:
    return math.log(1.0 + length * b / (a * math.hypot(1.0, b))) / b


def spiral_period(ncols: int, b: float = SPIRAL_B) -> float:
    """Upstream grows the period in pi/24 steps until the path is long enough."""
    needed = 3.5 * GLYPH_K * ncols
    period = math.pi / 4
    while arc_length(period, SPIRAL_A, b) < needed:
        period += math.pi / 24
    return period


class SpiralLayout:
    """Where every (column, row) cell sits, and at what angle and scale."""

    def __init__(self, ncols: int, tilt: float = 0.0, flip: int = 1,
                 tight: float = SPIRAL_B):
        self.ncols = ncols
        self.flip = -1 if flip == -1 else 1
        self.b = tight
        self.period = spiral_period(ncols, self.b)
        # Turned so the tail's outward tangent points straight down: the socket is a
        # fixture at the bottom of the panel and the writing comes out of it, so the
        # tail is the end whose direction is fixed and `tilt` leans the rest about it.
        self.rotation = (
            math.pi / 2 + tilt
            - math.atan2(float(self.flip), self.b)
            - self.flip * self.period
        )
        self.total_len = arc_length(self.period, SPIRAL_A, self.b)
        self.delta = (MAX_SCALE - 1) / (ncols - 1) if ncols > 1 else 0.0
        xs, ys = [], []
        for n in range(801):
            p = self._raw(self.period * n / 800)
            xs.append(p[0])
            ys.append(p[1])
        self.box = (max(xs) - min(xs), max(ys) - min(ys))
        # Anchored on the tail, not the centre: that is the point the socket holds.
        self.tail_scale = 1 + (ncols - 1) * self.delta
        tail_raw, tail_slope = self._raw(self.period), (
            math.atan2(float(self.flip), self.b) + self.flip * self.period
            + self.rotation
        )
        d_row = (2 - GRID_ROWS) * 3 * GLYPH_K * self.tail_scale
        self.anchor = (tail_raw[0] - d_row * math.sin(tail_slope),
                       tail_raw[1] + d_row * math.cos(tail_slope))
        self.ext = (min(xs) - self.anchor[0], max(xs) - self.anchor[0],
                    min(ys) - self.anchor[1], max(ys) - self.anchor[1])

    def _raw(self, theta: float) -> Point:
        """A point on the path.

        `flip` mirrors the curve. Only the curve: a mirrored glyph is not in the
        alphabet, and never has to be, because the layout places each glyph by
        turning it to the local tangent -- so reflecting the path leaves every glyph
        a plain rotation of itself.
        """
        a = self.flip * theta
        r = SPIRAL_A * math.exp(self.b * theta)
        z = complex(r * math.cos(a), r * math.sin(a))
        z *= complex(math.cos(self.rotation), math.sin(self.rotation))
        return (z.real, z.imag)

    def point_slope(self, k: float):
        """The point a fraction k along the path, and the tangent angle there.

        The tangent is closed form, not a finite difference. Differencing forwards
        needs a special case at the very end of the path, and stepping backwards
        there instead reverses the tangent by 180 degrees -- which flips the row
        offset and throws the last column to the far side of the spiral, with its
        connections stretched across the page to reach it.

            z(theta)  = a e^(b theta) e^(i f theta) e^(i rot)
            dz/dtheta = a e^(b theta) (b + i f) e^(i f theta) e^(i rot)
            arg       = atan2(f, b) + f theta + rot
        """
        theta = theta_at_length(max(0.0, min(1.0, k)) * self.total_len, SPIRAL_A, self.b)
        return self._raw(theta), (
            math.atan2(float(self.flip), self.b) + self.flip * theta + self.rotation
        )

    @property
    def centre(self) -> Point:
        """The point the path winds into, in the coordinates `place` returns --
        what "away from the spiral" is measured against."""
        return (-self.anchor[0], -self.anchor[1])

    def col_at(self, k: float) -> float:
        """Which column, as a real number, sits at path fraction k -- `fraction`
        inverted, so a reply can attach part way along its parent."""
        n = self.ncols - 1
        if n <= 0:
            return 1.0
        total = n + 0.5 * n * n * self.delta
        if self.delta == 0:
            return 1 + k * total
        return 1 + (-1 + math.sqrt(1 + 2 * self.delta * k * total)) / self.delta

    def point_at(self, k: float, j: int) -> dict:
        """The point on row j at an arbitrary fraction along the path, and the row
        axis there -- which is perpendicular to the spiral by construction."""
        theta = theta_at_length(max(0.0, min(1.0, k)) * self.total_len,
                                SPIRAL_A, self.b)
        base = self._raw(theta)
        slope = (math.atan2(float(self.flip), self.b) + self.flip * theta
                 + self.rotation)
        scale_here = 1 + (self.col_at(k) - 1) * self.delta
        d = (j - GRID_ROWS) * 3 * GLYPH_K * scale_here
        return {
            "x": base[0] - d * math.sin(slope) - self.anchor[0],
            "y": base[1] + d * math.cos(slope) - self.anchor[1],
            "ux": -math.sin(slope), "uy": math.cos(slope), "scale": scale_here,
        }

    def fraction(self, i: int) -> float:
        n = self.ncols - 1
        if n <= 0:
            return 0.0
        total = n + 0.5 * n * n * self.delta
        return ((i - 1) + 0.5 * (i - 1) ** 2 * self.delta) / total

    def place(self, i: int, j: int):
        k = self.fraction(i)
        base, slope = self.point_slope(k)
        scale_here = 1 + (i - 1) * self.delta
        d = (j - GRID_ROWS) * 3 * GLYPH_K * scale_here
        off = complex(0, d) * complex(math.cos(slope), math.sin(slope))
        pt = (base[0] + off.real - self.anchor[0],
              base[1] + off.imag - self.anchor[1])
        return similarity((MAX_SCALE - 1) * k + 1, slope, pt)

    def canvas(self):
        """The viewBox, which is centred on the *socket* rather than the drawing.

        The socket sits at the bottom middle of the panel with the tail in it, so the
        box is built outwards from the tail: wide enough to hold the drawing either
        side of it, and deep enough to leave the socket room below.
        """
        bw, bh = self.box
        pad = max(
            12 * GLYPH_K + (GRID_ROWS - 1) * 4 * GLYPH_K * 2 * MAX_SCALE,
            0.05 * bw,
            0.05 * bh,
        )
        m = pad / 2
        r = SOCKET_R * GLYPH_K * self.tail_scale
        x0, x1, y0, y1 = self.ext
        w = 2 * max(x1 + m, m - x0)
        y = y0 - m
        return -w / 2, y, w, (y1 + 2.2 * r + 0.15 * m) - y


def handwrite(grid, glyphs, amount: float, seed: int = 47):
    """Perturb a grid's glyphs as if hand drawn, mirroring upstream's `handwrite`.

    Two details matter and both cost us time to find the hard way. Points shared
    between a glyph's core and its annotation go through one map per glyph, so they
    move together -- which is why a connection endpoint stays bit-identical to the
    vertex it attaches to. And the shift is drawn once per PolySpec, not once per
    glyph, so a glyph's annotation sits slightly apart from where its core alone
    would put it.
    """
    import random as _random

    rng = _random.Random(seed)
    maps: dict = {}

    def shift_poly(points, pmap):
        tx = GLYPH_K * amount / 8 * rng.gauss(0, 1)
        ty = GLYPH_K * amount / 8 * rng.gauss(0, 1)
        out = []
        for p in points:
            if p not in pmap:
                pmap[p] = (
                    p[0] + GLYPH_K * amount / 20 * rng.gauss(0, 1) + tx,
                    p[1] + GLYPH_K * amount / 20 * rng.gauss(0, 1) + ty,
                )
            out.append(pmap[p])
        return tuple(out)

    drawn = {}
    for coord, gid in grid.glyphs.items():
        g = glyphs[gid - 1]
        pmap = maps.setdefault(coord, {})
        core = (shift_poly(g.core.points, pmap), g.core.close)
        ann = None
        if g.annotation is not None:
            ann = (shift_poly(g.annotation.points, pmap), g.annotation.close)
        drawn[coord] = (core, ann)

    conns = [
        (c.coord1, maps[c.coord1][c.point1], c.coord2, maps[c.coord2][c.point2])
        for c in grid.connections
    ]
    return drawn, conns


def spiral_elements(grid, glyphs, handwriting: float, seed: int, layout,
                    shift: Point = (0.0, 0.0)):
    """One spiral's SVG elements, and where each glyph's points landed.

    Split out of `render_grid` so a scroll can put several spirals on one sheet
    without any of the handwriting or connection code needing to know about it:
    `shift` moves this spiral into its place, and everything downstream is unchanged.
    """
    dx, dy = shift

    def place_for(coord):
        base = layout.place(*coord)
        return lambda pt: (lambda q: (q[0] + dx, q[1] + dy))(base(pt))

    places = {c: place_for(c) for c in grid.glyphs}
    drawn_at: dict = {c: [] for c in grid.glyphs}
    els: list[str] = []

    def part(points, closed, coord):
        world = [places[coord](pt) for pt in points]
        els.extend(polyspec_svg(points, closed, places[coord]))
        drawn_at[coord].extend(world)

    if handwriting > 0:
        drawn, conns = handwrite(grid, glyphs, handwriting, seed)
        for coord, (core, ann) in drawn.items():
            part(core[0], core[1], coord)
            if ann is not None:
                part(ann[0], ann[1], coord)
        for c1, p1, c2, p2 in conns:
            els.extend(connection_svg(places[c1](p1), places[c2](p2)))
    else:
        for coord, gid in grid.glyphs.items():
            g = glyphs[gid - 1]
            part(g.core.points, g.core.close, coord)
            if g.annotation is not None:
                part(g.annotation.points, g.annotation.close, coord)
        for conn in grid.connections:
            els.extend(
                connection_svg(
                    places[conn.coord1](conn.point1),
                    places[conn.coord2](conn.point2),
                )
            )
    return els, drawn_at


def render_grid(grid, glyphs, handwriting: float = 0.0, seed: int = 47,
                tilt: float = 0.0, flip: int = 1, tight: float = SPIRAL_B) -> str:
    """A GlyphGrid -> a complete SVG, laid out on the spiral."""
    layout = SpiralLayout(grid.ncols, tilt, flip, tight)
    els, _ = spiral_elements(grid, glyphs, handwriting, seed, layout)
    vx, vy, w, h = layout.canvas()
    return document(els, w, h, origin=(vx, vy))
