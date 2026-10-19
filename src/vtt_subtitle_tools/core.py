"""Parse and serialize WebVTT subtitle files.

Scope decisions (stated plainly):

* We only handle the body — cues with identifiers, timestamps, and payload.
  The WEBVTT file header line is validated but no metadata on the header line
  is parsed.
* STYLE and REGION blocks are preserved verbatim as raw text blocks so that
  round-tripping a file does not lose them. We do not interpret their CSS.
* NOTE blocks are treated like other non-cue blocks: preserved as raw text.
* A cue payload is kept as a single string (newline-joined). We do not split
  it into individual line cues or parse VTT cue tags (<b>, <i>, etc.).
* Timestamps are validated strictly per the WebVTT spec: MM:SS.mmm or
  HH:MM:SS.mmm. We normalize on output to HH:MM:SS.mmm with three-digit
  milliseconds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_TS_RE = re.compile(
    r"^(?:(\d{2,}):)?(\d{2}):(\d{2})\.(\d{3})$"
)

_HEADER_RE = re.compile(r"^WEBVTT(\s.*)?$")

_ARROW_RE = re.compile(r"^\S+\s+-->\s+\S+")


def parse_timestamp(value: str) -> int:
    """Parse a WebVTT timestamp into milliseconds since midnight.

    Accepts both ``MM:SS.mmm`` and ``HH:MM:SS.mmm``.
    Raises ``ValueError`` if the string is not a valid timestamp.
    """
    if not isinstance(value, str):
        raise ValueError(
            f"timestamp must be a string, got {type(value).__name__}"
        )
    m = _TS_RE.match(value.strip())
    if not m:
        raise ValueError(f"invalid WebVTT timestamp: {value!r}")
    hours = int(m.group(1)) if m.group(1) is not None else 0
    minutes = int(m.group(2))
    seconds = int(m.group(3))
    millis = int(m.group(4))
    return hours * 3_600_000 + minutes * 60_000 + seconds * 1_000 + millis


def format_timestamp(ms: int) -> str:
    """Format milliseconds since midnight as ``HH:MM:SS.mmm``."""
    if not isinstance(ms, int) or isinstance(ms, bool):
        raise ValueError(
            f"timestamp value must be int milliseconds, got {type(ms).__name__}"
        )
    if ms < 0:
        raise ValueError(f"timestamp must be non-negative, got {ms}")
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


@dataclass
class Cue:
    """A single WebVTT cue.

    ``identifier`` is the optional cue id (the line above the timestamps).
    ``start``/``end`` are int milliseconds since midnight.
    ``payload`` is the cue body as a single string (may contain newlines).
    """

    start: int
    end: int
    payload: str
    identifier: str | None = None

    def as_dict(self) -> dict:
        """Return a plain dict representation with formatted timestamps.

        Convenient for JSON export or inspection. We deliberately include
        the identifier only when set, so consumers can distinguish present
        vs. empty identifiers.
        """
        d = {
            "start": format_timestamp(self.start),
            "end": format_timestamp(self.end),
            "payload": self.payload,
        }
        if self.identifier is not None:
            d["identifier"] = self.identifier
        return d


@dataclass
class RawBlock:
    """A preserved non-cue block (STYLE, REGION, NOTE, etc.).

    We store the full text including the block header so round-tripping is
    lossless. We do not interpret the contents.
    """

    text: str


def _is_block_header(line: str) -> bool:
    """Return True for lines that start a known non-cue block.

    STYLE, REGION, and NOTE are the block types defined by WebVTT. Cue
    identifiers are arbitrary strings, so we treat any other line as either
    an identifier (followed by a timestamp line) or as part of a raw block.
    """
    return bool(re.match(r"^(STYLE|REGION|NOTE)\b", line))


def parse(text: str) -> list:
    """Parse WebVTT text into a list of items.

    Returns a list of ``Cue`` and ``RawBlock`` objects in document order.

    The WEBVTT header line is required and must be the first non-empty line.
    """
    if not isinstance(text, str):
        raise ValueError(
            f"parse expects str, got {type(text).__name__}"
        )

    # Normalize line endings so we can split reliably on \n regardless
    # of whether the file came from Windows or Unix.
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    i = 0
    n = len(lines)

    # Skip leading blank lines before the header (some encoders add them).
    while i < n and lines[i].strip() == "":
        i += 1

    if i >= n:
        raise ValueError("empty input: no WEBVTT header")

    if not _HEADER_RE.match(lines[i].strip()):
        raise ValueError(
            f"missing or invalid WEBVTT header: {lines[i]!r}"
        )
    i += 1

    items: list = []

    while i < n:
        line = lines[i]

        # Skip blank lines between blocks.
        if line.strip() == "":
            i += 1
            continue

        # Non-cue block (STYLE, REGION, NOTE).
        if _is_block_header(line):
            block_lines = [line]
            i += 1
            while i < n and lines[i].strip() != "":
                block_lines.append(lines[i])
                i += 1
            items.append(RawBlock(text="\n".join(block_lines)))
            continue

        # Try to interpret as a cue.
        identifier: str | None = None
        if _ARROW_RE.match(line.strip()):
            timestamp_line = line.strip()
        else:
            identifier = line.strip()
            i += 1
            if i >= n:
                raise ValueError(
                    f"cue identifier {identifier!r} not followed by "
                    "a timestamp line"
                )
            timestamp_line = lines[i].strip()
            if not _ARROW_RE.match(timestamp_line):
                raise ValueError(
                    f"expected timestamp line after identifier "
                    f"{identifier!r}, got {timestamp_line!r}"
                )

        m = re.match(
            r"^(\S+)\s+-->\s+(\S+)\s*(.*)$", timestamp_line
        )
        if not m:
            raise ValueError(
                f"invalid cue timing line: {timestamp_line!r}"
            )

        start_ms = parse_timestamp(m.group(1))
        end_ms = parse_timestamp(m.group(2))

        if end_ms < start_ms:
            raise ValueError(
                f"cue end ({format_timestamp(end_ms)}) is before "
                f"start ({format_timestamp(start_ms)})"
            )

        i += 1
        payload_lines: list[str] = []
        while i < n and lines[i].strip() != "":
            payload_lines.append(lines[i])
            i += 1

        items.append(
            Cue(
                start=start_ms,
                end=end_ms,
                payload="\n".join(payload_lines),
                identifier=identifier,
            )
        )

    return items


def serialize(items: list) -> str:
    """Serialize a list of ``Cue``/``RawBlock`` items back to WebVTT text.

    The output is normalized: timestamps use ``HH:MM:SS.mmm`` and blocks are
    separated by a single blank line.
    """
    if not isinstance(items, list):
        raise ValueError(
            f"serialize expects list, got {type(items).__name__}"
        )

    out: list[str] = ["WEBVTT", ""]

    for item in items:
        if isinstance(item, Cue):
            if item.identifier is not None:
                out.append(item.identifier)
            out.append(
                f"{format_timestamp(item.start)} "
                f"--> {format_timestamp(item.end)}"
            )
            out.append(item.payload)
            out.append("")
        elif isinstance(item, RawBlock):
            out.append(item.text)
            out.append("")
        else:
            raise ValueError(
                f"unsupported item type: {type(item).__name__}"
            )

    return "\n".join(out)
