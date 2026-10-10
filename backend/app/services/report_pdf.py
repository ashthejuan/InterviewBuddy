"""Render report markdown to a simple text PDF (stdlib only)."""

from __future__ import annotations

import re
from typing import Iterable

_MD_DECOR = re.compile(r"[*_`]+")
_MAX_LINE = 92
_LINES_PER_PAGE = 48


def _to_latin1(text: str) -> str:
    return (text or "").encode("latin-1", errors="replace").decode("latin-1")


def _escape_pdf(text: str) -> str:
    return _to_latin1(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _plain_line(raw: str) -> str:
    line = raw.rstrip()
    if line.startswith("#"):
        line = line.lstrip("#").strip()
    return _MD_DECOR.sub("", line)


def _wrap(line: str, width: int = _MAX_LINE) -> list[str]:
    if not line:
        return [""]
    words = line.split()
    if not words:
        return [""]
    rows: list[str] = []
    cur = words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= width:
            cur = f"{cur} {w}"
        else:
            rows.append(cur)
            cur = w
    rows.append(cur)
    return rows


def _iter_display_lines(markdown: str) -> Iterable[str]:
    for raw in (markdown or "").splitlines():
        for part in _wrap(_plain_line(raw)):
            yield part


def _page_content(lines: list[str]) -> str:
    cmds = ["BT", "/F1 11 Tf", "50 742 Td", "14 TL"]
    first = True
    for line in lines:
        if first:
            cmds.append(f"({_escape_pdf(line)}) Tj")
            first = False
        else:
            cmds.append("T*")
            cmds.append(f"({_escape_pdf(line)}) Tj")
    cmds.append("ET")
    return "\n".join(cmds)


def render_report_pdf(markdown: str) -> bytes:
    """Return a minimal multi-page PDF from report markdown."""
    display = list(_iter_display_lines(markdown))
    if not display:
        display = ["Interview debrief"]

    pages = [
        display[i : i + _LINES_PER_PAGE] for i in range(0, len(display), _LINES_PER_PAGE)
    ]
    objs: dict[int, str] = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    next_id = 4
    page_obj_ids: list[int] = []
    for page_lines in pages:
        content = _page_content(page_lines)
        content_bytes = content.encode("latin-1", errors="replace")
        content_id = next_id
        next_id += 1
        objs[content_id] = f"<< /Length {len(content_bytes)} >>\nstream\n{content}\nendstream"
        page_id = next_id
        next_id += 1
        objs[page_id] = (
            "<< /Type /Page /Parent 2 0 R "
            "/MediaBox [0 0 612 792] "
            f"/Contents {content_id} 0 R "
            "/Resources << /Font << /F1 3 0 R >> >> >>"
        )
        page_obj_ids.append(page_id)

    kids = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objs[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_obj_ids)} >>"

    out = bytearray(b"%PDF-1.4\n")
    offsets = {0: 0}
    for i in sorted(objs):
        offsets[i] = len(out)
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(objs[i].encode("latin-1", errors="replace"))
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    max_id = max(objs)
    out.extend(f"xref\n0 {max_id + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for i in range(1, max_id + 1):
        out.extend(f"{offsets[i]:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)
