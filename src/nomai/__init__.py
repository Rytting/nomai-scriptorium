"""Nomai text: a Python port of the upstream generator plus a decoder.

The generator half (`oracle`, `glyphs`, `gridgen`) is a faithful port of
evanfields/NomaiText.jl -- it exists so the decoder can re-derive the `k` of every
Oracle question, which is what makes decoding possible at all.
"""
