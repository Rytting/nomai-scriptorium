"""Shared helper: build an Observation from a Julia truth file."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nomai.decode import Observation


def obs_from_truth(truth) -> Observation:
    grid = truth["grid"]
    return Observation(
        glyphs={(e["i"], e["j"]): e["glyph"] for e in grid["glyphs"]},
        paths=[[tuple(c) for c in p] for p in grid["paths"]],
        connections={
            (tuple(c["coord1"]), tuple(c["coord2"])): (tuple(c["pt1"]), tuple(c["pt2"]))
            for c in grid["connections"]
        },
    )
