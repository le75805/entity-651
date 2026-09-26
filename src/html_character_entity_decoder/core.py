"""HTML character entity decoding.

The decoder is intentionally literal: a bare '&' not forming a valid entity is
left alone, unknown named entities raise EntityError, and entities are not
re-decoded in the output (a decoded '&' will never spuriously start a new
entity). The named-entity table is built from html.unescape rather than copied
out by hand — that keeps it in sync with the stdlib's definition of the HTML5
named-character-reference set without dragging in a vendored copy that would
go stale.
"""

import html as _html
import re


class EntityError(ValueError):
    """Raised when the input contains a reference the decoder cannot resolve.

    We treat an unknown *named* entity (e.g. &bogus;) as a hard error rather
    than passing it through, because in the contexts where a decoder is useful
    — log scrubbing, template post-processing, CSV repair — silently leaking an
    ampersand-shaped token downstream is exactly the failure mode the caller is
    trying to eliminate. A *numeric* entity that points outside the legal
    Unicode range is the same class of problem, so it raises too.
    """


_NAMED = {}

def _build_named_table():
    """Build a name -> character table from html.unescape.

    html.unescape is the most-maintained source of the HTML5 named-character
    reference list in the stdlib. We can't ask it for its table directly, so
    we round-trip one representative reference per name and read back the
    decoded character. This avoids vendoring a 2,000-entry table that would
    rot whenever the spec changes.
    """
    table = {}
    for name in _ALL_ENTITY_NAMES:
        ref = "&" + name + ";"
        decoded = _html.unescape(ref)
        if len(decoded) == 1:
            table[name] = decoded
        else:
            # Some legacy references (e.g. &lt without a semicolon) decode to
            # more than one character or to a bare ampersand; we only want the
            # strict semicolon-terminated forms, so skip anything that doesn't
            # round-trip to exactly one character.
            pass
    return table


def _collect_entity_names():
    """Return the set of semicolon-terminated HTML5 named entity names.

    html.entities.html5 maps names like 'lt;' to their characters; the
    trailing semicolon is part of the key. We strip it to get the bare name.
    """
    try:
        from html.entities import html5
    except ImportError:
        # Fallback: scrape by probing unescape with a broad set. In practice
        # html.entities.html5 has existed since Python 3.3, so this branch is
        # defensive only.
        return set()
    names = set()
    for key in html5:
        if key.endswith(";"):
            names.add(key[:-1])
    return names


_ALL_ENTITY_NAMES = _collect_entity_names()
_NAMED = _build_named_table()


_ENTITY_RE = re.compile(
    r"&(#[0-9]+;|#[xX][0-9A-Fa-f]+;|([A-Za-z][A-Za-z0-9]*);)"
)


def _decode_numeric(body):
    """Decode a numeric entity body (without the surrounding & and ;).

    Returns the decoded character, or raises EntityError if the code point is
    outside the legal Unicode range or encodes a surrogate in isolation.
    """
    if body[0] == "#":
        inner = body[1:]
        if inner[0] in ("x", "X"):
            try:
                code = int(inner[1:], 16)
            except ValueError:
                raise EntityError("invalid hex numeric entity: &%s" % body)
        else:
            try:
                code = int(inner, 10)
            except ValueError:
                raise EntityError("invalid decimal numeric entity: &%s" % body)
    else:
        # Should not happen: the regex only passes #-prefixed bodies here.
        raise EntityError("internal error: non-numeric body passed to _decode_numeric")

    if code < 0 or code > 0x10FFFF:
        raise EntityError("numeric entity out of range: &%s" % body)
    if 0xD800 <= code <= 0xDFFF:
        # Surrogates are not legal scalar values in Unicode; chr() would build
        # one but downstream consumers (encoding, comparison) break on it.
        raise EntityError("numeric entity encodes a lone surrogate: &%s" % body)
    try:
        return chr(code)
    except (ValueError, OverflowError):
        raise EntityError("cannot decode numeric entity: &%s" % body)


def decode_iter(text):
    """Yield decoded text in chunks, resolving one entity at a time.

    The output is the same as decode(text), but produced lazily so that very
    large inputs do not have to be fully buffered before the first character is
    consumed. Each yield is a str of arbitrary length (plain text between
    entities is yielded as one chunk per run).
    """
    if not isinstance(text, str):
        raise TypeError("decode_iter expects str, got %s" % type(text).__name__)
    pos = 0
    for m in _ENTITY_RE.finditer(text):
        if m.start() > pos:
            yield text[pos:m.start()]
        whole = m.group(1)
        if whole[0] == "#":
            # Numeric entity: strip the trailing ';' that the regex captured as
            # part of group 1, since _decode_numeric expects the '#...' body
            # without it.
            yield _decode_numeric(whole[:-1])
        else:
            name = m.group(2)
            if name in _NAMED:
                yield _NAMED[name]
            else:
                raise EntityError("unknown named entity: &%s;" % name)
        pos = m.end()
    if pos < len(text):
        yield text[pos:]


def decode_once(text):
    """Decode entities in *text* exactly once.

    A single pass: '&amp;' becomes '&', and the resulting '&' is not
    re-examined. This is the right behaviour for repairing text that was
    entity-encoded once by an upstream producer; it is the wrong behaviour if
    the input contains double-encoded text like '&amp;amp;', which is rare and
    not worth the ambiguity. Use decode() for the iterative form.
    """
    if not isinstance(text, str):
        raise TypeError("decode_once expects str, got %s" % type(text).__name__)
    return "".join(decode_iter(text))


def decode(text, max_passes=10):
    """Decode entities iteratively until the text stabilises.

    Some inputs are double-encoded: '&amp;amp;' represents '&amp;' after one
    pass and '&' after two. decode() repeats decode_once until the output stops
    changing or max_passes is exhausted. The pass cap exists to make a
    pathological input (e.g. a thousand nested '&amp;...;') terminate in bounded
    time rather than spinning until the stack blows. Ten passes covers any
    realistic double- or triple-encoded payload; callers who need more can pass
    a higher limit explicitly.
    """
    if not isinstance(text, str):
        raise TypeError("decode expects str, got %s" % type(text).__name__)
    if not isinstance(max_passes, int) or max_passes < 1:
        raise ValueError("max_passes must be a positive int")
    current = text
    for _ in range(max_passes):
        nxt = decode_once(current)
        if nxt == current:
            return nxt
        current = nxt
    return current
