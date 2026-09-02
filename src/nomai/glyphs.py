"""The 33 KNOWN_GLYPHS, loaded from coordinates exported by the real Julia package.

We deliberately do not recompute these in Python. They come out of Luxor's `ngon` /
`rotatepoint` / `anglethreepoints`, and `_shortest_connection` picks tied-shortest
vertex pairs with a 0.01 tolerance -- so a small numeric drift in the vertex tables
would silently change `k` and break replay decoding.

Regenerate with:  julia tools/export_truth.jl
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

Point = tuple[float, float]

_DATA = Path(__file__).resolve().parents[2] / "data" / "glyphs.json"


@dataclass(frozen=True)
class PolySpec:
    points: tuple[Point, ...]
    close: bool


@dataclass(frozen=True)
class Glyph:
    core: PolySpec
    annotation: Optional[PolySpec]

    @property
    def allpoints(self) -> tuple[Point, ...]:
        """Matches NomaiText.allpoints: core points then annotation points.

        May contain duplicates -- annotations are built from core vertices, so e.g.
        a square annotation reuses two of them. Duplicates matter: they create
        distinct Oracle answers that draw identically.
        """
        if self.annotation is None:
            return self.core.points
        return self.core.points + self.annotation.points


def _polyspec(d) -> PolySpec:
    return PolySpec(tuple((p[0], p[1]) for p in d["points"]), bool(d["close"]))


def _load():
    if not _DATA.exists():
        raise FileNotFoundError(
            f"{_DATA} missing -- run `julia tools/export_truth.jl` first"
        )
    raw = json.loads(_DATA.read_text(encoding="utf-8"))
    glyphs = tuple(
        Glyph(
            _polyspec(g["core"]),
            None if g["annotation"] is None else _polyspec(g["annotation"]),
        )
        for g in raw["glyphs"]
    )
    return glyphs, float(raw["k"]), int(raw["rows"])


KNOWN_GLYPHS, K, ROWS = _load()
