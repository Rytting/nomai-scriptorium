"""Why does strict decoding fail to be unique at base 200000?

Branchy columns are already zero, so the only multiplicity left is the termination
position -- the leading length digit was meant to rule those out.
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import Observation, _plan, verify, x_to_text  # noqa: E402
from nomai.gridgen import grid_from_message  # noqa: E402
from nomai.oracle import STRICT, decode_int, encode  # noqa: E402

WORDS = "the nomai came to this solar system searching for eye of universe".split()
BASE = 200_000


def english(rng, n):
    out = []
    while sum(len(w) + 1 for w in out) < n + 8:
        out.append(rng.choice(WORDS))
    return " ".join(out)[:n].strip()


rng = random.Random(7 * 12 + BASE)
shown = 0
for _ in range(30):
    msg = english(rng, 12)
    x_true = encode(msg, BASE, STRICT)
    obs = Observation.from_grid(grid_from_message(msg, BASE, STRICT))
    cols, M = _plan(obs, STRICT)
    seq = [(k, a) for (_, kv, ans) in cols for k, a in zip(kv, ans[0])]
    last_start = cols[-1][0]
    x, cands = 0, []
    for i, (k, a) in enumerate(seq):
        x += (a - 1) * M[i]
        if i >= last_start:
            cands.append(x)
    cands = list(dict.fromkeys(cands))

    kept = []
    for c in cands:
        cps = decode_int(c, BASE, STRICT)
        kept.append((c, cps is not None, x_to_text(c, BASE, False, STRICT) is not None,
                     verify(c, obs, STRICT)))
    survivors = [c for c, _, t, v in kept if t and v]
    if len(survivors) == 1 and survivors[0] == x_true:
        continue
    if shown >= 3:
        continue
    shown += 1
    print(f"\nmessage {msg!r}  len={len(msg)}  X_true={x_true}")
    print(f"  final column holds {len(cands)} distinct candidates, "
          f"{len(survivors)} survive")
    for c, ok_int, ok_txt, ok_ver in kept:
        cps = decode_int(c, BASE, STRICT)
        tag = "TRUE " if c == x_true else "     "
        print(f"  {tag}len_prefix_ok={ok_int!s:>5} text_ok={ok_txt!s:>5} "
              f"verify={ok_ver!s:>5}  ndigits={len(str(c))}  "
              f"decoded={None if cps is None else ''.join(chr(p) for p in cps)!r}")
