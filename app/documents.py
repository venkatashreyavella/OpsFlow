import hashlib
import io
from pathlib import PurePosixPath
from typing import Annotated, Literal
import uuid
import zipfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from .auth import CurrentEmployee, Db, current_employee, operator
from .models import Document, DocumentVersion, Order
from .settings import MAX_UPLOAD_BYTES, UPLOAD_DIR


router = APIRouter(prefix="/documents", tags=["Documents"], dependencies=[Depends(current_employee)])
Category = Literal["invoice", "purchase_order", "delivery", "other"]


def public_document(document: Document) -> dict:
    versions = [
        {key: getattr(version, key) for key in ("id", "version", "original_name", "sha256", "size_bytes", "uploaded_by", "created_at")}
        for version in document.versions
    ]
    return {"id": document.id, "name": document.name, "category": document.category, "order_id": document.order_id, "archived": document.archived, "versions": versions}


def get_document(document_id: int, session: Db, lock=False) -> Document:
    statement = select(Document).where(Document.id == document_id).options(selectinload(Document.versions))
    if lock:
        statement = statement.with_for_update()
    document = session.scalar(statement)
    if document is None:
        raise HTTPException(404, "Document not found")
    return document


def validate_file(name: str, content: bytes) -> None:
    extension = PurePosixPath(name).suffix.lower()
    signatures = {".pdf": b"%PDF-", ".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}
    if extension in signatures:
        if not content.startswith(signatures[extension]):
            raise HTTPException(422, "The file content does not match its extension")
    elif extension in {".txt", ".csv"}:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(422, "Text and CSV files must use UTF-8 encoding") from exc
        if "\x00" in text:
            raise HTTPException(422, "The text file contains invalid content")
    elif extension == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = archive.namelist()
                if "[Content_Types].xml" not in names or "word/document.xml" not in names or sum(item.file_size for item in archive.infolist()) > 25 * 1024 * 1024:
                    raise HTTPException(422, "The Word document is invalid or too large when expanded")
        except zipfile.BadZipFile as exc:
            raise HTTPException(422, "The Word document is invalid") from exc
    else:
        raise HTTPException(422, "Supported files are PDF, DOCX, PNG, JPEG, UTF-8 TXT, and CSV")


async def store_version(file: UploadFile, document: Document, employee_id: int, session: Db) -> None:
    name = PurePosixPath((file.filename or "").replace("\\", "/")).name
    if not name or len(name) > 255 or any(ord(character) < 32 for character in name):
        raise HTTPException(422, "The filename is invalid")
    content = bytearray()
    try:
        while chunk := await file.read(65536):
            content.extend(chunk)
            if len(content) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "Files must be 10 MB or smaller")
    finally:
        await file.close()
    if not content:
        raise HTTPException(422, "The file is empty")
    validate_file(name, bytes(content))
    key = uuid.uuid4().hex
    path = UPLOAD_DIR / key
    temporary = UPLOAD_DIR / f"{key}.tmp"
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
        version = max((item.version for item in document.versions), default=0) + 1
        document.versions.append(DocumentVersion(
            version=version, original_name=name, storage_key=key,
            sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content), uploaded_by=employee_id,
        ))
        session.add(document)
        session.commit()
    except Exception as exc:
        session.rollback()
        path.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, "Another version was saved at the same time. Refresh and upload again") from exc
        raise


@router.get("")
def list_documents(
    session: Db, archived: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    documents = session.scalars(select(Document).where(Document.archived == archived).options(selectinload(Document.versions)).order_by(Document.id.desc()).offset(offset).limit(limit))
    return [public_document(document) for document in documents]


@router.post("", status_code=201, dependencies=[Depends(operator)])
async def create_document(
    session: Db, employee: CurrentEmployee,
    name: Annotated[str, Form(min_length=1, max_length=200)],
    category: Annotated[Category, Form()],
    file: Annotated[UploadFile, File()],
    order_id: Annotated[int | None, Form(gt=0)] = None,
):
    if not name.strip() or "\x00" in name:
        raise HTTPException(422, "Enter a document name")
    if order_id is not None and session.get(Order, order_id) is None:
        raise HTTPException(404, "Order not found")
    document = Document(name=name.strip(), category=category, order_id=order_id)
    await store_version(file, document, employee.id, session)
    return public_document(document)


@router.post("/{document_id}/versions", status_code=201, dependencies=[Depends(operator)])
async def create_version(document_id: int, session: Db, employee: CurrentEmployee, file: Annotated[UploadFile, File()]):
    document = get_document(document_id, session, lock=True)
    if document.archived:
        raise HTTPException(409, "Restore this document before adding a version")
    await store_version(file, document, employee.id, session)
    return public_document(document)


@router.patch("/{document_id}/archive", dependencies=[Depends(operator)])
def archive_document(document_id: int, archived: bool, session: Db):
    document = get_document(document_id, session, lock=True)
    document.archived = archived
    session.commit()
    return public_document(document)


@router.get("/{document_id}/download")
def download(document_id: int, session: Db, version: Annotated[int | None, Query(gt=0)] = None):
    document = get_document(document_id, session)
    versions = [item for item in document.versions if version is None or item.version == version]
    if not versions:
        raise HTTPException(404, "Document version not found")
    selected = max(versions, key=lambda item: item.version)
    path = UPLOAD_DIR / selected.storage_key
    if not path.is_file():
        raise HTTPException(404, "The stored file is missing. Run a data-quality scan")
    return FileResponse(path, filename=selected.original_name, media_type="application/octet-stream", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
