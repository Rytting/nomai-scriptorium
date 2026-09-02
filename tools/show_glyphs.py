"""Draw all 33 glyphs on one sheet -- the alphabet the author traced from the game."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.glyphs import KNOWN_GLYPHS
from nomai.render import document, glyph_svg, similarity

CELL = 130
COLS = 6
rows = (len(KNOWN_GLYPHS) + COLS - 1) // COLS
W, H = COLS * CELL, rows * CELL

els = []
for idx, g in enumerate(KNOWN_GLYPHS):
    cx = (idx % COLS) * CELL + CELL / 2
    cy = (idx // COLS) * CELL + CELL / 2
    els.extend(glyph_svg(g, similarity(1.6, 0.0, (cx, cy))))

out = ROOT / "assets" / "glyph-sheet.svg"
out.write_text(document(els, W, H), encoding="utf-8")
print(f"wrote {out.relative_to(ROOT)}  ({len(KNOWN_GLYPHS)} glyphs, {W}x{H})")
