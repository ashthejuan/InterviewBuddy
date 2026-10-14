"""Phase 1 CRUD + Phase 2 document upload/paste."""

from __future__ import annotations

import uuid

from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import AuthedUser, get_current_user, require_owner
from app.config import get_settings
from app.db import get_session
from app.rate_limit import (
    answer_limiter,
    client_key,
    enforce,
    report_retry_limiter,
    upload_limiter,
    voice_token_limiter,
)
from app.models import (
    Document,
    DocumentSection,
    FrontierNode,
    InterviewSession,
    SessionReport,
    SessionResult,
    SessionTopic,
    Turn,
    TurnScore,
    User,
)
from app.schemas import (
    AnswerIn,
    AnswerOut,
    ChunkOut,
    DocumentOut,
    EvidenceOut,
    FrontierNodeOut,
    PasteDocumentIn,
    SectionOut,
    SessionCreate,
    SessionOut,
    SessionReportOut,
    SessionResultOut,
    TopicOut,
    TranscriptExportOut,
    TurnOut,
    TurnScoreOut,
    UserCreate,
    UserOut,
    VoiceStatusOut,
    VoiceTokenOut,
)
from app.services import grill as grill_svc
from app.services.export_transcript import build_export_payload, write_transcript_json
from app.services.prep import run_extract_job
from app.services.report_job import ensure_report_pending, run_report_job
from app.services.report_pdf import render_report_pdf
from app.services.scorer import finalize_session_results, schedule_turn_score
from app.services.storage import StorageError, build_object_key, put_bytes
from app.services.voice import mint_voice_grant
from app.services.validate_upload import (
    UploadValidationError,
    validate_paste,
    validate_upload,
)

router = APIRouter()


async def _owned_session(
    session_id: uuid.UUID,
    db: AsyncSession,
    user: AuthedUser,
) -> InterviewSession:
    session = await db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    require_owner(user, session.user_id)
    return session


