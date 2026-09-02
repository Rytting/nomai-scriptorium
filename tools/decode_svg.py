"""End to end: a real SVG in, text out.

Compares every intermediate against the Julia ground truth for the same message, so
a failure says which stage broke rather than just "wrong answer".
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import Observation, decode_backward  # noqa: E402
from nomai.gridgen import grid_from_message  # noqa: E402
from nomai.oracle import UPSTREAM  # noqa: E402
from nomai.vision import analyze  # noqa: E402

TRUTH_MSG, TRUTH_BASE = "hello", 200_000
want = Observation.from_grid(grid_from_message(TRUTH_MSG, TRUTH_BASE, UPSTREAM))

for sample in sorted((ROOT / "assets" / "samples").glob("*.svg")):
    print(f"\n=== {sample.name}")
    try:
        obs = analyze(sample)
    except Exception as exc:  # noqa: BLE001
        print(f"  analyze failed: {type(exc).__name__}: {exc}")
        continue

    ok_g = obs.glyphs == want.glyphs
    ok_p = obs.paths == want.paths
    ok_c = set(obs.connections) == set(want.connections)
    print(f"  glyphs      {'ok' if ok_g else 'MISMATCH'}   ({len(obs.glyphs)} cells)")
    if not ok_g:
        for cell in sorted(set(obs.glyphs) | set(want.glyphs)):
            a, b = obs.glyphs.get(cell), want.glyphs.get(cell)
            if a != b:
                print(f"      {cell}: got {a}, want {b}")
    print(f"  paths       {'ok' if ok_p else 'MISMATCH'}")
    if not ok_p:
        print(f"      got  {obs.paths}")
        print(f"      want {want.paths}")
    print(f"  connections {'ok' if ok_c else 'MISMATCH'}   ({len(obs.connections)})")
    if ok_c:
        bad = [k for k in obs.connections if obs.connections[k] != want.connections[k]]
        print(f"  endpoints   {'ok' if not bad else f'{len(bad)} wrong vertices'}")

    results = decode_backward(obs, bases=(TRUTH_BASE,), dialect=UPSTREAM)
    print(f"  decoded: {[t for _, _, t in results][:5]}")
    print(f"  TOP-1 == {TRUTH_MSG!r}: {bool(results) and results[0][2] == TRUTH_MSG}")
