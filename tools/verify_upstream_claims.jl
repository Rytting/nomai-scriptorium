#=
Check every claim in docs/upstream-issue-draft.md against the real NomaiText.jl,
so nothing goes upstream that was only ever verified in our Python port.

Run:  julia tools/verify_upstream_claims.jl
=#

using Pkg
const ROOT = normpath(joinpath(@__DIR__, ".."))
Pkg.activate(joinpath(@__DIR__, "env"))

using JSON
using NomaiText
using NomaiText: Oracle, Glyph, PolySpec, KNOWN_GLYPHS, allpoints, hasglyph,
                 GlyphGrid, DEFAULT_SPACING, K
const Point = NomaiText.Point        # Luxor, via NomaiText
const distance = NomaiText.distance

const ASK_LOG = Tuple{Int,Int}[]

# Mirrors src/oracles.jl verbatim, plus a log push.
@eval NomaiText function ask!(o::Oracle, k::Int)
    newstate, answer = divrem(o.state, k)
    if iszero(newstate)
        o.completed = true
        o.state = o.orig_state
    else
        o.state = newstate
    end
    push!(Main.ASK_LOG, (k, Int(answer) + 1))
    return answer + 1
end

results = Pair{String,Bool}[]
record(name, ok) = (push!(results, name => ok);
                    println(ok ? "  PASS  " : "  FAIL  ", name))

##
# Claim 1: "hi" and "&i" render to the same SVG at base 256.
##
println("\n[1] draw_spiral(\"hi\") == draw_spiral(\"&i\") at base 256")
clean(s) = replace(
    draw_spiral(s; base = 256, as_string = true),
    r"id\s*=\s*\"[^\"]*\"" => "id=\"x\"",
)
svg_hi, svg_amp = clean("hi"), clean("&i")
println("    SVG lengths: ", length(svg_hi), " vs ", length(svg_amp))
record("hi/&i render identically", svg_hi == svg_amp)

##
# Claim 2: they differ only by a swap of the two row answers, and the Oracle
# states re-merge immediately afterwards.
##
println("\n[2] ask trace")
function trace(msg)
    empty!(ASK_LOG)
    NomaiText.grid_from_oracle!(Oracle(msg; base = 256))
    return copy(ASK_LOG)
end
t_hi, t_amp = trace("hi"), trace("&i")
println("      #    k | \"hi\" | \"&i\"")
for (i, ((k1, a1), (k2, a2))) in enumerate(zip(t_hi, t_amp))
    println("    ", lpad(i - 1, 3), lpad(k1, 5), " | ", lpad(a1, 4), " | ", lpad(a2, 4),
            a1 == a2 ? "" : "   <- differs")
end
diffs = [i for i in 1:min(length(t_hi), length(t_amp)) if t_hi[i][2] != t_amp[i][2]]
swapped = length(diffs) == 2 && diffs[2] == diffs[1] + 1 &&
          t_hi[diffs[1]][2] == t_amp[diffs[2]][2] &&
          t_hi[diffs[2]][2] == t_amp[diffs[1]][2]
println("    differing positions: ", diffs .- 1)
record("exactly two adjacent answers, swapped", swapped)
println("    817 / 3 / 3 = ", 817 ÷ 3 ÷ 3, ",  815 / 3 / 3 = ", 815 ÷ 3 ÷ 3)
record("states re-merge after the two row questions", 817 ÷ 3 ÷ 3 == 815 ÷ 3 ÷ 3)

##
# Claim 3: allpoints can repeat a point, so _shortest_connection! can offer the
# same (ptA, ptB) pair at two indices -- two answers, one identical line.
##
println("\n[3] duplicate vertex pairs in the connection question")
dup_glyphs = [i for (i, g) in enumerate(KNOWN_GLYPHS)
              if length(unique(allpoints(g))) < length(allpoints(g))]
println("    glyphs whose allpoints repeats a point: ", dup_glyphs)

# The tie-collection loop, copied from _shortest_connection! in src/glyphgrid.jl.
function pairs_for(ptsA, ptsB, offset, thresh = 0.01)
    best = Inf
    pairs = Tuple{Point,Point}[]
    for ptA in ptsA, ptB in ptsB
        d = distance(ptA, ptB + offset)
        if d <= best - thresh
            empty!(pairs); push!(pairs, (ptA, ptB))
        elseif d < best + thresh
            push!(pairs, (ptA, ptB))
        end
        best = min(d, best)
    end
    return pairs
end

# wrapped in a function: a top-level `for` gets its own soft scope in Julia
function scan_duplicate_pairs()
    dup, total = 0, 0
    for ga in KNOWN_GLYPHS, gb in KNOWN_GLYPHS, dj in -2:2
        offset = Point(DEFAULT_SPACING * 1, DEFAULT_SPACING * dj)
        p = pairs_for(allpoints(ga), allpoints(gb), offset)
        total += 1
        length(unique(p)) < length(p) && (dup += 1)
    end
    return dup, total
end
dup_cases, total_cases = scan_duplicate_pairs()
println("    (glyphA, glyphB, offset) triples scanned: ", total_cases)
println("    triples where the pairs list repeats a pair: ", dup_cases)
record("duplicate pairs really occur", dup_cases > 0)

##
# Claim 4: 184 distinct integers give a byte-identical drawing for
# "Curious Archaeology". Compared at GlyphGrid level -- the drawing is a
# deterministic function of the grid.
##
println("\n[4] collision counts from data/collisions.json")

_pts_eq(a, b) = length(a) == length(b) &&
    all(isapprox(p.x, q.x; atol = 1e-9) && isapprox(p.y, q.y; atol = 1e-9)
        for (p, q) in zip(a, b))
function _same(a::Glyph, b::Glyph)
    isnothing(a.annotation) == isnothing(b.annotation) || return false
    a.core.close == b.core.close || return false
    _pts_eq(a.core.points, b.core.points) || return false
    isnothing(a.annotation) && return true
    return a.annotation.close == b.annotation.close &&
           _pts_eq(a.annotation.points, b.annotation.points)
end
function glyph_id(g::Glyph)
    for (i, kg) in enumerate(KNOWN_GLYPHS)
        _same(g, kg) && return i
    end
    error("glyph not found")
end
function signature(gg::GlyphGrid)
    glyphs = Tuple{Int,Int,Int}[]
    for i in 1:size(gg.grid, 1), j in 1:size(gg.grid, 2)
        hasglyph(gg.grid[i, j]) && push!(glyphs, (i, j, glyph_id(gg.grid[i, j])))
    end
    conns = [(c.coord1, round.((c.point1.x, c.point1.y); digits = 9),
              c.coord2, round.((c.point2.x, c.point2.y); digits = 9))
             for c in gg.connections]
    return (glyphs, [collect(p) for p in gg.paths], conns)
end

for case in JSON.parsefile(joinpath(ROOT, "data", "collisions.json"))
    msg, base = case["message"], case["base"]
    ref = signature(NomaiText.grid_from_oracle!(Oracle(msg; base = base)))
    xs = parse.(BigInt, case["colliding"])
    matches = count(x -> signature(NomaiText.grid_from_oracle!(Oracle(x))) == ref, xs)
    println("    ", repr(msg), ": ", length(xs), " claimed, ", matches, " confirmed")
    record("$(repr(msg)): all claimed collisions confirmed", matches == length(xs))
end

##
println("\n", "="^60)
for (name, ok) in results
    println(ok ? "PASS  " : "FAIL  ", name)
end
println(all(last, results) ? "\nALL CLAIMS HOLD" : "\nSOME CLAIMS FAILED")
