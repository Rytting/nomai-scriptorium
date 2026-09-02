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
| `src/nomai/codec.py` | the read/write API |

Two dialects share every glyph and every drawing rule:

* **upstream** — exactly what NomaiText.jl draws. It is lossy in three places, so a
  drawing can have several valid readings (`hi` and `&i` render identically). Use it
  to read anything the author's code or nomai-writing.com produced.
* **strict** — the same drawings, numbered differently so the map is injective.
  Decoding is then a linear replay with no search and no language prior.

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
```

Run them from PowerShell — Git Bash's cp1252 console cannot print the CJK in the
output.

`log.md` is the working record: what was measured, and which wrong turns cost time.
