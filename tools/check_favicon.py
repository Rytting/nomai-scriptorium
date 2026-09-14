"""Check shared favicon references and offline embedding after build_page.py."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "assets" / "icons" / "favicon.svg"


class IconLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and "icon" in attrs.get("rel", "").split():
            self.icons.append(attrs)


icon_text = ICON.read_text(encoding="utf-8")
svg = ET.fromstring(icon_text)
assert svg.tag == "{http://www.w3.org/2000/svg}svg"
assert svg.attrib["viewBox"] == "0 0 100 100"
colors = {element.get("stroke") for element in svg}
assert {"#9667ef", "#f18432"} <= colors, "Both dialogue colors must be present"

for name in ("index.html", "web/index.html", "web/repository.html",
             "web/nomai-scriptorium.html", "web/nomai-repository.html"):
    page = ROOT / name
    parser = IconLinks()
    parser.feed(page.read_text(encoding="utf-8"))
    assert len(parser.icons) == 1, f"{name}: expected one favicon"
    link = parser.icons[0]
    assert link["type"] == "image/svg+xml", name
    assert link["sizes"] == "any", name
    href = link["href"]
    if page.name.startswith("nomai-"):
        prefix = "data:image/svg+xml,"
        assert href.startswith(prefix), f"{name}: favicon must work offline"
        assert unquote(href[len(prefix):]) == icon_text, f"{name}: stale embedded icon"
        mode = "embedded, offline-ready"
    else:
        assert (page.parent / href).resolve() == ICON, f"{name}: wrong icon path"
        mode = "shared SVG"
    print(f"PASS {name}: {mode}")

print("5 favicon page checks passed; SVG geometry and dialogue colors validated.")
