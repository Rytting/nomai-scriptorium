"""Does the Python side write a conversation and read the whole thing back?"""
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.codec import write  # noqa: E402
from nomai.codec import read_strict  # noqa: E402
from nomai.decode import x_to_record  # noqa: E402
from nomai.glyphs import KNOWN_GLYPHS  # noqa: E402
from nomai.oracle import STRICT  # noqa: E402
from nomai.scroll import (  # noqa: E402
    Spiral,
    analyze_scroll,
    check_tree,
    render_scroll,
)

# (text, signature, parent)
CASES = {
    "a fan of three": [
        ("Come to the Ash Twin Project", "Poke", None),
        ("I will wait", "Solanum", 0),
        ("no", "Clary", 0),
        ("why not", "Poke", 2),
    ],
    "a pair": [
        ("The Eye is out there", "Solanum", None),
        ("where", "Poke", 0),
    ],
    "a chain of five": [
        ("a", "", None), ("b", "", 0), ("c", "", 1), ("d", "", 2), ("e", "", 3),
    ],
    "four replies to one": [
        ("one", "", None), ("two", "", 0), ("three", "", 0),
        ("four", "", 0), ("five", "", 0),
    ],
}

BASE = 256
tmp = ROOT / "data" / "strict_svg"
tmp.mkdir(exist_ok=True)

ok = bad = 0
rows = []
for name, spec in CASES.items():
    grids = [write(t, BASE, STRICT, s or None, p) for t, s, p in spec]
    for flip in (1, -1):
        for tight in (0.2, 0.29, 0.5):
            spirals = [Spiral(g, p) for g, (_, _, p) in zip(grids, spec)]
            t0 = time.time()
            try:
                svg = render_scroll(spirals, KNOWN_GLYPHS, 0.15, 47, flip, tight)
                (tmp / "scroll.svg").write_text(svg, encoding="utf-8")
                obs, edges, joins = analyze_scroll(svg)
                got, parents = [], []
                for o in obs:
                    r = read_strict(o, bases=(BASE,))
                    if len(r) != 1:
                        got.append(None)
                        parents.append(None)
                        continue
                    rec = x_to_record(r[0][1], BASE, False, STRICT)
                    got.append(rec)
                    parents.append(rec[2] if rec else None)
                tree_ok, why = check_tree(edges, parents, len(obs))
                same = len(got) == len(spec) and all(
                    g is not None and g[1] == t and (g[0] or "") == s and g[2] == p
                    for g, (t, s, p) in zip(got, spec)
                )
                good = same and tree_ok
                note = "" if good else (why or "text or parent differs")
            except Exception as exc:  # noqa: BLE001
                good, note = False, f"{type(exc).__name__}: {exc}"
                joins = []
            ms = int((time.time() - t0) * 1000)
            ok, bad = (ok + 1, bad) if good else (ok, bad + 1)
            rows.append((name, flip, tight, len(spec), len(joins), ms, good, note))

w = max(len(r[0]) for r in rows)
print(f"{'case':<{w}}  flip  tight  spirals  joins   ms  result")
print("-" * (w + 46))
for name, flip, tight, n, j, ms, good, note in rows:
    mark = "ok" if good else "FAIL " + note[:44]
    print(f"{name:<{w}}  {flip:>4}  {tight:>5}  {n:>7}  {j:>5}  {ms:>4}  {mark}")
print(f"\n{ok} ok, {bad} failed")
