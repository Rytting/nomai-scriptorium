"""Where does the branch walk stop, and is pruning to blame?"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import Observation, candidate_xs, column_options  # noqa: E402
from tools_shim import obs_from_truth  # noqa: E402

for path in sorted((ROOT / "data" / "truth").glob("*.json")):
    t = json.loads(path.read_text(encoding="utf-8"))
    obs = obs_from_truth(t)
    x_true = int(t["x"])
    n_asks_from_structure = sum(
        len(column_options(obs, c)[0]) for c in range(1, obs.ncols + 1)
    )
    n_opts = [len(column_options(obs, c)) for c in range(1, obs.ncols + 1)]
    unpruned = list(candidate_xs(obs, base=None))
    pruned = list(candidate_xs(obs, base=t["base"]))
    print(
        f"{path.stem:<30} cols={obs.ncols:>3} asks_true={len(t['asks']):>3} "
        f"asks_derived={n_asks_from_structure:>3} "
        f"cand_nopr={len(unpruned):>4} cand_pr={len(pruned):>4} "
        f"X_in_nopr={x_true in unpruned} X_in_pr={x_true in pruned} "
        f"branchy_cols={[i + 1 for i, n in enumerate(n_opts) if n > 1]}"
    )
