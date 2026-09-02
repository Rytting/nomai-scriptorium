"""Forward exhaustive search vs backward beam search, as messages get longer.

The port is bit-exact against Julia (tools/validate.py), so grids for arbitrary
messages can be generated in Python and fed straight back to the decoder.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import (  # noqa: E402
    Observation,
    candidate_xs,
    column_options,
    decode,
    decode_backward,
)
from nomai.gridgen import grid_from_message  # noqa: E402

SAMPLE = (
    "The Nomai came to this solar system searching for the Eye of the Universe, a "
    "signal older than the universe itself, and they never did find it. They built "
    "the Ash Twin Project to send memories back through time, and then the ghost "
    "matter killed every last one of them before it ever ran."
)
LENGTHS = [10, 20, 40, 60, 80, 120, 160, 240]
FWD_CAP = 300_000  # give up on the exhaustive walk past this many candidates

print(f"{'base':>7} {'len':>4} {'cols':>5} {'asks':>5} {'branchy':>8} | "
      f"{'fwd cand':>9} {'fwd s':>7} {'fwd':>4} | {'bwd hits':>8} {'bwd s':>7} {'bwd':>4}")
print("-" * 92)

for base in (256, 200_000):
    fwd_dead = False
    for n in LENGTHS:
        msg = SAMPLE[:n]
        gg = grid_from_message(msg, base)
        obs = Observation.from_grid(gg)
        cols = [column_options(obs, c) for c in range(1, obs.ncols + 1)]
        branchy = sum(1 for o in cols if len(o) > 1)
        asks = sum(len(o[0]) for o in cols)

        # forward, exhaustive
        if fwd_dead:
            fwd_cand, fwd_t, fwd_ok = None, None, None
        else:
            t0 = time.perf_counter()
            fwd_cand, overflow = 0, False
            for _ in candidate_xs(obs, base=base):
                fwd_cand += 1
                if fwd_cand > FWD_CAP:
                    overflow = True
                    break
            if overflow:
                fwd_cand, fwd_t, fwd_ok = None, time.perf_counter() - t0, None
                fwd_dead = True
            else:
                res = decode(obs, bases=(base,))
                fwd_ok = bool(res) and res[0][2] == msg
                fwd_t = time.perf_counter() - t0

        # backward, beam
        t0 = time.perf_counter()
        bwd = decode_backward(obs, bases=(base,))
        bwd_t = time.perf_counter() - t0
        bwd_ok = bool(bwd) and bwd[0][2] == msg

        def fmt(v, spec):
            return "  -  " if v is None else format(v, spec)

        print(
            f"{base:>7} {n:>4} {obs.ncols:>5} {asks:>5} {branchy:>8} | "
            f"{fmt(fwd_cand, '>9') if fwd_cand is not None else ('>' + str(FWD_CAP)):>9} "
            f"{fmt(fwd_t, '>7.1f')} {('  -  ' if fwd_ok is None else (' ok ' if fwd_ok else 'FAIL')):>4} | "
            f"{len(bwd):>8} {bwd_t:>7.1f} {(' ok ' if bwd_ok else 'FAIL'):>4}"
        )
