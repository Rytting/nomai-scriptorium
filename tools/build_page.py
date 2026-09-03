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
for name in ("write", "read"):
    icon = (ROOT / "assets" / "icons" / f"{name}-icon.svg").read_text(encoding="utf-8")
    # Inline the geometry so the downloadable HTML needs no external icon files.
    group = icon[icon.index("<g "):icon.index("</g>") + 4].replace(' id="icon"', '')
    ref = f'<use href="../assets/icons/{name}-icon.svg#icon"/>'
    assert src.count(ref) == 1, f"{name} icon placeholder missing"
    built = built.replace(ref, group)
out.write_text(built, encoding="utf-8")
print(f"wrote {out.relative_to(ROOT)}  {len(out.read_text(encoding='utf-8')):,} bytes")
