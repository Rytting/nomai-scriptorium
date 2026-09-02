"""Why do 'hi' and '&i' draw identically? Trace both Oracles side by side."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import Observation  # noqa: E402
from nomai.gridgen import grid_from_oracle  # noqa: E402
from nomai.oracle import Oracle  # noqa: E402


class LoggingOracle(Oracle):
    def __init__(self, x):
        super().__init__(x)
        self.log = []

    def ask(self, k):
        before = self.state
        answer = super().ask(k)
        self.log.append((k, answer, before))
        return answer


runs = {}
for msg in ("hi", "&i"):
    o = LoggingOracle(Oracle.from_message(msg, 256).orig_state)
    gg = grid_from_oracle(o)
    runs[msg] = (o, Observation.from_grid(gg))
    print(f"{msg!r}: X = {o.orig_state}")

print()
print(f"{'#':>3} {'k':>4} | {'hi answer':>10} {'hi state':>10} | "
      f"{'&i answer':>10} {'&i state':>10}   same?")
print("-" * 70)
a, b = runs["hi"][0].log, runs["&i"][0].log
for i, ((k1, r1, s1), (k2, r2, s2)) in enumerate(zip(a, b)):
    flag = "yes" if r1 == r2 else "NO"
    print(f"{i:>3} {k1:>4} | {r1:>10} {s1:>10} | {r2:>10} {s2:>10}   {flag}")

print()
print(f"drawings identical: {runs['hi'][1] == runs['&i'][1]}")
