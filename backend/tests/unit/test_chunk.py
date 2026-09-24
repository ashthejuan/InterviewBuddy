"""Unit tests for section parse + parent–child chunking (PRD §4)."""

from __future__ import annotations

from app.services.chunk import chunk_section, estimate_tokens
from app.services.sections import ParsedSection, parse_sections


RESUME_SAMPLE = """\
Jane Doe
Backend Engineer

EXPERIENCE

Acme Corp — Senior Engineer (2021–2024)
- Built billing API handling 2M req/day
- Reduced p99 latency 40% via caching
- Owned on-call for payments

Beta Inc — Software Engineer (2019–2021)
- Shipped search ranking v2

PROJECTS

InterviewBuddy
- Voice mock interview with LiveKit

SKILLS

Python, FastAPI, Postgres, Redis
"""

JD_SAMPLE = """\
# Backend Engineer

## Requirements
- 5+ years Python
- Experience with Postgres
- System design at scale

## Nice to have
- LiveKit or WebRTC
"""


def test_parse_resume_splits_known_headers() -> None:
    sections = parse_sections(RESUME_SAMPLE, doc_type="resume")
    kinds = [s.kind for s in sections]
    assert "experience" in kinds
    assert "projects" in kinds
    assert "skills" in kinds
    exp = next(s for s in sections if s.kind == "experience")
    assert "Acme Corp" in exp.text
    assert "Beta Inc" in exp.text


def test_parse_markdown_jd_headings() -> None:
    sections = parse_sections(JD_SAMPLE, doc_type="jd")
    kinds = [s.kind for s in sections]
    assert "requirements" in kinds
    assert "nice_to_have" in kinds
    req = next(s for s in sections if s.kind == "requirements")
    assert "Postgres" in req.text


def test_parse_empty_yields_no_sections() -> None:
    assert parse_sections("   \n  ", doc_type="resume") == []


def test_parse_no_headers_single_other_section() -> None:
    sections = parse_sections("Just a short bio with no headings.", doc_type="resume")
    assert len(sections) == 1
    assert sections[0].kind == "other"
    assert "short bio" in sections[0].text


def test_chunk_experience_parent_per_role_and_bullet_children() -> None:
    section = ParsedSection(
        kind="experience",
        title="EXPERIENCE",
        text=(
            "Acme Corp — Senior Engineer (2021–2024)\n"
            "- Built billing API handling 2M req/day\n"
            "- Reduced p99 latency 40% via caching\n"
            "\n"
            "Beta Inc — Software Engineer (2019–2021)\n"
            "- Shipped search ranking v2\n"
        ),
        ordinal=0,
    )
    chunks = chunk_section(section, doc_type="resume")
    parents = [c for c in chunks if c.parent_index is None]
    children = [c for c in chunks if c.parent_index is not None]
    assert len(parents) == 2
    assert all(p.chunk_kind == "role" for p in parents)
    assert "Acme Corp" in parents[0].content
    assert len(children) >= 3
    assert all(c.chunk_kind == "bullet" for c in children)
    parent_positions = [i for i, c in enumerate(chunks) if c.parent_index is None]
    assert children[0].parent_index == parent_positions[0]
    assert any(c.parent_index == parent_positions[1] for c in children)


def test_chunk_jd_requirements_as_requirement_children() -> None:
    section = ParsedSection(
        kind="requirements",
        title="Requirements",
        text="- 5+ years Python\n- Experience with Postgres\n- System design at scale\n",
        ordinal=0,
    )
    chunks = chunk_section(section, doc_type="jd")
    parents = [c for c in chunks if c.parent_index is None]
    children = [c for c in chunks if c.parent_index is not None]
    assert len(parents) == 1
    assert parents[0].chunk_kind == "section"
    assert len(children) == 3
    assert all(c.chunk_kind == "requirement" for c in children)
    assert "Postgres" in children[1].content


def test_chunk_merges_tiny_orphan_bullets() -> None:
    section = ParsedSection(
        kind="experience",
        title="EXPERIENCE",
        text=(
            "Acme — Eng\n"
            "- Built a long billing platform that processes millions of requests "
            "with careful attention to idempotency and retries across regions\n"
            "- ok\n"  # < MIN_CHILD_TOKENS → merge into previous
        ),
        ordinal=0,
    )
    chunks = chunk_section(section, doc_type="resume")
    children = [c for c in chunks if c.parent_index is not None]
    assert len(children) == 1
    assert "ok" in children[0].content


def test_estimate_tokens_roughly_words() -> None:
    assert estimate_tokens("one two three four") >= 4
    assert estimate_tokens("") == 0
