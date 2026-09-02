"""Port of NomaiText.jl's src/oracles.jl.

An Oracle holds a message as one big integer and answers "which of k?" questions by
repeatedly taking `divmod`. Note the wrap-around: when the state is exhausted it
resets to the original value and keeps answering, so the tail of a generation run
can contain answers that carry no message content.
"""


# Two dialects share every glyph, every geometry rule and every drawing; they differ
# only in how a message is numbered onto them.
#
# UPSTREAM is evanfields/NomaiText.jl exactly. It is lossy in three places, so a
# drawing can have several valid readings ('hi' and '&i' render byte-identically).
# Use it to read anything the author's code or nomai-writing.com produced.
#
# STRICT is our own, with those three leaks closed: the pair of row questions becomes
# one question over sorted outcomes, tied connection pairs are deduplicated, and the
# message length is carried as a leading digit. The set of drawings it can produce is
# unchanged -- only the message-to-drawing map differs -- but that map is injective,
# so decoding is a plain linear replay with no search, no beam and no language prior.
UPSTREAM = "upstream"
STRICT = "strict"
DIALECTS = (UPSTREAM, STRICT)


def evalpoly(base: int, digits) -> int:
    """digits[0] is the least significant -- i.e. the first character."""
    x = 0
    for d in reversed(list(digits)):
        x = x * base + d
    return x


def encode(
    message: str, base: int = 256, dialect: str = UPSTREAM, nonce: int = 1
) -> int:
    """Message -> the integer an Oracle consumes.

    STRICT wraps the codepoints in two extra digits: a length at the bottom and a
    `nonce` at the top. The length alone is not enough -- rival readings differ by a
    multiple of some M, and at base 200000 (= 2^6 * 5^5) M often *is* divisible by
    the base, which carries the low digit through unchanged. The nonce is the knob
    `codec.write` turns until the drawing it produces has exactly one reading, so
    uniqueness is constructed rather than hoped for.
    """
    cps = [ord(c) for c in message]
    if not cps:
        raise ValueError("empty message")
    if max(cps) >= base:
        raise ValueError(f"codepoint {max(cps)} does not fit in base {base}")
    if dialect == STRICT:
        if len(cps) >= base:
            raise ValueError(f"strict dialect: message longer than base {base}")
        if not 1 <= nonce < base:
            raise ValueError(f"nonce {nonce} out of range for base {base}")
        cps = [len(cps)] + cps + [nonce]
    return evalpoly(base, cps)


def decode_int(x: int, base: int, dialect: str = UPSTREAM):
    """The integer -> codepoints, or None if it cannot be a message in this dialect."""
    cps = []
    while x > 0:
        x, r = divmod(x, base)
        cps.append(r)
    if not cps:
        return None
    if dialect == STRICT:
        if len(cps) < 3:
            return None
        body, nonce = cps[:-1], cps[-1]
        declared, body = body[0], body[1:]
        if nonce < 1 or not body or declared != len(body):
            return None
        return body
    return cps


class Oracle:
    __slots__ = ("state", "orig_state", "completed")

    def __init__(self, x: int):
        self.state = int(x)
        self.orig_state = int(x)
        self.completed = False

    @classmethod
    def from_message(cls, message: str, base: int = 256) -> "Oracle":
        return cls(evalpoly(base, [ord(c) for c in message]))

    def ask(self, k: int) -> int:
        """Choose from 1:k, update state, return the 1-based choice."""
        newstate, answer = divmod(self.state, k)
        if newstate == 0:
            self.completed = True
            self.state = self.orig_state
        else:
            self.state = newstate
        return answer + 1

    def ask_options(self, options):
        return options[self.ask(len(options)) - 1]
