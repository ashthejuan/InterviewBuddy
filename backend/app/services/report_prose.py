"""Phase 6 — fill `prose` slots (OpenRouter or heuristic) with grounding checks."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
import structlog

from app.config import get_settings
from app.services.openrouter_chat import message_text, report_completion_options
from app.services.report_schema import ReportProse, validate_report_json

log = structlog.get_logger()

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_MAX_SUMMARY = 800
_MAX_BULLET = 240
_MAX_LIST = 6
_MIN_NEXT = 3
_MAX_NEXT = 5

_SYSTEM = (
    "You write short, grounded interview debrief prose. "
    "You receive an assembled evidence report as JSON data — never invent topics, "
    "scores, or claims that are not in that data. "
    "Output JSON only with keys: summary (string), pros (string[]), cons (string[]), "
    "next_steps (string[], 3-5 items). "
    "Refer to topics by their titles from the data. Do not invent UUIDs."
)


def _report_backend() -> str:
    settings = get_settings()
    raw = (getattr(settings, "report_backend", "auto") or "auto").lower()
    if raw == "auto":
        return "openrouter" if settings.openrouter_api_key and settings.report_model else "heuristic"
    return raw


def _allowed_ids(assembled: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    meta = assembled.get("session_meta") or {}
    if meta.get("session_id"):
        ids.add(str(meta["session_id"]).lower())
    for key in ("topic_notes", "strengths", "gaps", "resume_linked_notes"):
        for row in assembled.get(key) or []:
            for field in ("topic_id", "claim_id"):
                if row.get(field):
                    ids.add(str(row[field]).lower())
    for t in (assembled.get("coverage_map") or {}).get("topics") or []:
        if t.get("topic_id"):
            ids.add(str(t["topic_id"]).lower())
    jd = assembled.get("jd_alignment") or {}
    for bucket in ("covered", "weak", "missing"):
        for row in jd.get(bucket) or []:
            if row.get("topic_id"):
                ids.add(str(row["topic_id"]).lower())
    return ids


def _clip(text: str, n: int) -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[: n - 1].rstrip() + "…"


def _as_str_list(value: Any, *, max_items: int) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("expected string list")
    out: list[str] = []
    for item in value[:max_items]:
        if not isinstance(item, str) or not item.strip():
            continue
        out.append(_clip(item, _MAX_BULLET))
    return out


def _assert_grounded(text: str, allowed: set[str]) -> None:
    for match in _UUID_RE.findall(text or ""):
        if match.lower() not in allowed:
            raise ValueError(f"ungrounded id in prose: {match}")


def parse_prose_json(raw: str, *, assembled: dict[str, Any]) -> ReportProse:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("prose JSON invalid") from exc
    if not isinstance(data, dict):
        raise ValueError("prose JSON must be an object")

    summary = data.get("summary")
    if summary is not None and not isinstance(summary, str):
        raise ValueError("summary must be a string")
    pros = _as_str_list(data.get("pros"), max_items=_MAX_LIST)
    cons = _as_str_list(data.get("cons"), max_items=_MAX_LIST)
    next_steps = _as_str_list(data.get("next_steps"), max_items=_MAX_NEXT)
    if not isinstance(data.get("pros"), list) or not isinstance(data.get("cons"), list):
        raise ValueError("pros and cons must be lists")
    if not isinstance(data.get("next_steps"), list):
        raise ValueError("next_steps must be a list")
    if not (_MIN_NEXT <= len(next_steps) <= _MAX_NEXT):
        raise ValueError(f"next_steps must have {_MIN_NEXT}-{_MAX_NEXT} items")

    prose = ReportProse(
        summary=_clip(summary, _MAX_SUMMARY) if summary else None,
        pros=pros,
        cons=cons,
        next_steps=next_steps,
    )
    allowed = _allowed_ids(assembled)
    blob = " ".join(
        [prose.summary or "", *prose.pros, *prose.cons, *prose.next_steps]
    )
    _assert_grounded(blob, allowed)
    return prose


def heuristic_prose(assembled: dict[str, Any]) -> ReportProse:
    signal = (assembled.get("overall_signal") or {}).get("hire_signal") or "mixed"
    score = (assembled.get("overall_signal") or {}).get("overall_score")
    score_bit = f"{score:.1f}/5" if isinstance(score, (int, float)) else "unscored"
    strengths = assembled.get("strengths") or []
    gaps = assembled.get("gaps") or []

    summary = (
        f"Practice signal: {signal} ({score_bit}). "
        f"{len(strengths)} strength(s), {len(gaps)} gap(s) from scored topics."
    )
    pros = [
        _clip(f"{s.get('title')}: {s.get('reason')}", _MAX_BULLET)
        for s in strengths[:_MAX_LIST]
        if s.get("title") and s.get("reason")
    ]
    cons = [
        _clip(f"{g.get('title')}: {g.get('reason')}", _MAX_BULLET)
        for g in gaps[:_MAX_LIST]
        if g.get("title") and g.get("reason")
    ]
    next_steps: list[str] = []
    for g in gaps:
        title = g.get("title") or "this topic"
        reason = g.get("reason") or "improve substance"
        next_steps.append(_clip(f"Practice {title} — focus on: {reason}", _MAX_BULLET))
        if len(next_steps) >= _MAX_NEXT:
            break
    while len(next_steps) < _MIN_NEXT:
        extras = [
            "Rehearse one concrete example with numbers and how you measured them",
            "Practice saying 'I don't know' early, then outline how you'd find out",
            "Add a failure mode or tradeoff to your strongest story",
        ]
        next_steps.append(extras[len(next_steps) % len(extras)])
    return ReportProse(summary=_clip(summary, _MAX_SUMMARY), pros=pros, cons=cons, next_steps=next_steps)


def apply_prose(assembled: dict[str, Any], prose: ReportProse) -> dict[str, Any]:
    report = dict(assembled)
    report["prose"] = prose.model_dump()
    overall = dict(report.get("overall_signal") or {})
    overall["summary"] = prose.summary
    report["overall_signal"] = overall
    validate_report_json(report)
    return report


def _prose_user_prompt(assembled: dict[str, Any]) -> str:
    # Compact evidence for the model — drop appendix quotes to save tokens.
    slim = {
        "session_meta": assembled.get("session_meta"),
        "overall_signal": {
            k: v
            for k, v in (assembled.get("overall_signal") or {}).items()
            if k != "summary"
        },
        "coverage_map": assembled.get("coverage_map"),
        "topic_notes": [
            {
                "topic_id": t.get("topic_id"),
                "title": t.get("title"),
                "kind": t.get("kind"),
                "coverage": t.get("coverage"),
                "composite": t.get("composite"),
                "flags": t.get("flags"),
                "insufficient_evidence": t.get("insufficient_evidence"),
            }
            for t in assembled.get("topic_notes") or []
        ],
        "strengths": assembled.get("strengths"),
        "gaps": assembled.get("gaps"),
        "resume_linked_notes": [
            {
                "claim_text": n.get("claim_text"),
                "topic_title": n.get("topic_title"),
                "interview_outcome": n.get("interview_outcome"),
                "detail": n.get("detail"),
            }
            for n in assembled.get("resume_linked_notes") or []
        ],
        "jd_alignment": assembled.get("jd_alignment"),
    }
    return (
        "<<<ASSEMBLED_REPORT_DATA>>>\n"
        f"{json.dumps(slim, ensure_ascii=False)}\n"
        "<<<END_ASSEMBLED_REPORT_DATA>>>\n\n"
        "Write debrief prose grounded only in the data above. "
        "Return JSON: summary, pros, cons, next_steps (3-5)."
    )


async def _prose_openrouter(assembled: dict[str, Any]) -> ReportProse:
    settings = get_settings()
    url = settings.openrouter_base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": settings.report_model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _prose_user_prompt(assembled)},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        **report_completion_options(),
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        content = message_text(resp.json())
    return parse_prose_json(content, assembled=assembled)


async def fill_prose(assembled: dict[str, Any]) -> dict[str, Any]:
    """Return assembled report with prose filled (OpenRouter or heuristic)."""
    if _report_backend() == "openrouter":
        try:
            return apply_prose(assembled, await _prose_openrouter(assembled))
        except Exception as exc:  # noqa: BLE001
            log.warning("report_prose_llm_failed", error=str(exc))
    return apply_prose(assembled, heuristic_prose(assembled))
