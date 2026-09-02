# 给上游的 issue 草稿

草稿里每一条断言都已在**真实上游源码**（`b8ca259`）上跑过：
`julia tools/verify_upstream_claims.jl` → ALL CLAIMS HOLD（6/6）。
发之前自己再读一遍语气即可。

发到 https://github.com/evanfields/NomaiText.jl/issues

---

**Title:** Distinct messages collide far more often than todo item 5 suggests — the
`sort!` in `next!` is the dominant cause

Hi — I've been writing a decoder for spirals produced by this package, which meant
working out exactly what each `ask!` consumes. Along the way I ran into message
collisions much more often than your `todo.md` item 5 anticipates, and I think the
main cause is a separate one that isn't on the list yet. Sharing in case it's useful.

Everything below was checked against this repo at `b8ca259`.

## Minimal example

`"hi"` and `"&i"` produce the same drawing at base 256:

```julia
using NomaiText
clean(s) = replace(
    draw_spiral(s; base = 256, as_string = true),
    r"id\s*=\s*\"[^\"]*\"" => "id=\"x\"",   # the id is randomised
)
clean("hi") == clean("&i")   # true -- byte-identical, 6170 bytes each
```

Tracing both Oracles side by side:

```
  #    k |  "hi" answer |  "&i" answer
  0   33 |          24  |          24
  1    3 |           2  |           3     <- the two row questions
  2    3 |           3  |           2     <- answers are swapped
  3   33 |          25  |          25     <- states have re-merged
  4   33 |           3  |           3
  5    1 |           1  |           1
  6    1 |           1  |           1
```

(produced by logging `(k, answer)` inside `ask!`)

## Cause 1: `sort!` in `next!` (not currently in todo.md)

```julia
next_pts = [_next_point!(oracle, head) for head in path_heads]
sort!(next_pts; by = coord -> coord[2]) # prevent path X crossings
```

Each path head is asked separately, then the results are sorted. When both heads sit
on the same row the two questions have identical `k`, so swapping their answers gives
a different `x` but an identical drawing. And the states re-converge immediately:
`817 ÷ 3 ÷ 3 == 815 ÷ 3 ÷ 3 == 90`, so everything downstream is identical too.

Both paths start at `STARTING_POINT`, so column 2 always has both heads on the same
row — this fires on essentially every message.

## Cause 2: duplicate pairs in `_shortest_connection!`

`allpoints` concatenates core and annotation points, and annotations are built from
core vertices (`_compute_square` reuses `g.core.points[i]`), so the same point can
appear twice. `_shortest_connection!` can then return the same `(ptA, ptB)` at two
indices: two different Oracle answers, one identical line on the page.

All 17 annotated glyphs (`KNOWN_GLYPHS[17:33]`) repeat at least one point. Scanning
every `(glyphA, glyphB, offset)` combination that can actually arise — 33 x 33 glyph
pairs against the five reachable row offsets, 5445 in total — the tie list contains a
repeated pair in 119 of them.

## Scale

For `"Curious Archaeology"` at base 256 I find **184 distinct integers that produce a
byte-identical drawing**. Splitting the two causes apart on a 12-character message:
item 5 contributes about 3 readings and does not grow with message length (it is
bounded by the size of the final column); the `sort!` contributes a factor of about
1024 and grows as 2^(number of columns where both heads share a row).

This also makes the `draw_spiral` docstring optimistic:

> the probability that two distinct messages render the same is astronomically tiny

## Possible fixes

1. **`sort!`** — ask *one* question over the achievable **sorted** row pairs instead
   of two questions plus a sort. The reachable set of drawings is unchanged (you sort
   precisely so paths cannot cross, and every enumerated pair is already sorted), but
   the drawn pair *is* the answer, so nothing is lost.
2. **duplicate pairs** — `unique(pairs)` before `ask!`.
3. **item 5** — your sentinel glyph works. A cheaper alternative that costs no glyph:
   carry the message length as an extra digit, so the magnitude of `x` is pinned.

I've implemented 1 and 2 in a port and they remove the collisions entirely — decoding
becomes a single linear replay with no search. Happy to open a PR if you'd like,
though I realise these are breaking changes: existing spirals would encode different
messages afterwards. Entirely understand if that's not a trade you want for what is
primarily a drawing tool.

Thanks for the package and the write-up — the Oracle design is lovely.
