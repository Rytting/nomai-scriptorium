"""Render the same message with both renderers, for a look."""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.glyphs import KNOWN_GLYPHS
from nomai.gridgen import grid_from_message
from nomai.oracle import UPSTREAM
from nomai.render import render_grid

SVG = ROOT / "data" / "svg"
OUT = ROOT / "assets" / "compare"
OUT.mkdir(exist_ok=True)
manifest = json.loads((SVG / "manifest.json").read_text(encoding="utf-8"))

pick = max(
    (e for e in manifest if e["handwriting"] == 0.0 and e["base"] == 256),
    key=lambda e: len(e["message"]),
)
msg, base = pick["message"], pick["base"]
gg = grid_from_message(msg, base, UPSTREAM)
(OUT / "ours.svg").write_text(render_grid(gg, KNOWN_GLYPHS), encoding="utf-8")
shutil.copy(SVG / pick["file"], OUT / "julia.svg")
print(f"message: {msg!r}  base={base}  columns={gg.ncols}  glyphs={len(gg.glyphs)}")
print(f"wrote assets/compare/julia.svg and assets/compare/ours.svg")
