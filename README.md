# Nomai text: a decoder

Reads the procedural Nomai writing produced by
[evanfields/NomaiText.jl](https://github.com/evanfields/NomaiText.jl) back into text,
and writes an unambiguous variant of it.

Upstream is MIT licensed and is not vendored into this repository's history; it is
cloned into `vendor/` and pinned to commit `b8ca259`:

```
git clone https://github.com/evanfields/NomaiText.jl.git vendor/NomaiText.jl
git -C vendor/NomaiText.jl checkout b8ca259
```

The 33 glyph shapes in `data/glyphs.json` are exported from that package, so they are
derived from its author's work — hand-traced, in turn, from *Outer Wilds*.

## What is here

| | |
|---|---|
| `src/nomai/oracle.py` | the message integer, and the two dialects |
| `src/nomai/gridgen.py` | a bit-exact Python port of upstream's `glyphgrid.jl` |
| `src/nomai/decode.py` | replay decoder: grid structure back to text |
| `src/nomai/vision.py` | SVG drawing back to grid structure, no ML |
| `src/nomai/scroll.py` | a conversation on one sheet: layout, joins, segmentation |
| `src/nomai/codec.py` | the read/write API |
| `web/` | the same thing in JavaScript, as a page that needs no server |

Two dialects share every glyph and every drawing rule:

* **upstream** — exactly what NomaiText.jl draws. It is lossy in three places, so a
  drawing can have several valid readings (`hi` and `&i` render identically). Use it
  to read anything the author's code or nomai-writing.com produced.
* **strict** — the same drawings, numbered differently so the map is injective.
  Decoding is then a linear replay with no search and no language prior.

## Scrolls

A scroll is one drawing holding a conversation: a root spiral plugged into a socket at
the bottom of the sheet, with replies growing off whichever spiral they answer.

```python
from nomai.codec import write_scroll, read_scroll

svg = write_scroll([
    ("Come to the Ash Twin Project", "Poke", None),   # the root
    ("I will wait", "Solanum", 0),                    # answers spiral 0
    ("why", "Poke", 1),                               # answers spiral 1
], handwriting=0.15)

records, tree_ok, why = read_scroll(svg)
```

Layout is automatic. A reply goes anywhere on its parent with room for it, and may
wind the other way or coil differently to fit -- a real Nomai wall has both. The
writer draws each candidate placement on its own and reads it back before keeping it,
so a placement the reader would get wrong is never shipped.

Reading one back turns on a single detail: a reply is joined to its parent by an
ordinary connection line with **one dot at its midpoint**. Nothing else in a drawing
puts a dot in the middle of a two-point stroke -- connections dot their ends, glyphs
dot their vertices -- so cutting the beaded lines separates the spirals cleanly and
the ordinary reader then runs on each unchanged. Each reply also records *which*
spiral it answers, which is used to check the tree the geometry gives rather than to
supply it.

`python tools/check_scroll.py` round trips four conversation shapes across both
windings and three tightnesses: 21 of 24. The three that fail are the same per-drawing
limits the single-spiral reader has, on the root spiral, whose winding and coil the
layout is not free to change.

## Handwriting

`handwriting` jitters the strokes to look hand drawn. It also costs accuracy when
the drawing is read back, so there is a ceiling (`tools/hw_sweep.py`, strict dialect
round trip):

| handwriting | exact round trip |
|---|---|
| 0 | 20/20 |
| 0.1 | 20/20 |
| **0.2** | **19/20** |
| 0.3 | 16/20 |
| 0.6 | 15/20 |

**Keep it at 0.2 or below** for anything meant to be read back. Note that
nomai-writing.com sends 0.3, right at the edge -- part of why reading its output is
harder than reading our own.

The ceiling is a limitation of this decoder, not of the drawing. At 0.6 each point
moves about 0.6 units against glyph features of 20 to 40, so the shape is still
plainly there; the losses come from fitting each glyph independently instead of
using the fact that every glyph in a column shares one scale and one rotation.

## Running things

Julia is needed only to regenerate fixtures; everything else is Python.

```
julia tools/export_truth.jl          # glyph coordinates + ground-truth ask logs
julia tools/gen_samples.jl           # a corpus of real SVGs to test against
python tools/validate.py             # port, ask sequence, decoder: 12/12
python tools/strict_roundtrip.py     # strict dialect round trip: 600/600
python tools/batch_svg.py            # SVG in, text out, across the corpus
python tools/check_shape.py          # tilt, winding, tightness: 72/72
python tools/check_scroll.py         # conversations, written and read back: 21/24
```

Run them from PowerShell — Git Bash's cp1252 console cannot print the CJK in the
output.

`log.md` is the working record: what was measured, and which wrong turns cost time.
