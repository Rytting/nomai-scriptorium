"""Does the Python side render and read every tilt and winding?"""
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.codec import write  # noqa: E402
from nomai.decode import decode_strict  # noqa: E402
from nomai.glyphs import KNOWN_GLYPHS  # noqa: E402
from nomai.oracle import STRICT  # noqa: E402
from nomai.render import render_grid  # noqa: E402
from nomai.vision import analyze  # noqa: E402

tmp = ROOT / "data" / "strict_svg"
tmp.mkdir(exist_ok=True)
path = tmp / "winding.svg"

print(f"{'flip':>5} {'tilt':>7} {'hw':>5}  result")
print("-" * 40)
ok = fail = 0
for msg in ("Come to the Ash Twin Project", "hi", "The Eye of the Universe"):
    for flip in (1, -1):
        for tilt in (0.0, math.pi * 0.6, math.pi * 1.3):
            for hw in (0.0, 0.15):
                grid = write(msg, 256, STRICT)
                path.write_text(
                    render_grid(grid, KNOWN_GLYPHS, hw, 47, tilt, flip),
                    encoding="utf-8",
                )
                try:
                    got = decode_strict(analyze(path), bases=(256,))
                    good = len(got) == 1 and got[0][2] == msg
                except Exception as exc:  # noqa: BLE001
                    good, got = False, type(exc).__name__
                ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
                if not good:
                    print(f"{flip:>5} {tilt:>7.2f} {hw:>5}  FAIL {msg!r} -> {got}")
print(f"\n{ok} ok, {fail} failed")
