"""Phase 1 CRUD + Phase 2 document upload/paste."""

from __future__ import annotations

import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import Document, InterviewSession, User
from app.schemas import (
    DocumentOut,
    PasteDocumentIn,
    SessionCreate,
    SessionOut,
    UserCreate,
    UserOut,
)
from app.services.prep import run_extract_job
from app.services.storage import StorageError, build_object_key, put_bytes
from app.services.validate_upload import (
    UploadValidationError,
    validate_paste,
    validate_upload,
)

router = APIRouter()


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
) -> InterviewSession:
    settings = get_settings()
    user_id = body.user_id or uuid.UUID(settings.dev_user_id)

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail=f"user {user_id} not found — create via POST /users first",
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
) -> InterviewSession:
    result = await db.execute(
        select(InterviewSession).where(InterviewSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
) -> Document:
    doc = await db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return doc


@router.post(
    "/sessions/{session_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
) -> Document:
    if doc_type not in ("resume", "jd"):
        raise HTTPException(status_code=400, detail="doc_type must be resume or jd")

    session = await db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

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
    db: AsyncSession = Depends(get_session),
) -> Document:
    session = await db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

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
