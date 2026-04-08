"""String sanitization utilities for CSV import security."""

import re

# Characters that can trigger formula execution in spreadsheet applications
_CSV_INJECTION_CHARS = set("=+@\t\r")
# Minus/hyphen is also a CSV injection prefix
_CSV_INJECTION_CHARS.add("-")

_HTML_TAG_RE = re.compile(r"<[^>]*>")


def sanitize_string(value: str, max_length: int = 10000) -> str:
    """Sanitize a string field to prevent injection attacks.

    - Strip leading CSV injection characters (=, +, -, @, \\t, \\r) in a loop
    - Remove HTML/script tags
    - Remove null bytes
    - Truncate to *max_length*
    - Strip leading/trailing whitespace
    """
    # Strip leading CSV injection prefixes repeatedly
    while value and value[0] in _CSV_INJECTION_CHARS:
        value = value[1:]

    # Remove HTML / script tags
    value = _HTML_TAG_RE.sub("", value)

    # Remove null bytes
    value = value.replace("\x00", "")

    # Truncate to max_length
    value = value[:max_length]

    # Strip surrounding whitespace
    value = value.strip()

    return value
