# HTML Character Entity Decoder

Decodes HTML character entities — named (`&amp;`), decimal (`&#38;`), and hex (`&#x26;`) — to their Unicode characters. Standard library only, no third-party dependencies.

```python
from html_character_entity_decoder import decode, decode_once, decode_iter, EntityError

assert decode_once("a &amp; b") == "a & b"
assert decode_once("&#38;") == "&"
assert decode_once("&#x26;") == "&"
assert decode("&amp;amp;") == "&"  # iterative: resolves double-encoded entities

for chunk in decode_iter("x&amp;y"):
    ...  # lazy streaming for large inputs
```

## Why this exists

The standard library's `html.unescape` does most of this work, but its contract is loose: it silently leaves unknown references in place and will happily decode a numeric reference to a lone surrogate. When the point of decoding is to feed text into a strict downstream consumer (a CSV writer, a log line, a comparison key), those silent pass-throughs become the bug you find three weeks later. This library picks the opposite defaults: unknown named entities and out-of-range numeric entities raise `EntityError`, and a bare `&` that doesn't form a valid entity is left as a literal `&` rather than being dropped or guessed at.

The named-entity table is built at import time from `html.entities.html5` via `html.unescape`, so it stays in sync with the stdlib's definition of the HTML5 named-character set rather than carrying a vendored copy that would rot.

## The awkward edge

`decode_once` resolves each entity exactly once and does **not** re-scan its output. That means `&amp;lt;` decodes to `&lt;`, not to `<`. This is deliberate: a single pass is what you want when repairing text that was entity-encoded once by an upstream producer. For double-encoded input like `&amp;amp;`, use `decode()`, which repeats `decode_once` until the text stabilises or `max_passes` (default 10) is exhausted. The cap exists so a pathological input can't spin forever; ten passes covers any realistic double- or triple-encoded payload.

A second edge: lone surrogates (`&#xD800;`) and code points above U+10FFFF raise `EntityError`, because they cannot be represented as a single well-formed Unicode scalar value. If your input might legitimately contain such references and you'd rather pass them through, this is the wrong library.
