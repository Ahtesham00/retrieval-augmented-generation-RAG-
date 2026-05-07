from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import get_current_user, get_folder_for_user
from app.database import get_database
from app.models.conversation import ConversationCreate, ConversationOut
from app.models.folder import Folder
from app.models.message import MessageOut
from app.models.user import User
from app.repositories import ConversationRepository, MessageRepository

router = APIRouter(tags=["conversations"])


@router.get("/folders/{folder_id}/conversations", response_model=list[ConversationOut])
async def list_conversations(
    folder: Folder = Depends(get_folder_for_user),
) -> list[ConversationOut]:
    docs = await ConversationRepository(get_database()).list_by_folder(folder.id)
    return [ConversationOut.model_validate(d) for d in docs]


@router.post("/folders/{folder_id}/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate,
    folder: Folder = Depends(get_folder_for_user),
    current_user: User = Depends(get_current_user),
) -> ConversationOut:
    doc = await ConversationRepository(get_database()).create(
        folder_id=folder.id,
        user_id=current_user.id,
        title=body.title or "New conversation",
    )
    return ConversationOut.model_validate(doc)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
) -> ConversationOut:
    doc = await ConversationRepository(get_database()).get_by_id_and_user(conversation_id, current_user.id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return ConversationOut.model_validate(doc)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def get_messages(
    conversation_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
) -> list[MessageOut]:
    db = get_database()
    conv = await ConversationRepository(db).get_by_id_and_user(conversation_id, current_user.id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    docs = await MessageRepository(db).list_by_conversation(conversation_id, page=page, page_size=page_size)
    return [MessageOut.model_validate(d) for d in docs]


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    db = get_database()
    conv_repo = ConversationRepository(db)
    doc = await conv_repo.get_by_id_and_user(conversation_id, current_user.id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    await MessageRepository(db).delete_by_conversation(conversation_id)
    await conv_repo.delete(conversation_id)
