"""Export the colliding X values so the Julia side can confirm them independently."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import Observation, candidate_xs, verify  # noqa: E402
from nomai.gridgen import grid_from_message  # noqa: E402
from nomai.oracle import UPSTREAM, encode  # noqa: E402

CASES = [("hi", 256), ("Curious Archaeology", 256)]

out = []
for msg, base in CASES:
    obs = Observation.from_grid(grid_from_message(msg, base, UPSTREAM))
    colliding = [
        x for x in dict.fromkeys(candidate_xs(obs, base=base)) if verify(x, obs)
    ]
    out.append({
        "message": msg,
        "base": base,
        "x_true": str(encode(msg, base, UPSTREAM)),
        "colliding": [str(x) for x in sorted(colliding)],
    })
    print(f"{msg!r} base {base}: {len(colliding)} colliding integers")

path = ROOT / "data" / "collisions.json"
path.write_text(json.dumps(out), encoding="utf-8")
print(f"wrote {path.relative_to(ROOT)}")
