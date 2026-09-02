"""Why does the parser see nothing in one SVG flavour?"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.svgparse import _D_RE, _PATH_RE, parse_svg  # noqa: E402

for label, path in (
    ("hosted API", ROOT / "assets" / "samples" / "hello_base200000_seed47.svg"),
    ("local julia", ROOT / "data" / "svg" / "s001.svg"),
):
    raw = path.read_text(encoding="utf-8")
    if raw.lstrip().startswith('"'):
        raw = json.loads(raw)
    tags = _PATH_RE.findall(raw)
    print(f"\n=== {label}: {path.name}")
    print(f"  <path tags matched: {len(tags)}")
    if tags:
        a = tags[0]
        m = _D_RE.search(a)
        print(f"  attrs[:150]: {a[:150]!r}")
        print(f"  first d= match: {m.group(1)[:50]!r}" if m else "  no d= found")
        print(f"  'stroke-width' present: {'stroke-width' in a}")
    st, ci = parse_svg(path)
    print(f"  parse_svg -> strokes={len(st)} circles={len(ci)}")
