from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from app.core.exceptions import InvalidPollOptionsError

POLL_SEPARATOR_RE = re.compile(r"(?:\r?\n|[^\S\r\n]{2,})+")
HTML_TAG_RE = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")


def validate_poll_options(options: Sequence[str]) -> list[str]:
    normalized = [option.strip() for option in options]
    if not 2 <= len(normalized) <= 6:
        raise InvalidPollOptionsError("Укажите от 2 до 6 вариантов.")
    if any(not 1 <= len(option) <= 40 for option in normalized):
        raise InvalidPollOptionsError("Каждый вариант должен содержать от 1 до 40 символов.")
    if any(HTML_TAG_RE.search(option) for option in normalized):
        raise InvalidPollOptionsError("HTML-разметка в вариантах не поддерживается.")
    if any(any(unicodedata.category(char) == "Cc" for char in option) for option in normalized):
        raise InvalidPollOptionsError("Варианты должны быть обычным текстом.")
    folded = [option.casefold() for option in normalized]
    if len(set(folded)) != len(folded):
        raise InvalidPollOptionsError("Варианты не должны повторяться.")
    return normalized


def parse_poll_options(value: str) -> list[str]:
    options = [option for option in POLL_SEPARATOR_RE.split(value.strip()) if option.strip()]
    return validate_poll_options(options)
