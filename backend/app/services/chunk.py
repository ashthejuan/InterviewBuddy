"""Parent–child chunking of parsed sections (PRD §4 “7”)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.sections import ParsedSection

# Target child size ~50–300 tokens (PRD §4). Only glue *tiny* orphans
# (1–2 word fragments), not normal short bullets/requirements.
MIN_CHILD_TOKENS = 3
MAX_CHILD_TOKENS = 300

_BULLET = re.compile(r"^[\-\*\u2022]\s+(.+)$")
_NUMBERED = re.compile(r"^\d+[.)]\s+(.+)$")


@dataclass
class ParsedChunk:
    chunk_kind: str
    content: str
    parent_index: int | None  # None = parent; else index of parent in same list
    metadata: dict = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    words = text.split()
    return len(words)


def chunk_section(section: ParsedSection, *, doc_type: str) -> list[ParsedChunk]:
    if doc_type == "jd":
        child_kind = (
            "requirement"
            if section.kind in ("requirements", "nice_to_have")
            else "bullet"
        )
        return _chunk_flat_bullets(
            section, parent_kind="section", child_kind=child_kind
        )
    if section.kind == "experience":
        return _chunk_experience(section)
    if section.kind == "projects":
        return _chunk_experience(section, parent_kind="role")
    if section.kind == "skills":
        return _chunk_skills(section)
    return _chunk_flat_bullets(section, parent_kind="section", child_kind="bullet")


def _chunk_experience(section: ParsedSection, *, parent_kind: str = "role") -> list[ParsedChunk]:
    blocks = _split_role_blocks(section.text)
    if not blocks:
        return [
            ParsedChunk(
                chunk_kind=parent_kind,
                content=section.text.strip(),
                parent_index=None,
                metadata={"section_kind": section.kind},
            )
        ]

    out: list[ParsedChunk] = []
    for block in blocks:
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        parent_idx = len(out)
        out.append(
            ParsedChunk(
                chunk_kind=parent_kind,
                content="\n".join(lines),
                parent_index=None,
                metadata={"section_kind": section.kind},
            )
        )
        bullets = [_strip_bullet(ln) for ln in lines if _is_bullet(ln)]
        if not bullets and len(lines) > 1:
            # Non-bullet body after a header line → children
            bullets = [ln.strip() for ln in lines[1:]]

        merged = _merge_orphans(bullets)
        for b in merged:
            if not b.strip():
                continue
            out.append(
                ParsedChunk(
                    chunk_kind="bullet",
                    content=b.strip(),
                    parent_index=parent_idx,
                    metadata={"section_kind": section.kind},
                )
            )
    return out


def _chunk_flat_bullets(
    section: ParsedSection,
    *,
    parent_kind: str,
    child_kind: str,
) -> list[ParsedChunk]:
    parent = ParsedChunk(
        chunk_kind=parent_kind,
        content=section.text.strip(),
        parent_index=None,
        metadata={"section_kind": section.kind},
    )
    lines = [ln.rstrip() for ln in section.text.splitlines() if ln.strip()]
    items: list[str] = []
    for ln in lines:
        if _is_bullet(ln):
            items.append(_strip_bullet(ln))
        else:
            # Non-bullet line: treat as its own item if substantial
            items.append(ln.strip())
    merged = _merge_orphans(items)
    children = [
        ParsedChunk(
            chunk_kind=child_kind,
            content=item.strip(),
            parent_index=0,
            metadata={"section_kind": section.kind},
        )
        for item in merged
        if item.strip()
    ]
    # Avoid duplicating parent-only when no children
    if not children:
        return [parent]
    return [parent, *children]


def _chunk_skills(section: ParsedSection) -> list[ParsedChunk]:
    parent = ParsedChunk(
        chunk_kind="section",
        content=section.text.strip(),
        parent_index=None,
        metadata={"section_kind": "skills"},
    )
    # Prefer comma / semicolon lists; else lines
    raw = section.text.strip()
    if "," in raw or ";" in raw:
        parts = re.split(r"[,;]", raw)
        items = [p.strip() for p in parts if p.strip()]
    else:
        items = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        items = [_strip_bullet(i) if _is_bullet(i) else i for i in items]

    merged = _merge_orphans(items)
    children = [
        ParsedChunk(
            chunk_kind="bullet",
            content=item,
            parent_index=0,
            metadata={"section_kind": "skills"},
        )
        for item in merged
        if item
    ]
    if not children:
        return [parent]
    return [parent, *children]


def _split_role_blocks(text: str) -> list[str]:
    """Split experience/projects on blank lines; also start a block on non-bullet after bullets."""
    lines = text.splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        body = "\n".join(current).strip()
        if body:
            blocks.append(current)
        current = []

    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            if current:
                flush()
            continue
        # New role: non-bullet line while current block already has content and prior was bullet
        if (
            current
            and not _is_bullet(stripped)
            and any(_is_bullet(x.strip()) for x in current if x.strip())
        ):
            flush()
        current.append(ln)
    if current:
        flush()
    return ["\n".join(b) for b in blocks]


def _is_bullet(line: str) -> bool:
    s = line.strip()
    return bool(_BULLET.match(s) or _NUMBERED.match(s))


def _strip_bullet(line: str) -> str:
    s = line.strip()
    m = _BULLET.match(s) or _NUMBERED.match(s)
    return m.group(1).strip() if m else s


def _merge_orphans(items: list[str]) -> list[str]:
    """Merge children under MIN_CHILD_TOKENS into previous; clip overflow softly."""
    if not items:
        return []
    merged: list[str] = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        toks = estimate_tokens(item)
        if merged and toks < MIN_CHILD_TOKENS:
            # Prefer merge into previous rather than leaving a tiny orphan
            prev = merged[-1]
            if estimate_tokens(prev) + toks <= MAX_CHILD_TOKENS * 2:
                merged[-1] = f"{prev}\n{item}"
                continue
        merged.append(item)
    # If first item alone is tiny and there's only one, keep it (nothing to merge into)
    return merged
