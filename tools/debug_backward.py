"""Two things the backward search rests on. Check both before building it.

1. The k sequence must be branch-independent, or M_j cannot be computed up front.
2. Going backwards, trailing characters must actually get pinned quickly -- measure
   how many asks from the end it takes to determine the last 1, 2, 3 ... characters.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import column_options  # noqa: E402
from tools_shim import obs_from_truth  # noqa: E402


def digits(x, base):
    out = []
    while x > 0:
        x, r = divmod(x, base)
        out.append(r)
    return out[::-1]  # most significant first


def pinned_trailing_chars(lo, width, base, n_digits):
    """How many leading base-digits of X are constant across [lo, lo + width)."""
    hi = lo + width - 1
    dl, dh = digits(lo, base), digits(hi, base)
    if len(dl) != n_digits or len(dh) != n_digits:
        return 0
    t = 0
    for a, b in zip(dl, dh):
        if a != b:
            break
        t += 1
    return t


print(f"{'case':<30} {'k fixed':>8} {'chars':>6} | asks from end to pin 1,2,3,4 chars")
print("-" * 88)

for path in sorted((ROOT / "data" / "truth").glob("*.json")):
    t = json.loads(path.read_text(encoding="utf-8"))
    obs = obs_from_truth(t)
    base, x_true = t["base"], int(t["x"])
    asks = [tuple(a) for a in t["asks"]]

    # 1. every option in every column must carry the same k vector
    k_fixed = True
    ks = []
    for col in range(1, obs.ncols + 1):
        opts = column_options(obs, col)
        kvecs = {tuple(k for k, _ in o) for o in opts}
        if len(kvecs) != 1:
            k_fixed = False
        ks.extend(k for k, _ in opts[0])

    # M_i from the k sequence alone
    M = [1]
    for k in ks:
        M.append(M[-1] * k)

    # locate the true termination step
    x = 0
    n = None
    for i, (k, a) in enumerate(asks):
        x += (a - 1) * M[i]
        if x == x_true and n is None:
            n = i
    L = len(digits(x_true, base))

    # 2. walk backwards from n, tracking how tight the interval on X has become
    need = {}
    S = 0
    for j in range(n, -1, -1):
        S += (asks[j][1] - 1) * M[j]
        pins = pinned_trailing_chars(S, M[j], base, L)
        for c in range(1, 5):
            if pins >= c and c not in need:
                need[c] = n - j + 1

    print(
        f"{path.stem:<30} {str(k_fixed):>8} {L:>6} | "
        + ", ".join(str(need.get(c, "-")) for c in range(1, 5))
    )
