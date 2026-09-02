"""Public read/write API.

    write(message, base)  -> GlyphGrid          (strict dialect, uniquely readable)
    read(observation)     -> list of readings   (either dialect)

Use STRICT for messages we write ourselves: the drawing has exactly one reading and
decoding is a linear replay. Use UPSTREAM to read anything produced by
evanfields/NomaiText.jl or nomai-writing.com -- those drawings are genuinely
ambiguous, so `read` returns candidates ranked by a character prior, not an answer.
"""
from .decode import Observation, decode_backward, decode_strict
from .gridgen import GlyphGrid, grid_from_oracle
from .oracle import STRICT, UPSTREAM, Oracle, encode

MAX_NONCE = 64


def write(message: str, base: int = 256, dialect: str = STRICT,
          signature: str | None = None) -> GlyphGrid:
    """Message -> drawing. In STRICT, guarantees the drawing has exactly one reading.

    Rival readings are a deterministic function of X, so the encoder can simply check
    its own output: try nonces until the produced drawing decodes back to exactly one
    reading, and that reading is the message. Costs a few regenerations at write time
    and buys a hard guarantee at read time.
    """
    if dialect != STRICT:
        return grid_from_oracle(Oracle(encode(message, base, dialect)), dialect)
    want = f"{signature}: {message}" if signature else message
    for nonce in range(1, MAX_NONCE + 1):
        x = encode(message, base, STRICT, nonce, signature)
        gg = grid_from_oracle(Oracle(x), STRICT)
        readings = decode_strict(Observation.from_grid(gg), bases=(base,))
        if len(readings) == 1 and readings[0][2] == want:
            return gg
    raise RuntimeError(
        f"no nonce below {MAX_NONCE} yields a uniquely readable drawing for "
        f"{message!r} at base {base}"
    )


def read(obs: Observation, bases=(256, 200_000), dialect: str = STRICT):
    """Drawing -> readings. STRICT returns exactly one; UPSTREAM returns candidates."""
    if dialect == STRICT:
        return decode_strict(obs, bases=bases)
    return decode_backward(obs, bases=bases, dialect=UPSTREAM)
