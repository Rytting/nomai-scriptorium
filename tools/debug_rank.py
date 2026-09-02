import json, sys
from pathlib import Path
ROOT = Path(r"D:\nomai-translator-project")
sys.path.insert(0, str(ROOT / "src"))
from nomai.decode import decode_backward, text_score
from nomai.oracle import UPSTREAM
from nomai.vision import analyze
SVG = ROOT / "data" / "svg"
man = {e["file"]: e for e in json.loads((SVG / "manifest.json").read_text(encoding="utf-8"))}
for name in ("s020.svg", "s026.svg", "s055.svg"):
    e = man[name]
    obs = analyze(SVG / name)
    res = decode_backward(obs, bases=(e["base"],), dialect=UPSTREAM)
    print(f"{name}  base={e['base']}")
    print(f"   true : {e['message']!r}")
    for i, (_b, _x, t) in enumerate(res[:3], 1):
        mark = "  <- true" if t == e["message"] else ""
        print(f"   #{i}   : {t!r}  score={text_score(t):.3f}{mark}")
    rank = next((i for i, (_b, _x, t) in enumerate(res, 1) if t == e["message"]), None)
    print(f"   true message ranked #{rank} of {len(res)}")
