"""Pure text normalization helpers."""

from __future__ import annotations

import re
import unicodedata


def normalize_text(text: str) -> str:
    if not text:
        return ""
    value = unicodedata.normalize("NFKD", text.lower().strip())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value)

