"""Validate the Python port and the replay decoder against Julia-generated truth.

Four independent checks per case:

  port    our generator reproduces the exact grid the real NomaiText.jl produced
  asks    our generator asks the same (k, answer) sequence, question for question
  der     the decoder re-derives that same sequence from the *structure* alone,
          which is the part `asks` does not cover: `asks` validates the port,
          `der` validates the decoder
  decode  feeding only the observable structure back in recovers X and the message

Run:  python tools/validate.py
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
    decode,
    decode_backward,
    verify,
)
from nomai.gridgen import grid_from_oracle  # noqa: E402
from nomai.oracle import Oracle  # noqa: E402


class LoggingOracle(Oracle):
    """Oracle that records every (k, answer) so we can diff against Julia's log."""

    def __init__(self, x):
        super().__init__(x)
        self.log = []

    def ask(self, k):
        answer = super().ask(k)
        self.log.append((k, answer))
        return answer


def asks_to_list(seq):
    return [list(a) for a in seq]


def obs_from_truth(truth) -> Observation:
    grid = truth["grid"]
    return Observation(
        glyphs={(e["i"], e["j"]): e["glyph"] for e in grid["glyphs"]},
        paths=[[tuple(c) for c in p] for p in grid["paths"]],
        connections={
            (tuple(c["coord1"]), tuple(c["coord2"])): (tuple(c["pt1"]), tuple(c["pt2"]))
            for c in grid["connections"]
        },
    )


def first_divergence(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i, x, y
    if len(a) != len(b):
        return min(len(a), len(b)), "<end>" if len(a) < len(b) else a[len(b)], (
            "<end>" if len(b) < len(a) else b[len(a)]
        )
    return None


def run_case(path: Path):
    truth = json.loads(path.read_text(encoding="utf-8"))
    msg, base, x_true = truth["message"], truth["base"], int(truth["x"])
    truth_asks = [tuple(a) for a in truth["asks"]]
    obs = obs_from_truth(truth)
    row = {"case": path.stem, "message": msg, "base": base,
           "cols": obs.ncols, "asks": len(truth_asks)}

    # 1. port fidelity
    oracle = LoggingOracle(x_true)
    gg = grid_from_oracle(oracle)
    ours = Observation.from_grid(gg)
    row["port"] = (
        ours.glyphs == obs.glyphs
        and ours.paths == obs.paths
        and set(ours.connections) == set(obs.connections)
    )

    # 2. ask-sequence fidelity
    row["asks_ok"] = oracle.log == truth_asks
    if not row["asks_ok"]:
        row["diverge"] = first_divergence(oracle.log, truth_asks)

    # 3. derivation fidelity: the true ask sequence must be among the sequences
    # column_options enumerates from the structure. Checking the generator's log
    # (step 2) does not cover this -- that is the port, this is the decoder.
    pos, derived_ok = 0, True
    for col in range(1, obs.ncols + 1):
        opts = column_options(obs, col)
        n = len(opts[0])
        if asks_to_list(truth_asks[pos : pos + n]) not in [
            asks_to_list(o) for o in opts
        ]:
            derived_ok = False
            row["derive_col"] = col
            break
        pos += n
    row["derived"] = derived_ok

    # 4. decoding, from the observable structure alone
    row["branches"] = sum(1 for _ in candidate_xs(obs, base=base))
    results = decode(obs, bases=(base,))
    row["n_results"] = len(results)
    row["decoded"] = any(x == x_true and text == msg for _, x, text in results)
    row["rank"] = next(
        (i + 1 for i, (_, x, _) in enumerate(results) if x == x_true), None
    )
    row["texts"] = [t for _, _, t in results][:3]

    # 5. the backward beam search must reach the same answer
    bwd = decode_backward(obs, bases=(base,))
    row["bwd_hits"] = len(bwd)
    row["bwd"] = bool(bwd) and bwd[0][1] == x_true and bwd[0][2] == msg
    return row


def main() -> int:
    truth_dir = ROOT / "data" / "truth"
    files = sorted(truth_dir.glob("*.json"))
    if not files:
        print(f"no truth files in {truth_dir} -- run `julia tools/export_truth.jl`")
        return 1

    rows = [run_case(f) for f in files]
    width = max(len(r["case"]) for r in rows)
    hdr = (
        f"{'case':<{width}}  {'cols':>4} {'asks':>5} {'cand':>5} {'hits':>4} "
        f"{'rank':>4} {'bwd#':>5}  port asks der dec bwd  top results"
    )
    print(hdr)
    print("-" * len(hdr))
    ok = True
    for r in rows:
        mark = lambda b: " ok " if b else "FAIL"  # noqa: E731
        ok &= (r["port"] and r["asks_ok"] and r["derived"]
               and r["decoded"] and r["bwd"])
        print(
            f"{r['case']:<{width}}  {r['cols']:>4} {r['asks']:>5} {r['branches']:>5} "
            f"{r['n_results']:>4} {str(r['rank']):>4} {r['bwd_hits']:>5}  "
            f"{mark(r['port'])} {mark(r['asks_ok'])} {mark(r['derived'])} "
            f"{mark(r['decoded'])} {mark(r['bwd'])}  {r['texts']}"
        )
        if "derive_col" in r:
            print(f"    derivation failed at column {r['derive_col']}")
        if "diverge" in r and r["diverge"]:
            i, mine, theirs = r["diverge"]
            print(f"    ask #{i}: ours={mine} julia={theirs}")
    print()
    print("ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
