#=
Export ground truth from the upstream NomaiText.jl so the Python decoder can be
validated against the real generator rather than against our own port.

Produces:
  data/glyphs.json          the 33 KNOWN_GLYPHS with exact vertex coordinates
  data/truth/<slug>.json    per test case: the true BigInt X, the full (k, answer)
                            ask log, and the observable grid structure

Run:  julia tools/export_truth.jl
=#

using Pkg
const ROOT = normpath(joinpath(@__DIR__, ".."))
Pkg.activate(joinpath(@__DIR__, "env"))
Pkg.develop(path = joinpath(ROOT, "vendor", "NomaiText.jl"))
Pkg.add("JSON")

using JSON
using NomaiText
using NomaiText: Glyph, PolySpec, Oracle, KNOWN_GLYPHS, allpoints, GlyphGrid,
                 hasglyph, ROWS, MIDLINE, STARTING_POINT

##
# Instrument ask! so we capture the exact (k, answer) sequence.
# This mirrors src/oracles.jl verbatim plus a log push; if upstream changes
# ask!, this must be updated too.
##
const ASK_LOG = Tuple{Int,Int}[]

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

##
# Serialization
##
poly_json(ps::PolySpec) = Dict(
    "points" => [[p.x, p.y] for p in ps.points],
    "close"  => ps.close,
)

glyph_json(g::Glyph) = Dict(
    "core"       => poly_json(g.core),
    "annotation" => isnothing(g.annotation) ? nothing : poly_json(g.annotation),
)

_pts_eq(a, b) = length(a) == length(b) &&
    all(isapprox(p.x, q.x; atol=1e-9) && isapprox(p.y, q.y; atol=1e-9)
        for (p, q) in zip(a, b))

function _same(a::Glyph, b::Glyph)
    isnothing(a.annotation) == isnothing(b.annotation) || return false
    a.core.close == b.core.close || return false
    _pts_eq(a.core.points, b.core.points) || return false
    isnothing(a.annotation) && return true
    return a.annotation.close == b.annotation.close &&
           _pts_eq(a.annotation.points, b.annotation.points)
end

"1-based index into KNOWN_GLYPHS."
function glyph_id(g::Glyph)
    for (i, kg) in enumerate(KNOWN_GLYPHS)
        _same(g, kg) && return i
    end
    error("glyph not found in KNOWN_GLYPHS")
end

"""Everything a perfect vision frontend would hand the decoder: glyph identities,
path row sequences, and connection endpoints as *coordinates* (not indices --
resolving a coordinate back to a vertex index is part of the decoder's job, and
is genuinely ambiguous when a glyph has duplicate points)."""
function grid_json(gg::GlyphGrid)
    glyphs = Dict{String,Any}[]
    for i in 1:size(gg.grid, 1), j in 1:size(gg.grid, 2)
        hasglyph(gg.grid[i, j]) || continue
        push!(glyphs, Dict("i" => i, "j" => j, "glyph" => glyph_id(gg.grid[i, j])))
    end
    conns = [Dict(
        "coord1" => [c.coord1[1], c.coord1[2]],
        "pt1"    => [c.point1.x, c.point1.y],
        "coord2" => [c.coord2[1], c.coord2[2]],
        "pt2"    => [c.point2.x, c.point2.y],
    ) for c in gg.connections]
    return Dict(
        "rows"        => size(gg.grid, 2),
        "ncols"       => size(gg.grid, 1),
        "glyphs"      => glyphs,
        "paths"       => [[[c[1], c[2]] for c in p] for p in gg.paths],
        "connections" => conns,
    )
end

##
# Test cases
##
const CASES = [
    ("hi",                   256),
    ("hi",                200000),
    ("hello",                256),
    ("hello",             200000),
    ("hella",             200000),
    ("Nomai",             200000),
    ("a",                    256),
    ("ab",                   256),
    ("The quick brown fox",  256),
    ("Curious Archaeology",  256),
    ("Quantum Moon",       200000),
    ("你好",               200000),
]

slug(msg, base) = string(
    replace(msg, r"[^A-Za-z0-9]" => "_"), "_base", base
)

mkpath(joinpath(ROOT, "data", "truth"))

open(joinpath(ROOT, "data", "glyphs.json"), "w") do io
    JSON.print(io, Dict(
        "k"      => NomaiText.K,
        "rows"   => ROWS,
        "glyphs" => [glyph_json(g) for g in KNOWN_GLYPHS],
    ))
end
println("wrote data/glyphs.json  ($(length(KNOWN_GLYPHS)) glyphs)")

for (msg, base) in CASES
    empty!(ASK_LOG)
    oracle = Oracle(msg; base = base)
    x = oracle.orig_state
    gg = grid_from_oracle!(oracle)
    payload = Dict(
        "message" => msg,
        "base"    => base,
        "x"       => string(x),
        "asks"    => [[k, a] for (k, a) in ASK_LOG],
        "grid"    => grid_json(gg),
    )
    path = joinpath(ROOT, "data", "truth", slug(msg, base) * ".json")
    open(io -> JSON.print(io, payload), path, "w")
    println("wrote $(basename(path))  ncols=$(payload["grid"]["ncols"]) asks=$(length(ASK_LOG))")
end
