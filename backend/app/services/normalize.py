"""Normalize extracted document text (PRD §3.1.1)."""

from __future__ import annotations

import unicodedata


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    # Drop nulls and other C0/C1 controls except \t \n \r
    return "".join(
        ch
        for ch in text
        if ch in "\t\n\r" or (unicodedata.category(ch)[0] != "C")
    )
