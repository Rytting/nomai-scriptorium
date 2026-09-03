"""Do the six scrolls on the wall actually etch and read back?

The wall keeps the words, not the drawings, so a canonical scroll is written the
moment somebody takes it down. That makes it a thing that can fail in the reader's
browser rather than here, which is exactly the sort of failure worth catching in
advance. The list is read out of the page itself so there is one copy of it.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.codec import read_strict, write  # noqa: E402
from nomai.decode import x_to_record  # noqa: E402
from nomai.glyphs import KNOWN_GLYPHS  # noqa: E402
from nomai.oracle import STRICT  # noqa: E402
from nomai.scroll import Spiral, analyze_scroll, check_tree, render_scroll  # noqa: E402

# the page's own settings when it etches one of these
HAND, SEED, FLIP, TIGHT = 0.12, 47, 1, 0.29

def read_canon():
    """The wall's list, out of the page it lives in.

    It is JavaScript, so three things stand between it and json: comments, strings
    written in pieces so the lines fit, and unquoted keys. Only the keys of these
    objects get quoted, and only where a brace or a comma puts them -- a blanket
    `word:` rewrite would reach inside the scrolls themselves, which say things like
    "Mission: Science compels us to explode the sun!".
    """
    src = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    block = re.search(r"const CANON = (\[.*?\n\]);", src, re.S).group(1)
    block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    block = re.sub(r'"\s*\+\s*"', "", block)
    block = re.sub(r"([{,]\s*)(where|who|turns)(\s*:)", r'\1"\2"\3', block)
    got = json.loads(block)
    assert all(set(c) == {"where", "who", "turns"} for c in got), got[0]
    return got


CANON = read_canon()

ok = bad = 0
rows = []
for c in CANON:
    spec = [(t, s, p) for t, s, p in c["turns"]]
    base = 200000 if any(ord(ch) >= 256 for t, s, _ in spec for ch in t + s) else 256
    grids = [write(t, base, STRICT, s or None, p) for t, s, p in spec]
    spirals = [Spiral(g, p) for g, (_, _, p) in zip(grids, spec)]
    try:
        svg = render_scroll(spirals, KNOWN_GLYPHS, HAND, SEED, FLIP, TIGHT)
        obs, edges, _joins = analyze_scroll(svg)
        got, parents = [], []
        for o in obs:
            r = read_strict(o, bases=(base,))
            rec = x_to_record(r[0][1], base, False, STRICT) if len(r) == 1 else None
            got.append(rec)
            parents.append(rec[2] if rec else None)
        tree_ok, why = check_tree(edges, parents, len(obs))
        same = len(got) == len(spec) and all(
            g is not None and g[1] == t and (g[0] or "") == s and g[2] == p
            for g, (t, s, p) in zip(got, spec))
        good = same and tree_ok
        note = "" if good else (why or "text or parent differs")
    except Exception as exc:  # noqa: BLE001
        good, note = False, f"{type(exc).__name__}: {exc}"
    ok, bad = (ok + 1, bad) if good else (ok, bad + 1)
    rows.append((c["who"], c["where"], len(spec), good, note))

w = max(len(r[0]) for r in rows)
for who, where, n, good, note in rows:
    print(f"{who:<{w}}  {where:<24}  {n} spirals  "
          + ("ok" if good else "FAIL " + note[:44]))
print(f"\n{ok} ok, {bad} failed")
