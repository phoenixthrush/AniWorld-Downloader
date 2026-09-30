"""Read JSON objects from Next.js page data without evaluating JavaScript."""

import json
import re

from ...extractors.common import walk_objects


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
    for line in "".join(chunks).splitlines():
        _, _, payload = line.partition(":")
        if not payload.startswith(("[", "{")):
            continue
        try:
            value = json.loads(payload)
        except ValueError:
            continue
        yield from walk_objects(value)
