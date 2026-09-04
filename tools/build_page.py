"""Inline the glyph table into the page so it ships as one self-contained file."""
import json
import pathlib
import subprocess
from urllib.parse import quote

ROOT = pathlib.Path(__file__).resolve().parents[1]
src = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
data = (ROOT / "web" / "glyphs.min.json").read_text(encoding="utf-8")
marker = "/*__GLYPHS__*/null"
assert src.count(marker) == 1, "glyph placeholder missing (already built?)"
out = ROOT / "web" / "nomai-scriptorium.html"
read_js = (ROOT / "web" / "read.js").read_text(encoding="utf-8")
assert src.count("/*__READ__*/") == 1, "read placeholder missing"
built = src.replace(marker, data).replace("/*__READ__*/", read_js)
for name, count in (("write-icon", 1), ("read-icon", 1), ("curl-icons", 2)):
    icon = (ROOT / "assets" / "icons" / f"{name}.svg").read_text(encoding="utf-8")
    # Inline the geometry so the downloadable HTML needs no external icon files.
    group = icon[icon.index("<g "):icon.index("</g>") + 4].replace(' id="icon"', '')
    ref = f'<use href="../assets/icons/{name}.svg#icon"/>'
    assert src.count(ref) == count, f"{name} icon placeholder count mismatch"
    built = built.replace(ref, group)
for texture_name in ("writing-tablet.svg", "writing-tablet-pressed.svg", "vessel-etching.svg"):
    texture_ref = f'../assets/textures/{texture_name}'
    texture = (ROOT / "assets" / "textures" / texture_name).read_text(encoding="utf-8")
    assert built.count(texture_ref) == 1, f"{texture_name} reference missing"
    built = built.replace(texture_ref, 'data:image/svg+xml,' + quote(texture, safe=''))
# Which build this is, so a page can say so. A copy saved to disk has no server to
# ask, which is the whole reason the recorder is worth having.
rev = subprocess.run(["git", "log", "-1", "--format=%h"], cwd=ROOT,
                     capture_output=True, text=True)
day = subprocess.run(["git", "log", "-1", "--format=%cs"], cwd=ROOT,
                     capture_output=True, text=True)
stamp = '{ rev: "%s", date: "%s" }' % (rev.stdout.strip() or "dev", day.stdout.strip())
assert built.count("/*__BUILD__*/") == 1, "build placeholder missing"
built = built.replace('/*__BUILD__*/{ rev: "dev", date: "" }', "/*__BUILD__*/" + stamp)

out.write_text(built, encoding="utf-8")
print(f"wrote {out.relative_to(ROOT)}  {len(out.read_text(encoding='utf-8')):,} bytes")
