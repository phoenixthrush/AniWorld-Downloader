"""Read JSON objects from Next.js page data without evaluating JavaScript."""

import json
import re

from ...extractors.common import walk_objects

# A text record, "<id>:T<hex byte length>,<text>". It ends after that many
# bytes instead of at a newline, so the next record can follow on the same line.
_TEXT_RECORD = re.compile(rb"T([0-9a-fA-F]+),")


def _payloads(data):
    """Yield every record's payload from a Flight stream, as text."""
    pos = 0
    while pos < len(data):
        colon = data.find(b":", pos)
        if colon < 0:
            return
        start = colon + 1
        text = _TEXT_RECORD.match(data, start)
        if text:
            start = text.end()
            pos = start + int(text[1], 16)
            yield data[start:pos].decode("utf-8", errors="replace")
            continue
        end = data.find(b"\n", start)
        if end < 0:
            end = len(data)
        yield data[start:end].decode("utf-8", errors="replace")
        pos = end + 1


def page_objects(html):
    chunks = []
    for match in re.finditer(
        r"self\.__next_f\.push\((.*?)\)</script>", html, re.DOTALL
    ):
        try:
            value = json.loads(match[1])
        except ValueError:
            continue
        if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str):
            chunks.append(value[1])
    # A Flight record can be split across multiple script elements.
    for payload in _payloads("".join(chunks).encode("utf-8")):
        if not payload.startswith(("[", "{")):
            continue
        try:
            value = json.loads(payload)
        except ValueError:
            continue
        yield from walk_objects(value)
