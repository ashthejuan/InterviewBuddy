"""Phase 6 — render report_json to downloadable markdown."""

from __future__ import annotations

from typing import Any


def _fmt_score(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return "—"


def render_report_markdown(report: dict[str, Any]) -> str:
    meta = report.get("session_meta") or {}
    overall = report.get("overall_signal") or {}
    cov = report.get("coverage_map") or {}
    counts = cov.get("counts") or {}
    prose = report.get("prose") or {}
    lines: list[str] = [
        "# Interview debrief",
        "",
        f"- Session: `{meta.get('session_id', '')}`",
        f"- Duration: {meta.get('duration_minutes', '—')} minutes",
        f"- Seniority: {meta.get('seniority', '—')} · Difficulty: {meta.get('difficulty', '—')}",
        f"- Resume: {meta.get('resume_filename') or '—'}",
        f"- JD: {meta.get('jd_filename') or '—'}",
        f"- Ended: {meta.get('wrap_reason') or '—'}",
        "",
        "## Overall signal",
        "",
        f"**{(overall.get('hire_signal') or 'unknown').replace('_', ' ')}** · "
        f"{_fmt_score(overall.get('overall_score'))} / 5",
        "",
    ]
    summary = prose.get("summary") or overall.get("summary")
    if summary:
        lines.extend([summary, ""])

    dims = overall.get("dims") or {}
    if dims:
        lines.append("### Rubric averages")
        lines.append("")
        for k, v in dims.items():
            lines.append(f"- {k}: {_fmt_score(v)}")
        lines.append("")

    lines.extend(
        [
            "## Coverage",
            "",
            f"Planned topics: {cov.get('planned_n', '—')}. "
            f"Grilled {counts.get('grilled', 0)}, light {counts.get('light', 0)}, "
            f"skipped {counts.get('skipped', 0)}.",
            "",
            "## Topic notes",
            "",
        ]
    )
    for t in report.get("topic_notes") or []:
        title = t.get("title") or "Topic"
        if t.get("insufficient_evidence"):
            lines.append(f"### {title}")
            lines.append("")
            lines.append("_Insufficient evidence — topic was not scored._")
            lines.append("")
            continue
        lines.append(f"### {title}")
        lines.append("")
        lines.append(
            f"- Kind: {t.get('kind')} · Coverage: {t.get('coverage')} · "
            f"Score: {_fmt_score(t.get('composite'))}"
        )
        intents = t.get("intents") or []
        if intents:
            lines.append(f"- Asked about: {'; '.join(intents)}")
        flags = t.get("flags") or {}
        if flags:
            lines.append(f"- Flags: {', '.join(sorted(str(k) for k, v in flags.items() if v))}")
        lines.append("")

    strengths = report.get("strengths") or []
    if strengths:
        lines.extend(["## Strengths", ""])
        for s in strengths:
            lines.append(f"- **{s.get('title')}** — {s.get('reason')}")
        lines.append("")

    gaps = report.get("gaps") or []
    if gaps:
        lines.extend(["## Gaps", ""])
        for g in gaps:
            sev = f" ({g['severity']})" if g.get("severity") else ""
            lines.append(f"- **{g.get('title')}**{sev} — {g.get('reason')}")
        lines.append("")

    if prose.get("pros") or prose.get("cons"):
        lines.extend(["## Pros / cons", ""])
        for p in prose.get("pros") or []:
            lines.append(f"- (+) {p}")
        for c in prose.get("cons") or []:
            lines.append(f"- (−) {c}")
        lines.append("")

    notes = report.get("resume_linked_notes") or []
    if notes:
        lines.extend(["## Resume-linked notes", ""])
        for n in notes:
            lines.append(
                f"- Resume said: _{n.get('claim_text')}_ → interview: "
                f"**{n.get('interview_outcome')}**. {n.get('detail')}"
            )
        lines.append("")

    jd = report.get("jd_alignment")
    if jd:
        lines.extend(["## JD alignment", ""])
        for label, key in (("Covered", "covered"), ("Weak", "weak"), ("Missing", "missing")):
            rows = jd.get(key) or []
            if not rows:
                continue
            lines.append(f"### {label}")
            lines.append("")
            for r in rows:
                lines.append(f"- {r.get('title')} ({r.get('coverage')})")
            lines.append("")

    steps = prose.get("next_steps") or []
    if steps:
        lines.extend(["## Next steps", ""])
        for i, step in enumerate(steps, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
