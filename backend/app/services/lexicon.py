"""Build session.lexicon jsonb for STT keyterms + repair (PRD §7)."""

from __future__ import annotations

import re

_METRIC = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*%|\$\d[\d,]*(?:\.\d+)?[kKmMbB]?|\d[\d,]*(?:\.\d+)?\s*[xX]|"
    r"\d+\s*(?:M|k|K|ms|s)\b|\d[\d,]+\s*(?:req(?:/day)?|users?)\b",
    re.I,
)
_COMPANY = re.compile(
    r"\b([A-Z][A-Za-z0-9]+(?:\s+(?:Corp|Inc|Labs|LLC|Ltd|Technologies|Systems))?)\b"
)
_TOOL_PRETTY = {
    "python": "Python",
    "fastapi": "FastAPI",
    "postgres": "Postgres",
    "postgresql": "PostgreSQL",
    "redis": "Redis",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "docker": "Docker",
    "livekit": "LiveKit",
    "typescript": "TypeScript",
    "sqlalchemy": "SQLAlchemy",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "react": "React",
    "kafka": "Kafka",
    "spark": "Spark",
}
_SKIP_COMPANY = {
    "senior",
    "engineer",
    "software",
    "backend",
    "experience",
    "skills",
    "projects",
    "led",
    "team",
    "reduced",
    "built",
    "python",
    "fastapi",
}


def build_lexicon(*, claim_texts: list[str], chunk_texts: list[str]) -> dict[str, list[str]]:
    skills: set[str] = set()
    tools: set[str] = set()
    companies: set[str] = set()
    metrics: set[str] = set()

    for text in claim_texts + chunk_texts:
        for m in _METRIC.findall(text):
            metrics.add(m.strip())
        for tok in re.findall(r"[A-Za-z][A-Za-z0-9.+#/-]{1,}", text):
            pretty = _TOOL_PRETTY.get(tok.lower())
            if pretty:
                tools.add(pretty)
                skills.add(pretty)
        for m in _COMPANY.finditer(text):
            name = m.group(1)
            if name.lower() in _SKIP_COMPANY or name.lower() in _TOOL_PRETTY:
                continue
            if len(name) >= 3:
                companies.add(name)

    return {
        "skills": sorted(skills),
        "tools": sorted(tools),
        "companies": sorted(companies),
        "metrics": sorted(metrics),
    }
