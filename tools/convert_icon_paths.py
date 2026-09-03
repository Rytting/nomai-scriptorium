"""Convert Photoshop's Illustrator path exports to filled, reusable SVG icons.

Usage: python tools/convert_icon_paths.py input.ai output.svg
Only path geometry is consumed; PostScript is never executed.
"""
import argparse
import pathlib
import re


def convert(source):
    bounds = re.search(r"%%HiResBoundingBox: ([^\r\n]+)", source)
    if not bounds:
        raise ValueError("Missing high-resolution bounds")
    x0, y0, x1, y1 = map(float, bounds[1].split())
    commands = []
    current = None
    active = False
    subpaths = 0
    for line in source.splitlines():
        if line.startswith("%Adobe_Photoshop_Path_Begin"):
            active = True
        elif line.startswith("%Adobe_Photoshop_Path_End"):
            active = False
        if not active or not line or line.startswith(("%", "*")):
            continue
        parts = line.split()
        op = parts[-1]
        if op == "XR":
            if parts != ["1", "XR"]:
                raise ValueError("Only even-odd compound paths are supported")
            continue
        if op.lower() in ("n", "h"):
            if current is not None:
                commands.append("Z")
                current = None
            continue
        vals = list(map(float, parts[:-1]))
        if op.lower() == "m" and len(vals) == 2:
            commands.append("M" + " ".join(parts[:-1]))
            subpaths += 1
        elif op.lower() == "l" and len(vals) == 2:
            commands.append("L" + " ".join(parts[:-1]))
        elif op.lower() == "c" and len(vals) == 6:
            commands.append("C" + " ".join(parts[:-1]))
        elif op.lower() == "v" and len(vals) == 4 and current is not None:
            commands.append("C" + " ".join(map(str, [*current, *vals])))
        elif op.lower() == "y" and len(vals) == 4:
            commands.append("C" + " ".join(map(str, [*vals, *vals[-2:]])))
        else:
            raise ValueError(f"Unsupported path command: {line}")
        current = vals[-2:]
    if current is not None:
        commands.append("Z")
    if not subpaths:
        raise ValueError("No paths found")
    width, height = x1 - x0, y1 - y0
    # Illustrator's Y axis points up; SVG's points down. Even-odd keeps holes.
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}">\n'
            f'  <g id="icon" fill="currentColor" fill-rule="evenodd" '
            f'transform="translate({-x0:g} {y1:g}) scale(1 -1)">\n'
            f'    <path d="{" ".join(commands)}"/>\n'
            '  </g>\n</svg>\n'), subpaths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    svg, count = convert(args.source.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    print(f"{args.output}: {count} subpaths")
