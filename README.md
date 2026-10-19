# vtt_subtitle_tools

Parses and serializes WebVTT subtitle files, preserving cues (with optional identifiers) and non-cue blocks (STYLE, REGION, NOTE) verbatim.

## Usage

```python
from vtt_subtitle_tools import parse, serialize, Cue

items = parse("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello world")
for item in items:
    if isinstance(item, Cue):
        print(item.as_dict())

text = serialize(items)
```

`parse(text: str) -> list` returns a list of `Cue` and `RawBlock` objects in document order. `serialize(items: list) -> str` turns them back into WebVTT text. `Cue` is a dataclass with `start` and `end` (int milliseconds), `payload` (str), and `identifier` (str or None). `RawBlock` has a single `text` field containing the full block.

## Why this exists

The WebVTT format looks simple but has enough edge cases — optional cue identifiers, short vs. long timestamps, STYLE/REGION/NOTE blocks — that ad-hoc string splitting fails quickly. This library handles those without pulling in a full media framework.

The trade-off: we do not interpret cue payload tags (`<b>`, `<i>`, `<c>`) or parse the CSS inside STYLE blocks. Payloads are kept as raw strings. If you need to manipulate inline formatting, you will need to layer that on top.

## Edge cases

Timestamps are normalized to `HH:MM:SS.mmm` on output, so a file using the short `MM:SS.mmm` form will come back with the long form. Cue identifiers are any single line above the timestamp line; if that line looks like a timestamp itself, it is treated as a cue without an identifier rather than an identifier.
