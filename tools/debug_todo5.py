"""Isolate upstream todo.md item 5 from the sort ambiguity.

Item 5 alone: hold the ask sequence fixed at the TRUE one, and vary only where the
Oracle is assumed to have run dry inside the final column. That is the ambiguity the
author flagged. Everything else in the candidate count comes from the post-hoc sort.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import (  # noqa: E402
    Observation,
    candidate_xs,
    column_options,
    text_score,
    verify,
    x_to_text,
)
from tools_shim import obs_from_truth  # noqa: E402

print(
    f"{'case':<30} {'lastcol':>7} {'item5':>6} {'i5_ok':>6} {'i5_txt':>7} "
    f"{'i5_rank':>7} | {'full':>6} {'full_ok':>7} {'ratio':>6}"
)
print("-" * 96)

for path in sorted((ROOT / "data" / "truth").glob("*.json")):
    t = json.loads(path.read_text(encoding="utf-8"))
    obs = obs_from_truth(t)
    base, x_true = t["base"], int(t["x"])
    asks = [tuple(a) for a in t["asks"]]

    sizes = [len(column_options(obs, c)[0]) for c in range(1, obs.ncols + 1)]
    last = sizes[-1]

    # Prefix sums, keeping only those that end inside the final column.
    x, m = 0, 1
    item5 = []
    for idx, (k, a) in enumerate(asks):
        x += (a - 1) * m
        m *= k
        if idx >= len(asks) - last:
            item5.append(x)
    # Deduplicate: a post-termination answer of 1 contributes (a-1)*M = 0, so X is
    # unchanged and the same candidate would otherwise be counted several times.
    item5 = list(dict.fromkeys(item5))

    ok = [c for c in item5 if verify(c, obs)]
    txt = [(c, x_to_text(c, base, strict=True)) for c in ok]
    txt = [(c, s) for c, s in txt if s is not None]
    txt.sort(key=lambda r: -text_score(r[1]))
    rank = next((i + 1 for i, (c, _) in enumerate(txt) if c == x_true), None)

    full = list(dict.fromkeys(candidate_xs(obs, base=base)))
    full_ok = [c for c in full if verify(c, obs)]
    assert set(item5) <= set(full), "isolated candidates must be a subset of the walk"

    print(
        f"{path.stem:<30} {last:>7} {len(item5):>6} {len(ok):>6} {len(txt):>7} "
        f"{str(rank):>7} | {len(full):>6} {len(full_ok):>7} "
        f"{len(full_ok) / max(len(ok), 1):>6.0f}x"
    )
