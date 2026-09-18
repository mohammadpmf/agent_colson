"""Unicode paragraph direction shared by the composer and message renderer."""

import unicodedata


def text_direction(text: str) -> str:
    for char in text:
        bidi = unicodedata.bidirectional(char)
        if bidi in ("R", "AL"):
            return "rtl"
        if bidi == "L":
            return "ltr"
    return "ltr"
