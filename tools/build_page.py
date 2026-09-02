"""Inline the glyph table into the page so it ships as one self-contained file."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
src = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
data = (ROOT / "web" / "glyphs.min.json").read_text(encoding="utf-8")
marker = "/*__GLYPHS__*/null"
assert src.count(marker) == 1, "glyph placeholder missing (already built?)"
out = ROOT / "web" / "nomai-scriptorium.html"
read_js = (ROOT / "web" / "read.js").read_text(encoding="utf-8")
assert src.count("/*__READ__*/") == 1, "read placeholder missing"
built = src.replace(marker, data).replace("/*__READ__*/", read_js)
out.write_text(built, encoding="utf-8")
print(f"wrote {out.relative_to(ROOT)}  {len(out.read_text(encoding='utf-8')):,} bytes")
