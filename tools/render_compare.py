"""Render a message ourselves and compare the canvas with what Julia produced."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.glyphs import KNOWN_GLYPHS
from nomai.gridgen import grid_from_message
from nomai.oracle import UPSTREAM
from nomai.render import render_grid

SVG = ROOT / "data" / "svg"
manifest = json.loads((SVG / "manifest.json").read_text(encoding="utf-8"))
print(f"{'file':>9} {'cols':>5} {'julia canvas':>18} {'ours':>18} {'ratio':>12}")
print("-" * 68)
for entry in manifest[:1] + [e for e in manifest if e["handwriting"] == 0.0][:7]:
    raw = (SVG / entry["file"]).read_text(encoding="utf-8")
    m = re.search(r'width="([\d.]+)"[^>]*height="([\d.]+)"', raw)
    jw, jh = float(m.group(1)), float(m.group(2))
    gg = grid_from_message(entry["message"], entry["base"], UPSTREAM)
    svg = render_grid(gg, KNOWN_GLYPHS)
    m2 = re.search(r'width="([\d.]+)" height="([\d.]+)"', svg)
    ow, oh = float(m2.group(1)), float(m2.group(2))
    print(f"{entry['file']:>9} {gg.ncols:>5} {jw:>8.1f} x{jh:>8.1f} "
          f"{ow:>8.1f} x{oh:>8.1f} {ow / jw:>6.3f} {oh / jh:>5.3f}")
