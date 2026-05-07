import asyncio
import hashlib
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status

from app.config import get_settings
from app.core.dependencies import get_current_user, get_folder_for_user
from app.database import get_database
from app.models.file import FileOut, FileStatus
from app.models.folder import Folder
from app.models.user import User
from app.repositories import FileRepository, FolderRepository
from app.services.ingestion import delete_file_data, run_ingestion

logger = logging.getLogger(__name__)
router = APIRouter(tags=["files"])

_status_queues: dict[str, list[asyncio.Queue]] = {}


def _publish_status(folder_id: str, payload: dict) -> None:
    for q in _status_queues.get(folder_id, []):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


async def _ingestion_with_notify(file_id: str, folder_id: str) -> None:
    db = get_database()
    try:
        await run_ingestion(file_id)
    except Exception:
        logger.exception("Ingestion failed for file %s", file_id)

    doc = await FileRepository(db).get_by_id(file_id)
    if doc:
        _publish_status(folder_id, {
            "file_id": file_id,
            "status": doc.get("status", FileStatus.FAILED.value),
            "error": doc.get("error"),
            "chunk_count": doc.get("chunk_count", 0),
        })


def _compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _content_type_from_ext(ext: str) -> str:
    mapping = {
        ".md": "markdown", ".markdown": "markdown",
        ".pdf": "pdf",
        ".docx": "word", ".doc": "word",
        ".txt": "text", ".rst": "text", ".log": "text",
        ".json": "json",
        ".py": "code:python", ".js": "code:javascript", ".ts": "code:typescript",
        ".go": "code:go", ".java": "code:java", ".cpp": "code:cpp",
        ".c": "code:c", ".cs": "code:csharp", ".rb": "code:ruby",
        ".rs": "code:rust", ".swift": "code:swift",
        ".png": "image", ".jpg": "image", ".jpeg": "image",
        ".webp": "image", ".gif": "image",
    }
    return mapping.get(ext.lower(), "text")


@router.get("/folders/{folder_id}/files", response_model=list[FileOut])
async def list_files(folder: Folder = Depends(get_folder_for_user)) -> list[FileOut]:
    docs = await FileRepository(get_database()).list_by_folder(folder.id)
    return [FileOut.model_validate(d) for d in docs]


@router.post("/folders/{folder_id}/files", response_model=list[FileOut], status_code=status.HTTP_202_ACCEPTED)
async def upload_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    folder: Folder = Depends(get_folder_for_user),
    current_user: User = Depends(get_current_user),
) -> list[FileOut]:
    settings = get_settings()
    db = get_database()
    file_repo = FileRepository(db)

    existing_count = await file_repo.count_by_folder(folder.id)
    if existing_count + len(files) > settings.MAX_FILES_PER_FOLDER:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"File limit of {settings.MAX_FILES_PER_FOLDER} per folder reached",
        )

    upload_dir = Path(settings.UPLOAD_DIR) / str(folder.id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    results: list[FileOut] = []

    for upload in files:
        data = await upload.read()
        size_bytes = len(data)

        if size_bytes > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File {upload.filename} exceeds {settings.MAX_FILE_SIZE_MB}MB limit",
            )

        file_hash = _compute_hash(data)
        original_name = upload.filename or "unknown"
        ext = Path(original_name).suffix.lower()
        content_type = _content_type_from_ext(ext)

        # Return immediately if already successfully ingested with actual chunks
        existing = await file_repo.get_by_hash(folder.id, file_hash, FileStatus.READY)
        if existing and (existing.get("chunk_count") or 0) > 0:
            results.append(FileOut.model_validate(existing))
            continue

        # Delete any stale doc: same hash (any status, or ready with 0 chunks) or same name different hash
        stale = await file_repo.get_by_hash(folder.id, file_hash)
        if stale:
            await delete_file_data(str(stale["_id"]), folder.pinecone_namespace)
            await file_repo.delete(str(stale["_id"]))
        else:
            old = await file_repo.get_by_name(folder.id, original_name)
            if old and old.get("file_hash") != file_hash:
                await delete_file_data(str(old["_id"]), folder.pinecone_namespace)
                await file_repo.delete(str(old["_id"]))

        storage_path = str(upload_dir / f"{file_hash}{ext}")
        with open(storage_path, "wb") as f:
            f.write(data)

        file_doc = await file_repo.create(
            folder_id=folder.id,
            user_id=current_user.id,
            file_name=original_name,
            file_extension=ext,
            content_type=content_type,
            storage_path=storage_path,
            file_hash=file_hash,
            size_bytes=size_bytes,
        )

        background_tasks.add_task(_ingestion_with_notify, str(file_doc["_id"]), folder.id)
        results.append(FileOut.model_validate(file_doc))

    return results


@router.get("/files/{file_id}", response_model=FileOut)
async def get_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
) -> FileOut:
    doc = await FileRepository(get_database()).get_by_id_and_user(file_id, current_user.id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileOut.model_validate(doc)


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    db = get_database()
    file_repo = FileRepository(db)
    doc = await file_repo.get_by_id_and_user(file_id, current_user.id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    folder_doc = await FolderRepository(db).get_by_id(str(doc["folder_id"]))
    namespace = folder_doc["pinecone_namespace"] if folder_doc else ""
    await delete_file_data(file_id, namespace)
    await file_repo.delete(file_id)


@router.websocket("/folders/{folder_id}/files/status")
async def file_status_ws(
    websocket: WebSocket,
    folder_id: str,
) -> None:
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _status_queues.setdefault(folder_id, []).append(queue)
    try:
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_json(payload)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except (WebSocketDisconnect, Exception):
                    break
    except WebSocketDisconnect:
        pass
    finally:
        queues = _status_queues.get(folder_id, [])
        if queue in queues:
            queues.remove(queue)
