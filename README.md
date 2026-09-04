# Nomai Scriptorium

**[Write something in Nomai &rarr;](https://rytting.github.io/nomai-scriptorium/)**
&nbsp;&nbsp;No install, no server, nothing leaves the page.

![Four Nomai spirals joined into one scroll: a child's questions about the Eye of the
Universe, drawn in the procedural script from Outer Wilds](assets/readme/scroll.png)

That drawing is a conversation. Four spirals, three of them replies, plugged into one
socket &mdash; and it can be read back into the sentences it was made from, exactly,
by anyone with the page and nothing else.

The writing is the one from *Outer Wilds*. What is ours is a change to how it is
numbered: in the original, one drawing has many possible readings and none of them is
*the* reading. Here every question the drawing answers has a single possible answer,
so a sentence goes in and the same sentence comes out. Any language, either direction,
in one HTML file.

- **Write** a sentence, sign it, and watch the spiral unwind.
- **Reply** to a spiral and the scroll grows a branch, the way a Nomai wall does.
- **Read** a scroll somebody else drew &mdash; hold the translator against it and the
  lines come back one at a time. Replies stay hidden until you have read what they
  answer.
- **Take one off the wall**: six walls from the game, verbatim, in English and Chinese.

## How this was made

Written by a person and an AI together, in the open. The direction, the art and most
of the defects found are the author's; most of the code is the model's. Every decision
and every mistake is written down as it happened in [`log.md`](log.md) &mdash; including
the ones that were shipped and caught later, which are the interesting ones.

## Where it comes from

Upstream is MIT licensed and is not vendored into this repository's history; it is
cloned into `vendor/` and pinned to commit `b8ca259`:

```
git clone https://github.com/evanfields/NomaiText.jl.git vendor/NomaiText.jl
git -C vendor/NomaiText.jl checkout b8ca259
```

The 33 glyph shapes in `data/glyphs.json` are exported from
[evanfields/NomaiText.jl](https://github.com/evanfields/NomaiText.jl), so they are
derived from its author's work &mdash; hand-traced, in turn, from *Outer Wilds*. The
mode and coil icons on the page were traced from the game by hand for this project.

*Outer Wilds* is Mobius Digital's. This is a fan project and is not affiliated with
them.

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

The page reads in English or Chinese, switched at the top and remembered, and
starts in whichever the browser asks for. Translations live in one table keyed by
the English string itself, so adding one is a single line and anything missing
simply stays in English.

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
windings and three tightnesses: 24 of 24. `python tools/hunt_branching.py` throws a
wider net -- six shapes against both windings, three coils and two handwriting
levels -- and gets 72 of 72.

What the layout may change to make a spiral readable, and what it may not: the hand
(the jitter seed) is nobody's, so it is searched; the root's angle is nobody's either,
since the whole scroll turns about its socket; a reply's place, side, coil and winding
are the layout's to pick. The root's coil and winding belong to the writer, so if a
drawing cannot be read at the ones asked for, the page says so rather than handing
over something that will not come back.

## Handwriting

`handwriting` jitters the strokes to look hand drawn. It also costs accuracy when the
drawing is read back, so there is a ceiling. Two measurements, and the difference
between them is the point:

| handwriting | 20 chosen messages | 900 random ones |
|---|---|---|
| 0 | 20/20 | **99.5%** |
| 0.1 | 20/20 | **95.5%** |
| 0.15 | — | **92.3%** |
| **0.2** | 19/20 | **88.5%** |
| 0.3 | 16/20 | — |
| 0.6 | 15/20 | — |

The left column is `tools/hw_sweep.py` over messages somebody picked. The right is
`tools/fuzz_roundtrip.py`, which picks the text itself -- lengths from one character
up, mixed case, digits, punctuation, CJK, repeated characters -- and takes each one all
the way through drawing and reading, searching the jitter seed the way the page does.

The chosen messages were flattering. Trust the right-hand column for what a stranger
will run into: at 0.2 roughly one drawing in nine does not come back.

**Keep it at 0.15 or below** for anything meant to be read. nomai-writing.com sends
0.3, well past the edge, which is part of why reading its output is harder than
reading our own.

Note also what `tools/strict_roundtrip.py`'s 600/600 does *not* say. It round trips
through `Observation.from_grid`, which never renders anything: it shows the numbering
is sound, not that a drawing of it comes back.

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
python tools/check_scroll.py         # conversations, written and read back: 24/24
python tools/hunt_branching.py       # a wider net over shapes and settings: 72/72
python tools/fuzz_roundtrip.py 29 900  # random text, drawn and read back: 844/900
python tools/check_canon.py         # the rack's walls, both languages: 12/12 (~8 min)
```

Run them from PowerShell — Git Bash's cp1252 console cannot print the CJK in the
output.

`log.md` is the working record: what was measured, and which wrong turns cost time.
