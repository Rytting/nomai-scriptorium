#=
Generate a spread of real SVGs from the upstream renderer, for batch-testing the
Python vision pipeline against inputs it has never seen.

Run:  julia tools/gen_samples.jl
=#
using Pkg
const ROOT = normpath(joinpath(@__DIR__, ".."))
Pkg.activate(joinpath(@__DIR__, "env"))

using JSON
using NomaiText

const WORDS = split(
    "the nomai came to this solar system searching for eye of universe a signal " *
    "older than itself and they never did find it built ash twin project send " *
    "memories back through time then ghost matter killed every last one of them"
)

function phrase(rng, n)
    parts = String[]
    while sum(length.(parts)) + length(parts) < n + 8
        push!(parts, rand(rng, WORDS))
    end
    return String(strip(join(parts, " ")[1:min(end, n)]))  # draw_spiral wants ::String
end

using Random
rng = MersenneTwister(20260901)

outdir = joinpath(ROOT, "data", "svg")
mkpath(outdir)
foreach(f -> rm(joinpath(outdir, f)), readdir(outdir))

manifest = Dict{String,Any}[]
idx = 0
for base in (256, 200_000)
    for n in (2, 5, 10, 18, 30)
        for hw in (0.0, 0.3, 0.6)
            for trial in 1:2
                global idx += 1
                msg = phrase(rng, n)
                seed = rand(rng, 1:10_000)
                svg = draw_spiral(msg; base = base, as_string = true,
                                  handwriting = hw, seed = seed)
                name = "s$(lpad(idx, 3, '0')).svg"
                write(joinpath(outdir, name), svg)
                push!(manifest, Dict(
                    "file" => name, "message" => msg, "base" => base,
                    "handwriting" => hw, "seed" => seed,
                ))
                println("$(name)  base=$(base) hw=$(hw) len=$(length(msg))  $(repr(msg))")
            end
        end
    end
end
open(io -> JSON.print(io, manifest), joinpath(outdir, "manifest.json"), "w")
println("\nwrote $(length(manifest)) samples to data/svg/")
