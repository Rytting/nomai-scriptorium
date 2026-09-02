"""Read a NomaiText SVG back into strokes and vertex circles.

`draw` emits exactly three kinds of element:
  * stroked polylines  -- glyph cores, annotations, connection lines
  * filled circles     -- the vertex dots, two cubic beziers each
  * one background rect

Cairo serialises the same drawing two ways depending on its version. The hosted
endpoint emits a single `style="fill:none;stroke-width:4;..."` attribute; a local
render emits `fill="none" stroke-width="4" ...` as separate attributes. So match the
whole tag and classify on whether a stroke width appears anywhere in it, which is
true of both flavours.

A closed polygon is written `M .. L .. L .. L .. Z M ..`, so the trailing `M`
repeats the first point; we drop it and record `closed=True` instead.
"""
import json
import re
from dataclasses import dataclass

Point = tuple[float, float]

_PATH_RE = re.compile(r"<path([^>]*)>")
# the leading separator matters: without it this also matches inside stroke-width="4"
_D_RE = re.compile(r'[\s;"]d="([^"]*)"')
_COORD_RE = re.compile(r'([MLC])((?:\s+[-\d.]+){2,6})')


@dataclass(frozen=True)
class Stroke:
    points: tuple[Point, ...]
    closed: bool

    @property
    def length(self) -> float:
        pts = self.points + (self.points[0],) if self.closed else self.points
        return sum(
            ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            for a, b in zip(pts, pts[1:])
        )


def _numbers(chunk: str) -> list[float]:
    return [float(v) for v in chunk.split()]


def _close(a: Point, b: Point, tol: float = 1e-6) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def parse_svg(text_or_path) -> tuple[list[Stroke], list[Point]]:
    """Return (strokes, circle centres)."""
    raw = text_or_path
    if not isinstance(raw, str) or "<path" not in raw:
        raw = open(text_or_path, encoding="utf-8").read()
    if raw.lstrip().startswith('"'):
        raw = json.loads(raw)  # the Lambda endpoint returns a JSON-quoted string

    strokes: list[Stroke] = []
    circles: list[Point] = []
    for attrs in _PATH_RE.findall(raw):
        m = _D_RE.search(attrs)
        if m is None:
            continue
        d = m.group(1)
        pts: list[Point] = []
        closed = "Z" in d or "z" in d
        for _cmd, chunk in _COORD_RE.findall(d):
            nums = _numbers(chunk)
            for i in range(0, len(nums) - 1, 2):
                pts.append((nums[i], nums[i + 1]))
        if not pts:
            continue
        if "stroke-width" not in attrs:  # a filled vertex dot
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            circles.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
            continue
        if closed and len(pts) > 1 and _close(pts[0], pts[-1]):
            pts = pts[:-1]  # drop the repeated start point after Z
        strokes.append(Stroke(tuple(pts), closed))
    return strokes, circles
