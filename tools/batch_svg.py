"""Decode every generated SVG and report where the pipeline stands.

Each sample is checked in two places: whether `analyze` rebuilds the grid the
generator actually drew (a vision result), and whether the decoder then returns the
message at rank 1 (an end-to-end result). Separating them means a failure says which
half broke.
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import Observation, decode_backward  # noqa: E402
from nomai.gridgen import grid_from_message  # noqa: E402
from nomai.oracle import UPSTREAM  # noqa: E402
from nomai.vision import analyze  # noqa: E402

SVG = ROOT / "data" / "svg"
manifest = json.loads((SVG / "manifest.json").read_text(encoding="utf-8"))

rows = []
for entry in manifest:
    msg, base, hw = entry["message"], entry["base"], entry["handwriting"]
    want = Observation.from_grid(grid_from_message(msg, base, UPSTREAM))
    rec = {"file": entry["file"], "base": base, "hw": hw, "len": len(msg),
           "cols": len(want.paths[0])}
    t0 = time.perf_counter()
    try:
        obs = analyze(SVG / entry["file"])
        rec["vision"] = (
            obs.glyphs == want.glyphs
            and obs.paths == want.paths
            and obs.connections == want.connections
        )
        if not rec["vision"]:
            rec["why"] = (
                "glyphs" if obs.glyphs != want.glyphs
                else "paths" if obs.paths != want.paths
                else "endpoints"
            )
    except Exception as exc:  # noqa: BLE001
        rec["vision"] = False
        rec["why"] = f"{type(exc).__name__}: {str(exc)[:44]}"
        rows.append(rec)
        continue

    try:
        res = decode_backward(obs, bases=(base,), dialect=UPSTREAM)
        rec["top1"] = bool(res) and res[0][2] == msg
        rec["found"] = any(t == msg for _, _, t in res)
    except Exception as exc:  # noqa: BLE001
        rec["top1"] = rec["found"] = False
        rec.setdefault("why", f"decode {type(exc).__name__}: {str(exc)[:38]}")
    rec["sec"] = time.perf_counter() - t0
    rows.append(rec)

print(f"{'file':>9} {'base':>7} {'hw':>4} {'len':>4} {'cols':>5} "
      f"{'vision':>7} {'top1':>6} {'found':>6} {'sec':>6}  note")
print("-" * 76)
for r in rows:
    print(f"{r['file']:>9} {r['base']:>7} {r['hw']:>4} {r['len']:>4} {r['cols']:>5} "
          f"{str(r.get('vision')):>7} {str(r.get('top1')):>6} "
          f"{str(r.get('found')):>6} {r.get('sec', 0):>6.1f}  {r.get('why', '')}")

n = len(rows)
print(f"\nvision exact : {sum(1 for r in rows if r.get('vision'))}/{n}")
print(f"top-1 correct: {sum(1 for r in rows if r.get('top1'))}/{n}")
print(f"message found: {sum(1 for r in rows if r.get('found'))}/{n}")
fails = Counter(r["why"] for r in rows if not r.get("vision"))
if fails:
    print(f"vision failure modes: {dict(fails)}")
by_hw = Counter((r["hw"], bool(r.get("vision"))) for r in rows)
print(f"by handwriting: "
      f"{ {hw: f'{by_hw[(hw, True)]}/{by_hw[(hw, True)] + by_hw[(hw, False)]}' for hw in (0.0, 0.3, 0.6)} }")
