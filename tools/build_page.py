"""Inline what each page needs so it ships as one self-contained file.

Two pages are built: the scriptorium, which carries the glyph table and the reader,
and the repository, which carries the corpus. Both are meant to survive being saved
to a disk and opened from a double click, where there is no server to fetch from.
"""
import json
import argparse
from datetime import date
import base64
import pathlib
import subprocess
from urllib.parse import quote

ROOT = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--release-version', help='Stamp a release before its final commit is tagged')
args = parser.parse_args()
src = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
data = (ROOT / "web" / "glyphs.min.json").read_text(encoding="utf-8")
marker = "/*__GLYPHS__*/null"
assert src.count(marker) == 1, "glyph placeholder missing (already built?)"
out = ROOT / "web" / "nomai-scriptorium.html"
read_js = (ROOT / "web" / "read.js").read_text(encoding="utf-8")
assert src.count("/*__READ__*/") == 1, "read placeholder missing"
built = src.replace(marker, data).replace("/*__READ__*/", read_js)
labels = (ROOT / "web" / "corpus-labels.js").read_text(encoding="utf-8")
built = built.replace('<script src="corpus-labels.js"></script>', '<script>' + labels + '</script>')
corpus = (ROOT / "docs" / "nomai_corpus.json").read_text(encoding="utf-8")
assert built.count("/*__RANDOM_CORPUS__*/null") == 1
built = built.replace("/*__RANDOM_CORPUS__*/null", corpus)
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
# `git describe` rather than a bare hash: a hash cannot be compared by eye, and a
# hand-kept version number is forgotten and then confidently wrong. A tag is decided
# once, by hand, when a stage is finished; everything between two of them reads as
# "v1.0, seven commits on, at 6fc2153", which is the one thing a plain version number
# cannot say about itself.
# (no --dirty: building is itself what dirties the tree, so it would always say so)
rev = subprocess.run(["git", "describe", "--tags", "--always"], cwd=ROOT,
                     capture_output=True, text=True)
day = subprocess.run(["git", "log", "-1", "--format=%cs"], cwd=ROOT,
                     capture_output=True, text=True)
stamp = json.dumps(dict(rev=args.release_version or rev.stdout.strip() or 'dev',
                        date=date.today().isoformat() if args.release_version else day.stdout.strip()))
assert built.count("/*__BUILD__*/") == 1, "build placeholder missing"
built = built.replace('/*__BUILD__*/{ rev: "dev", date: "" }', "/*__BUILD__*/" + stamp)

def report(path):
    print(f"wrote {path.relative_to(ROOT)}  "
          f"{len(path.read_text(encoding='utf-8')):,} bytes")


out.write_text(built, encoding="utf-8")
report(out)

# The repository is the same trick with a different payload. Over file:// a fetch is
# refused by CORS, so the unbuilt page opens to "could not load" and nothing else --
# which is exactly what it looks like when somebody double-clicks the source.
repo_src = (ROOT / "web" / "repository.html").read_text(encoding="utf-8")
repo_src = repo_src.replace('<script src="corpus-labels.js"></script>', '<script>' + labels + '</script>')
boot_image = base64.b64encode((ROOT / "assets" / "outer-wilds-ventures-reference.jpg").read_bytes()).decode("ascii")
repo_src = repo_src.replace("../assets/outer-wilds-ventures-reference.jpg", "data:image/jpeg;base64," + boot_image)
corpus = (ROOT / "docs" / "nomai_corpus.json").read_text(encoding="utf-8")
corpus_marker = "/*__CORPUS__*/null"
assert repo_src.count(corpus_marker) == 1, "corpus placeholder missing (already built?)"
repo_out = ROOT / "web" / "nomai-repository.html"
repo_out.write_text(repo_src.replace(corpus_marker, corpus), encoding="utf-8")
report(repo_out)
