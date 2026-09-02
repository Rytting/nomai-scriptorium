"""Check the forward accumulation against the true ask log, independent of any
structure re-derivation. If X does not show up as a prefix sum here, the formula is
wrong; if it does, the bug is in branch enumeration or pruning."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for path in sorted((ROOT / "data" / "truth").glob("*.json")):
    t = json.loads(path.read_text(encoding="utf-8"))
    x_true = int(t["x"])
    asks = [tuple(a) for a in t["asks"]]
    x, m = 0, 1
    hit = None
    for step, (k, a) in enumerate(asks):
        x += (a - 1) * m
        m *= k
        if x == x_true and hit is None:
            hit = step
    print(
        f"{path.stem:<30} asks={len(asks):>3} "
        f"X_found_at={'no' if hit is None else hit:>4} final_x_eq_X={x == x_true}"
    )
