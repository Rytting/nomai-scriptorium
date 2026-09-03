"""Random text, all the way through: write it, draw it, read the drawing, compare.

Every other test on this path uses messages someone chose, and the two bugs found this
week were both turned up by someone typing something nobody had thought to try. So
this picks the text instead of a person: lengths from one character upward, mixed case,
digits, punctuation, CJK, leading and trailing spaces, repeated characters.

`strict_roundtrip.py` is not this. It round trips through `Observation.from_grid`,
which never renders anything -- it says the *numbering* is sound, not that a drawing of
it comes back.
"""
import pathlib
import random
import sys
import time
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.codec import read_drawing, write  # noqa: E402
from nomai.glyphs import KNOWN_GLYPHS  # noqa: E402
from nomai.oracle import STRICT  # noqa: E402
from nomai.render import render_grid  # noqa: E402

ASCII = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"
PUNCT = " .,!?;:'\"-()[]/@#&*+=<>%$"
CJK = "宇宙眼信号螺旋时间记忆灰烬双子星探索者"


def message(rng):
    kind = rng.random()
    n = rng.choice([1, 1, 2, 3, 5, 8, 12, 20, 30, 45])
    if kind < 0.45:
        pool = ASCII + " "
    elif kind < 0.65:
        pool = ASCII + DIGITS + PUNCT
    elif kind < 0.8:
        pool = PUNCT + DIGITS
    elif kind < 0.92:
        pool = CJK
        n = min(n, 14)
    else:
        return rng.choice("abcxyz") * n
    return "".join(rng.choice(pool) for _ in range(n))


rng = random.Random(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
runs = int(sys.argv[2]) if len(sys.argv) > 2 else 120

ok = raw_ok = rescued = 0
fails = []
by_hw = {h: [0, 0] for h in (0.0, 0.1, 0.15, 0.2)}
by_sig = {False: [0, 0], True: [0, 0]}
by_len = {i: [0, 0] for i in range(5)}
t0 = time.time()
for i in range(runs):
    msg = message(rng)
    sig = rng.choice(["", "", "Poke", "Solanum", "卢"])
    base = 200_000 if any(ord(c) > 255 for c in msg + sig) else rng.choice([256, 200_000])
    flip = rng.choice([1, -1])
    tight = rng.choice([0.15, 0.2, 0.29, 0.4, 0.6])
    hw = rng.choice([0.0, 0.1, 0.15, 0.2])
    tilt = rng.uniform(0, 6.283)
    want = f"{sig}: {msg}" if sig else msg
    by_hw[hw][0] += 1
    by_sig[bool(sig)][0] += 1
    by_len[min(len(msg) // 10, 4)][0] += 1
    def draw_and_read(seed):
        svg = render_grid(grid, KNOWN_GLYPHS, hw, seed, tilt, flip, tight)
        got = read_drawing(svg, bases=(base,))
        return len(got) == 1 and got[0][2] == want, got

    try:
        grid = write(msg, base, STRICT, sig or None)
        good, got = draw_and_read(47)
        if good:
            ok += 1
            raw_ok += 1
            continue
        # what the page does: the hand a spiral is written in is free, so search it
        for k in range(1, 8):
            try:
                good, got = draw_and_read(47 + k * 7919)
            except Exception:  # noqa: BLE001
                continue
            if good:
                break
        if good:
            ok += 1
            rescued += 1
            continue
        why = f"{len(got)} readings" + (f" -> {got[0][2]!r}" if got else "")
    except Exception as exc:  # noqa: BLE001
        why = f"{type(exc).__name__}: {exc}"[:56]
    shown = "".join(c if unicodedata.category(c)[0] != "C" else "?" for c in msg)
    fails.append((shown[:34], sig, base, flip, tight, hw, why))
    by_hw[hw][1] += 1
    by_sig[bool(sig)][1] += 1
    by_len[min(len(msg) // 10, 4)][1] += 1

print(f"{ok}/{runs} round tripped through the drawing   [{time.time() - t0:.0f}s]\n")
def tally(title, d, label):
    print(f"  {title}")
    for k, (n, bad) in sorted(d.items(), key=lambda kv: str(kv[0])):
        if n:
            print(f"     {label(k):<14} {n - bad:>3}/{n:<3}  {(n - bad) / n * 100:5.1f}%")

print("failure rate broken down:")
tally("by handwriting", by_hw, lambda h: f"hw {h}")
tally("by signature", by_sig, lambda b: "signed" if b else "unsigned")
tally("by length", by_len, lambda i: f"{i * 10}-{i * 10 + 9} chars" if i < 4 else "40+ chars")
print()
if fails:
    print(f"{'message':<36} {'sig':<9} base    flip tight hw    why")
    print("-" * 108)
    for msg, sig, base, flip, tight, hw, why in fails[:24]:
        print(f"{msg!r:<36} {sig!r:<9} {base:<7} {flip:>4} {tight:<5} {hw:<5} {why}")
