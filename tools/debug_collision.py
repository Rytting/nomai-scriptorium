"""Are the extra decode results genuine collisions, or is verify() broken?

Regenerate independently of decode.py and diff the grids field by field.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import Observation, candidate_xs, x_to_text  # noqa: E402
from nomai.gridgen import grid_from_oracle  # noqa: E402
from nomai.oracle import Oracle  # noqa: E402
from tools_shim import obs_from_truth  # noqa: E402

CASE = sys.argv[1] if len(sys.argv) > 1 else "Curious_Archaeology_base256"
t = json.loads((ROOT / "data" / "truth" / f"{CASE}.json").read_text(encoding="utf-8"))
obs = obs_from_truth(t)
base, x_true = t["base"], int(t["x"])

cands = list(candidate_xs(obs, base=base))
print(f"{CASE}: {len(cands)} candidates, X_true present = {x_true in cands}")

exact = []
for x in cands:
    gg = grid_from_oracle(Oracle(x))
    got = Observation.from_grid(gg)
    same_glyphs = got.glyphs == obs.glyphs
    same_paths = got.paths == obs.paths
    same_conn_keys = set(got.connections) == set(obs.connections)
    same_conn_pts = same_conn_keys and all(
        got.connections[k] == obs.connections[k] for k in got.connections
    )
    if same_glyphs and same_paths and same_conn_pts:
        exact.append(x)

print(f"structurally identical to the observed drawing: {len(exact)}")
for x in exact[:8]:
    print(f"  X={x}  text={x_to_text(x, base)!r}  is_true={x == x_true}")
if len(exact) > 8:
    print(f"  ... and {len(exact) - 8} more")
