"""Inline the glyph table into the page so it ships as one self-contained file."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
src = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
data = (ROOT / "web" / "glyphs.min.json").read_text(encoding="utf-8")
marker = "/*__GLYPHS__*/null"
assert src.count(marker) == 1, "glyph placeholder missing (already built?)"
out = ROOT / "web" / "nomai-scriptorium.html"
out.write_text(src.replace(marker, data), encoding="utf-8")
print(f"wrote {out.relative_to(ROOT)}  {len(out.read_text(encoding='utf-8')):,} bytes")