async def _owned_document(
    document_id: uuid.UUID,
    db: AsyncSession,
    user: AuthedUser,
) -> Document:
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    require_owner(user, doc.user_id)
    return doc


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_session),
) -> User:
    user = User(id=body.id or uuid.uuid4(), email=body.email, name=body.name)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="email already registered") from None
    await db.refresh(user)
    return user


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> InterviewSession:
    # Ownership binds to the JWT subject (body.user_id ignored).
    user_id = current_user.id

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail=f"user {user_id} not found — sign up first",
        )

    session = InterviewSession(
        user_id=user_id,
        resume_document_id=body.resume_document_id,
        jd_document_id=body.jd_document_id,
        status="preparing",
        settings=body.settings.model_dump(),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session_by_id(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> InterviewSession:
    return await _owned_session(session_id, db, current_user)


@router.post("/sessions/{session_id}/start", response_model=SessionOut)
async def start_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> InterviewSession:
    session = await _owned_session(session_id, db, current_user)
    if session.status in ("preparing", "failed"):
        raise HTTPException(
            status_code=409,
            detail=f"session not ready (status={session.status})",
        )
    if session.status == "ready":
        now = datetime.now(timezone.utc)
        duration = int((session.settings or {}).get("duration_minutes", 30))
        session.status = "live"
        session.started_at = now
        session.ends_at = now + timedelta(minutes=duration)
        await grill_svc.begin_interview(db, session)
        await db.commit()
        await db.refresh(session)
    elif session.status == "live":
        # Idempotent re-start: ensure opening question exists
        await grill_svc.begin_interview(db, session)
        await db.commit()
        await db.refresh(session)
    return session


@router.get("/sessions/{session_id}/turns", response_model=list[TurnOut])
async def list_session_turns(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> list[Turn]:
    await _owned_session(session_id, db, current_user)
    result = await db.execute(
        select(Turn)
        .where(Turn.session_id == session_id)
        .order_by(Turn.created_at, Turn.id)
    )
    return list(result.scalars().all())


@router.post("/sessions/{session_id}/answer", response_model=AnswerOut)
async def answer_session(
    session_id: uuid.UUID,
    body: AnswerIn,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> AnswerOut:
    enforce(
        answer_limiter,
        client_key(request, str(current_user.id)),
        route="answer",
    )
    session = await _owned_session(session_id, db, current_user)
    if session.status != "live":
        raise HTTPException(
            status_code=409,
            detail=f"session not live (status={session.status})",
        )
    user_turn, agent_turn = await grill_svc.submit_answer(db, session, body.text.strip())
    await db.commit()
    schedule_turn_score(user_turn.id)
    await db.refresh(session)
    await db.refresh(user_turn)
    if agent_turn is not None:
        await db.refresh(agent_turn)
    if session.status == "completed":
        background_tasks.add_task(run_report_job, session_id)
    return AnswerOut(
        session=SessionOut.model_validate(session),
        user_turn=TurnOut.model_validate(user_turn),
        agent_turn=TurnOut.model_validate(agent_turn) if agent_turn else None,
    )


@router.post("/sessions/{session_id}/end", response_model=SessionOut)
async def end_session(
    session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> InterviewSession:
    session = await _owned_session(session_id, db, current_user)
    if session.status not in ("live", "completed"):
        raise HTTPException(
            status_code=409,
            detail=f"session cannot end (status={session.status})",
        )
    if session.status == "live":
        await grill_svc.end_interview(db, session)
        await db.commit()
        await db.refresh(session)
        background_tasks.add_task(run_report_job, session_id)
    elif session.status == "completed":
        # Already wrapped (e.g. timer) — ensure a report job exists.
        row = (
            await db.execute(select(SessionReport).where(SessionReport.session_id == session_id))
        ).scalar_one_or_none()
        if row is None or row.status != "ready":
            await ensure_report_pending(db, session_id)
            await db.commit()
            background_tasks.add_task(run_report_job, session_id)
    return session


@router.get("/sessions/{session_id}/report", response_model=SessionReportOut)
async def get_session_report(
    session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> SessionReportOut:
    session = await _owned_session(session_id, db, current_user)
    if session.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"report available after the interview ends (status={session.status})",
        )
    row = (
        await db.execute(select(SessionReport).where(SessionReport.session_id == session_id))
    ).scalar_one_or_none()
    if row is None:
        # Ensure results exist before assembling the report.
        result = (
            await db.execute(select(SessionResult).where(SessionResult.session_id == session_id))
        ).scalar_one_or_none()
        if result is None:
            await finalize_session_results(db, session)
        row = await ensure_report_pending(db, session_id)
        await db.commit()
        await db.refresh(row)
        background_tasks.add_task(run_report_job, session_id)
    elif row.status == "pending":
        background_tasks.add_task(run_report_job, session_id)
    return SessionReportOut.model_validate(row)


@router.post("/sessions/{session_id}/report/retry", response_model=SessionReportOut)
async def retry_session_report(
    session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> SessionReportOut:
    enforce(
        report_retry_limiter,
        client_key(request, str(current_user.id)),
        route="report_retry",
    )
    session = await _owned_session(session_id, db, current_user)
    if session.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"report available after the interview ends (status={session.status})",
        )
    row = await ensure_report_pending(db, session_id, force=True)
    await db.commit()
    await db.refresh(row)
    background_tasks.add_task(run_report_job, session_id)
    return SessionReportOut.model_validate(row)


@router.get("/sessions/{session_id}/report.pdf")
async def download_session_report_pdf(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> Response:
    session = await _owned_session(session_id, db, current_user)
    if session.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"report available after the interview ends (status={session.status})",
        )
    row = (
        await db.execute(select(SessionReport).where(SessionReport.session_id == session_id))
    ).scalar_one_or_none()
    if row is None or row.status != "ready" or not row.report_markdown:
        raise HTTPException(
            status_code=409,
            detail=f"report PDF available when status=ready (status={row.status if row else 'missing'})",
        )
    pdf = render_report_pdf(row.report_markdown)
    filename = f"interview-report-{str(session_id)[:8]}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sessions/{session_id}/results", response_model=SessionResultOut)
async def get_session_results(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> SessionResultOut:
    session = await _owned_session(session_id, db, current_user)
    if session.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"results available after the interview ends (status={session.status})",
        )
    result = (
        await db.execute(select(SessionResult).where(SessionResult.session_id == session_id))
    ).scalar_one_or_none()
    if result is None:
        # Sessions completed before scoring shipped get a rollup on first read.
        result = await finalize_session_results(db, session)
        await db.commit()

    topics = (
        await db.execute(
            select(SessionTopic)
            .where(SessionTopic.session_id == session_id)
            .order_by(SessionTopic.priority.desc(), SessionTopic.title)
        )
    ).scalars().all()
    scored = (
        await db.execute(
            select(Turn, TurnScore)
            .join(TurnScore, TurnScore.turn_id == Turn.id)
            .where(Turn.session_id == session_id)
            .options(selectinload(TurnScore.evidence))
            .order_by(Turn.created_at, Turn.id)
        )
    ).all()
    return SessionResultOut(
        session_id=session_id,
        overall_score=result.overall_score,
        hire_signal=result.hire_signal,
        strengths=result.strengths,
        gaps=result.gaps,
        coverage_summary=result.coverage_summary,
        topics=[TopicOut.model_validate(t) for t in topics],
        turn_scores=[
            TurnScoreOut(
                turn_id=turn.id,
                topic_id=turn.topic_id,
                answer=turn.normalized_text or turn.raw_text,
                correctness=score.correctness,
                relevance=score.relevance,
                depth=score.depth,
                structure=score.structure,
                honesty=score.honesty,
                confidence=score.confidence,
                rationale=score.rationale,
                flags=score.flags or {},
                evidence=[EvidenceOut.model_validate(e) for e in score.evidence],
            )
            for turn, score in scored
        ],
    )


@router.post(
    "/sessions/{session_id}/export",
    response_model=TranscriptExportOut,
)
async def export_session_transcript(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> TranscriptExportOut:
    """Write transcript (+ results if present) to repo `interview_logs/interview_N.json`."""
    session = await _owned_session(session_id, db, current_user)
    if session.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"export available after the interview ends (status={session.status})",
        )

    turns = (
        await db.execute(
            select(Turn)
            .where(Turn.session_id == session_id)
            .order_by(Turn.created_at, Turn.id)
        )
    ).scalars().all()
    topics = (
        await db.execute(
            select(SessionTopic)
            .where(SessionTopic.session_id == session_id)
            .order_by(SessionTopic.priority.desc(), SessionTopic.title)
        )
    ).scalars().all()
    result = (
        await db.execute(select(SessionResult).where(SessionResult.session_id == session_id))
    ).scalar_one_or_none()

    results_payload = None
    if result is not None:
        results_payload = {
            "overall_score": result.overall_score,
            "hire_signal": result.hire_signal,
            "strengths": result.strengths,
            "gaps": result.gaps,
            "coverage_summary": result.coverage_summary,
        }

    payload = build_export_payload(
        session_id=str(session.id),
        status=session.status,
        settings=session.settings or {},
        started_at=session.started_at,
        ends_at=session.ends_at,
        topics=[
            {
                "id": str(t.id),
                "title": t.title,
                "kind": t.kind,
                "status": t.status,
                "priority": t.priority,
                "rollup_scores": t.rollup_scores or {},
            }
            for t in topics
        ],
        turns=[
            {
                "id": str(t.id),
                "role": t.role,
                "text": t.normalized_text or t.raw_text,
                "raw_text": t.raw_text,
                "topic_id": str(t.topic_id) if t.topic_id else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in turns
        ],
        results=results_payload,
    )
    path = write_transcript_json(payload)
    return TranscriptExportOut(
        path=str(path),
        filename=path.name,
        session_id=session_id,
    )


@router.get("/voice/status", response_model=VoiceStatusOut)
async def voice_status() -> VoiceStatusOut:
    return VoiceStatusOut(enabled=get_settings().voice_enabled)


@router.post("/sessions/{session_id}/voice/token", response_model=VoiceTokenOut)
async def create_voice_token(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> VoiceTokenOut:
    enforce(
        voice_token_limiter,
        client_key(request, str(current_user.id)),
        route="voice_token",
    )
    settings = get_settings()
    if not settings.voice_enabled:
        raise HTTPException(status_code=503, detail="voice is not configured on this server")
    session = await _owned_session(session_id, db, current_user)
    if session.status != "live":
        raise HTTPException(
            status_code=409,
            detail=f"session not live (status={session.status}) — start the interview first",
        )
    grant = mint_voice_grant(session_id=session.id, user_id=session.user_id, settings=settings)
    return VoiceTokenOut(
        server_url=grant.server_url,
        room_name=grant.room_name,
        participant_identity=grant.participant_identity,
        token=grant.token,
        expires_at=grant.expires_at,
    )


@router.get("/sessions/{session_id}/topics", response_model=list[TopicOut])
async def list_session_topics(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> list[SessionTopic]:
    await _owned_session(session_id, db, current_user)
    result = await db.execute(
        select(SessionTopic)
        .where(SessionTopic.session_id == session_id)
        .order_by(SessionTopic.priority.desc(), SessionTopic.title)
    )
    return list(result.scalars().all())


@router.get("/sessions/{session_id}/frontier", response_model=list[FrontierNodeOut])
async def list_session_frontier(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> list[FrontierNode]:
    await _owned_session(session_id, db, current_user)
    result = await db.execute(
        select(FrontierNode).where(FrontierNode.session_id == session_id)
    )
    return list(result.scalars().all())


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> Document:
    return await _owned_document(document_id, db, current_user)


@router.get("/documents/{document_id}/sections", response_model=list[SectionOut])
async def list_document_sections(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> list[SectionOut]:
    await _owned_document(document_id, db, current_user)

    result = await db.execute(
        select(DocumentSection)
        .where(DocumentSection.document_id == document_id)
        .options(selectinload(DocumentSection.chunks))
        .order_by(DocumentSection.ordinal)
    )
    sections = result.scalars().all()
    out: list[SectionOut] = []
    for sec in sections:
        chunks = [
            ChunkOut(
                id=c.id,
                chunk_kind=c.chunk_kind,
                content=c.content,
                parent_chunk_id=c.parent_chunk_id,
                metadata=c.metadata_ or {},
                has_embedding=c.embedding is not None,
            )
            for c in sec.chunks
        ]
        out.append(
            SectionOut(
                id=sec.id,
                kind=sec.kind,
                title=sec.title,
                text=sec.text,
                ordinal=sec.ordinal,
                chunks=chunks,
            )
        )
    return out


@router.post(
    "/sessions/{session_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    request: Request,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> Document:
    enforce(
        upload_limiter,
        client_key(request, str(current_user.id)),
        route="upload",
    )
    if doc_type not in ("resume", "jd"):
        raise HTTPException(status_code=400, detail="doc_type must be resume or jd")

    session = await _owned_session(session_id, db, current_user)

    settings = get_settings()
    data = await file.read(settings.max_upload_bytes + 1)
    filename = file.filename or "upload.bin"

    try:
        validated = validate_upload(
            data,
            filename=filename,
            content_type=file.content_type,
            max_bytes=settings.max_upload_bytes,
        )
    except UploadValidationError as exc:
        code = 413 if "too large" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    document_id = uuid.uuid4()
    key = build_object_key(
        user_id=session.user_id,
        session_id=session.id,
        document_id=document_id,
        filename=validated.original_filename,
    )
    try:
        bucket, key = put_bytes(key=key, data=data, content_type=validated.content_type)
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    doc = Document(
        id=document_id,
        user_id=session.user_id,
        doc_type=doc_type,
        r2_bucket=bucket,
        r2_key=key,
        content_type=validated.content_type,
        original_filename=validated.original_filename,
        byte_size=validated.byte_size,
        parse_status="pending",
    )
    db.add(doc)
    if doc_type == "resume":
        session.resume_document_id = document_id
    else:
        session.jd_document_id = document_id
    await db.commit()
    await db.refresh(doc)

    background_tasks.add_task(run_extract_job, document_id, data, validated.kind)
    return doc


@router.post(
    "/sessions/{session_id}/documents/paste",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def paste_document(
    session_id: uuid.UUID,
    body: PasteDocumentIn,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: AuthedUser = Depends(get_current_user),
) -> Document:
    enforce(
        upload_limiter,
        client_key(request, str(current_user.id)),
        route="paste",
    )
    session = await _owned_session(session_id, db, current_user)

    settings = get_settings()
    try:
        text = validate_paste(body.text, max_chars=settings.max_paste_chars)
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = text.encode("utf-8")
    filename = f"{body.doc_type}.txt"
    document_id = uuid.uuid4()
    key = build_object_key(
        user_id=session.user_id,
        session_id=session.id,
        document_id=document_id,
        filename=filename,
    )
    try:
        bucket, key = put_bytes(key=key, data=data, content_type="text/plain")
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    doc = Document(
        id=document_id,
        user_id=session.user_id,
        doc_type=body.doc_type,
        r2_bucket=bucket,
        r2_key=key,
        content_type="text/plain",
        original_filename=filename,
        byte_size=len(data),
        parse_status="pending",
    )
    db.add(doc)
    if body.doc_type == "resume":
        session.resume_document_id = document_id
    else:
        session.jd_document_id = document_id
    await db.commit()
    await db.refresh(doc)

    background_tasks.add_task(run_extract_job, document_id, data, "paste")
    return doc
