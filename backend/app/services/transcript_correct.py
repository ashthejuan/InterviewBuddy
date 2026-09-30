"""Deterministic transcript correction against the session lexicon (PRD §7). No LLM.

Order per span: exact (incl. split-word joins) → spoken alias → fuzzy. Ambiguous fuzzy
ties abstain. Only terms from the session lexicon + a small global glossary are emitted.
"""

from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz, process

FUZZY_THRESHOLD = 90.0
FUZZY_TIE_MARGIN = 2.0
_MAX_NGRAM = 4
_FUZZY_MAX_NGRAM = 2
_FUZZY_MIN_LEN = 5

# Unambiguous tech terms only — no common English words (e.g. "React", "Spark", "Go").
GLOBAL_GLOSSARY: tuple[str, ...] = (
    "AWS",
    "BigQuery",
    "Celery",
    "Django",
    "Docker",
    "DynamoDB",
    "Elasticsearch",
    "FastAPI",
    "GCP",
    "GitHub",
    "GitLab",
    "Grafana",
    "GraphQL",
    "gRPC",
    "JavaScript",
    "Kafka",
    "Kubernetes",
    "LiveKit",
    "MongoDB",
    "MySQL",
    "Next.js",
    "Nginx",
    "Node.js",
    "NumPy",
    "pgvector",
    "Postgres",
    "PostgreSQL",
    "PyTorch",
    "RabbitMQ",
    "Redis",
    "SQLAlchemy",
    "TensorFlow",
    "Terraform",
    "TypeScript",
)

# Phonetic spellings STT tends to emit → canonical term (must also be in the vocabulary).
SPOKEN_ALIASES: dict[str, str] = {
    "sequel alchemy": "SQLAlchemy",
    "my sequel": "MySQL",
    "postgres sequel": "PostgreSQL",
    "postgre sequel": "PostgreSQL",
    "post gres q l": "PostgreSQL",
    "graph sequel": "GraphQL",
    "g r p c": "gRPC",
    "k eight s": "Kubernetes",
    "k8s": "Kubernetes",
    "pie torch": "PyTorch",
    "engine x": "Nginx",
    "num pie": "NumPy",
    "jango": "Django",
}

_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[.+#][A-Za-z0-9]+)*[+#]*")
_STOPWORDS = frozenset(
    {
        "about", "after", "again", "being", "could", "every", "first", "other", "their",
        "there", "these", "those", "under", "where", "which", "while", "would",
    }
)


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9+#]", "", text.lower())


def build_vocabulary(lexicon: dict[str, Any] | None) -> list[str]:
    """Lexicon skills/tools/companies first, then glossary. Metrics are never corrected."""
    seen: set[str] = set()
    vocab: list[str] = []
    lex = lexicon or {}
    candidates: list[str] = []
    for key in ("skills", "tools", "companies"):
        vals = lex.get(key) or []
        if isinstance(vals, list):
            candidates.extend(str(v) for v in vals)
    candidates.extend(GLOBAL_GLOSSARY)
    for term in candidates:
        term = term.strip()
        key = _compact(term)
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        vocab.append(term)
    return vocab


def correct_transcript(
    text: str, lexicon: dict[str, Any] | None
) -> tuple[str, list[dict[str, Any]]]:
    """Return (normalized_text, corrections[]). Corrections carry offsets into the raw text."""
    if not text:
        return text, []
    vocab = build_vocabulary(lexicon)
    by_key = {_compact(t): t for t in vocab}
    alias_by_key = {
        _compact(spoken): canonical
        for spoken, canonical in SPOKEN_ALIASES.items()
        if _compact(canonical) in by_key
    }
    fuzzy_keys = [k for k in by_key if len(k) >= 3]

    tokens = list(_TOKEN.finditer(text))
    corrections: list[dict[str, Any]] = []
    i = 0
    while i < len(tokens):
        hit = _match_exact_or_alias(text, tokens, i, by_key, alias_by_key)
        if hit is None:
            hit = _match_fuzzy(text, tokens, i, by_key, fuzzy_keys)
        if hit is None:
            i += 1
            continue
        n, canonical, method, score = hit
        start, end = tokens[i].start(), tokens[i + n - 1].end()
        original = text[start:end]
        if original != canonical:
            corrections.append(
                {
                    "from": original,
                    "to": canonical,
                    "method": method,
                    "score": score,
                    "start": start,
                    "end": end,
                }
            )
        i += n

    out = text
    for c in reversed(corrections):
        out = out[: c["start"]] + c["to"] + out[c["end"] :]
    return out, corrections


def _span(text: str, tokens: list[re.Match[str]], i: int, n: int) -> str | None:
    """Joined span text if tokens i..i+n-1 are separated only by whitespace."""
    if i + n > len(tokens):
        return None
    for a, b in zip(tokens[i : i + n - 1], tokens[i + 1 : i + n]):
        if text[a.end() : b.start()].strip():
            return None
    return text[tokens[i].start() : tokens[i + n - 1].end()]


def _match_exact_or_alias(
    text: str,
    tokens: list[re.Match[str]],
    i: int,
    by_key: dict[str, str],
    alias_by_key: dict[str, str],
) -> tuple[int, str, str, float] | None:
    for n in range(_MAX_NGRAM, 0, -1):
        span = _span(text, tokens, i, n)
        if span is None:
            continue
        key = _compact(span)
        if key in by_key:
            canonical = by_key[key]
            same_words = " ".join(span.lower().split()) == canonical.lower()
            return n, canonical, "exact" if same_words else "alias", 100.0
        if key in alias_by_key:
            return n, alias_by_key[key], "alias", 100.0
    return None


def _match_fuzzy(
    text: str,
    tokens: list[re.Match[str]],
    i: int,
    by_key: dict[str, str],
    fuzzy_keys: list[str],
) -> tuple[int, str, str, float] | None:
    if not fuzzy_keys:
        return None
    for n in range(_FUZZY_MAX_NGRAM, 0, -1):
        span = _span(text, tokens, i, n)
        if span is None:
            continue
        words = span.split()
        if not all(w.isalpha() for w in words):
            continue
        if n == 1 and words[0].lower() in _STOPWORDS:
            continue
        key = _compact(span)
        if len(key) < _FUZZY_MIN_LEN:
            continue
        found = process.extract(
            key, fuzzy_keys, scorer=fuzz.ratio, limit=2, score_cutoff=FUZZY_THRESHOLD
        )
        if not found:
            continue
        if len(found) > 1 and found[0][1] - found[1][1] < FUZZY_TIE_MARGIN:
            return None
        best_key, score, _ = found[0]
        return n, by_key[best_key], "fuzzy", round(float(score), 1)
    return None
