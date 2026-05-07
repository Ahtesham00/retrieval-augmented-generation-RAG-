from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.cache import invalidate_folder_meta
from app.config import get_settings
from app.core.dependencies import get_current_user, get_folder_for_user
from app.database import get_database
from app.models.folder import Folder, FolderCreate, FolderOut, FolderSettings, FolderUpdate
from app.models.user import User
from app.pinecone_client import get_index, make_namespace
from app.repositories import ConversationRepository, FileRepository, FolderRepository, MessageRepository

router = APIRouter(prefix="/folders", tags=["folders"])


@router.get("", response_model=list[FolderOut])
async def list_folders(current_user: User = Depends(get_current_user)) -> list[FolderOut]:
    repo = FolderRepository(get_database())
    docs = await repo.list_by_user(current_user.id)
    return [FolderOut.model_validate(d) for d in docs]


@router.post("", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
async def create_folder(
    body: FolderCreate,
    current_user: User = Depends(get_current_user),
) -> FolderOut:
    settings = get_settings()
    repo = FolderRepository(get_database())

    count = await repo.count_by_user(current_user.id)
    if count >= settings.MAX_FOLDERS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Folder limit of {settings.MAX_FOLDERS_PER_USER} reached",
        )

    folder_oid = ObjectId()
    namespace = make_namespace(current_user.id, str(folder_oid))
    doc = await repo.create(
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        pinecone_namespace=namespace,
        settings=body.settings or FolderSettings(),
        folder_id=folder_oid,
    )
    return FolderOut.model_validate(doc)


@router.get("/{folder_id}", response_model=FolderOut)
async def get_folder(folder: Folder = Depends(get_folder_for_user)) -> FolderOut:
    return FolderOut.model_validate(folder.model_dump(by_alias=True))


@router.patch("/{folder_id}", response_model=FolderOut)
async def update_folder(
    body: FolderUpdate,
    folder: Folder = Depends(get_folder_for_user),
) -> FolderOut:
    repo = FolderRepository(get_database())
    fields: dict = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.description is not None:
        fields["description"] = body.description
    if body.settings is not None:
        fields["settings"] = body.settings.model_dump()

    updated = await repo.update(folder.id, fields)
    await invalidate_folder_meta(folder.id)
    return FolderOut.model_validate(updated)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(folder: Folder = Depends(get_folder_for_user)) -> None:
    db = get_database()
    file_repo = FileRepository(db)
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)
    folder_repo = FolderRepository(db)

    # Delete Pinecone namespace
    try:
        index = get_index()
        index.delete(delete_all=True, namespace=folder.pinecone_namespace)
    except Exception:
        pass

    # Drop MongoDocumentStore collections for this folder
    # LlamaIndex creates two collections per namespace: .../data and .../metadata
    ns = f"llamaindex_{folder.id}"
    await db[f"{ns}/data"].drop()
    await db[f"{ns}/metadata"].drop()

    await file_repo.delete_by_folder(folder.id)

    conv_ids = await conv_repo.list_ids_by_folder(folder.id)
    await msg_repo.delete_by_conversation_ids(conv_ids)
    await conv_repo.delete_by_folder(folder.id)

    await folder_repo.delete(folder.id)
    await invalidate_folder_meta(folder.id)
