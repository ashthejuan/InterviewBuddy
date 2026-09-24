"""Section-aware parse of normalized resume/JD text (PRD §4 “3”)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Canonical kind → header aliases (matched case-insensitively after normalize)
_RESUME_HEADERS: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "profile", "about", "objective"),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "work history",
    ),
    "projects": ("projects", "personal projects", "selected projects"),
    "education": ("education", "academic"),
    "skills": ("skills", "technical skills", "technologies", "tech stack"),
    "certifications": ("certifications", "certificates", "licenses"),
    "awards": ("awards", "honors", "achievements"),
}

_JD_HEADERS: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "about the role", "about", "overview"),
    "responsibilities": (
        "responsibilities",
        "what you'll do",
        "what you will do",
        "the role",
        "duties",
    ),
    "requirements": (
        "requirements",
        "qualifications",
        "what we're looking for",
        "what we are looking for",
        "must have",
        "must-haves",
        "required",
    ),
    "nice_to_have": (
        "nice to have",
        "nice-to-have",
        "nice to haves",
        "preferred",
        "bonus",
        "plus",
    ),
}

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ALL_CAPS = re.compile(r"^[A-Z][A-Z0-9 /&\-]{1,60}$")


@dataclass(frozen=True)
class ParsedSection:
    kind: str
    title: str | None
    text: str
    ordinal: int


def parse_sections(text: str, *, doc_type: str) -> list[ParsedSection]:
    stripped = text.strip()
    if not stripped:
        return []

    catalog = _JD_HEADERS if doc_type == "jd" else _RESUME_HEADERS
    alias_to_kind = {
        alias: kind for kind, aliases in catalog.items() for alias in aliases
    }

    lines = stripped.splitlines()
    cuts: list[tuple[int, str, str]] = []  # (line_index, kind, title)

    for i, line in enumerate(lines):
        title = _heading_title(line)
        if title is None:
            continue
        kind = _match_kind(title, alias_to_kind)
        if kind is None:
            continue
        cuts.append((i, kind, title))

    if not cuts:
        return [
            ParsedSection(kind="other", title=None, text=stripped, ordinal=0),
        ]

    sections: list[ParsedSection] = []
    ordinal = 0

    # Preamble before first header
    first_i = cuts[0][0]
    if first_i > 0:
        preamble = "\n".join(lines[:first_i]).strip()
        if preamble:
            sections.append(
                ParsedSection(kind="other", title=None, text=preamble, ordinal=ordinal)
            )
            ordinal += 1

    for idx, (start, kind, title) in enumerate(cuts):
        end = cuts[idx + 1][0] if idx + 1 < len(cuts) else len(lines)
        body = "\n".join(lines[start + 1 : end]).strip()
        if not body:
            continue
        sections.append(
            ParsedSection(kind=kind, title=title, text=body, ordinal=ordinal)
        )
        ordinal += 1

    if not sections:
        return [
            ParsedSection(kind="other", title=None, text=stripped, ordinal=0),
        ]
    return sections


def _heading_title(line: str) -> str | None:
    raw = line.strip()
    if not raw:
        return None
    md = _MD_HEADING.match(raw)
    if md:
        return md.group(2).strip().rstrip(":").strip()
    # ALL-CAPS banner or short Title Case / trailing colon headers
    cleaned = raw.rstrip(":").strip()
    if _ALL_CAPS.match(cleaned):
        return cleaned
    # Single-line Title Case header (≤6 words, no bullet)
    if raw.startswith(("-", "*", "•")):
        return None
    words = cleaned.split()
    if 1 <= len(words) <= 6 and all(w[:1].isupper() for w in words if w[0].isalpha()):
        return cleaned
    return None


def _match_kind(title: str, alias_to_kind: dict[str, str]) -> str | None:
    key = re.sub(r"\s+", " ", title.lower().rstrip(":").strip())
    return alias_to_kind.get(key)
