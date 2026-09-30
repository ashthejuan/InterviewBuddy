"""Unit: deterministic transcript correction (PRD §7)."""

from __future__ import annotations

from app.services.transcript_correct import build_vocabulary, correct_transcript

LEXICON = {
    "skills": ["FastAPI", "Postgres", "Python"],
    "tools": ["FastAPI", "Postgres", "Python"],
    "companies": ["Acme Corp"],
    "metrics": ["40%", "2M req/day"],
}


def test_exact_match_fixes_casing() -> None:
    text, corrections = correct_transcript("i used fastapi daily", LEXICON)
    assert text == "i used FastAPI daily"
    assert corrections == [
        {"from": "fastapi", "to": "FastAPI", "method": "exact", "score": 100.0, "start": 7, "end": 14}
    ]


def test_split_words_join_to_lexicon_term() -> None:
    text, corrections = correct_transcript("we built it on fast api.", LEXICON)
    assert text == "we built it on FastAPI."
    assert corrections[0]["method"] == "alias"


def test_spoken_alias_maps_only_when_term_in_vocabulary() -> None:
    text, _ = correct_transcript("then sequel alchemy for the ORM", LEXICON)
    assert text == "then SQLAlchemy for the ORM"  # glossary term

    text, corrections = correct_transcript("I like my sequel", {"skills": []})
    assert "MySQL" in text
    assert corrections[0]["method"] == "alias"


def test_fuzzy_repairs_near_miss() -> None:
    text, corrections = correct_transcript("latency on postgress was bad", LEXICON)
    assert text == "latency on Postgres was bad"
    assert corrections[0]["method"] == "fuzzy"
    assert corrections[0]["score"] >= 90


def test_fuzzy_never_invents_outside_vocabulary() -> None:
    text, corrections = correct_transcript("the zorblatt service", LEXICON)
    assert text == "the zorblatt service"
    assert corrections == []


def test_ambiguous_fuzzy_tie_abstains() -> None:
    lex = {"tools": ["StreamLoaderX", "StreamLoaderY"]}
    text, corrections = correct_transcript("we used streamloaderz", lex)
    assert text == "we used streamloaderz"
    assert corrections == []


def test_common_words_and_metrics_untouched() -> None:
    text, corrections = correct_transcript("Reduced p99 by 40% for the team", LEXICON)
    assert text == "Reduced p99 by 40% for the team"
    assert corrections == []


def test_already_correct_is_noop() -> None:
    text, corrections = correct_transcript("FastAPI and Postgres", LEXICON)
    assert text == "FastAPI and Postgres"
    assert corrections == []


def test_multiword_company_exact() -> None:
    text, _ = correct_transcript("at acme corp we shipped", LEXICON)
    assert text == "at Acme Corp we shipped"


def test_empty_lexicon_and_text() -> None:
    assert correct_transcript("", {}) == ("", [])
    assert correct_transcript("hello there", None) == ("hello there", [])


def test_build_vocabulary_excludes_metrics_and_dedupes() -> None:
    vocab = build_vocabulary(LEXICON)
    assert "FastAPI" in vocab
    assert "40%" not in vocab
    assert len(vocab) == len(set(vocab))
