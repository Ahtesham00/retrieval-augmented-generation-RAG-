from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_current_user
from app.database import get_database
from app.models.message import MessageCreate
from app.models.user import User
from app.repositories import ConversationRepository, FolderRepository
from app.services.generation import stream_chat

router = APIRouter(tags=["chat"])


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: MessageCreate,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    db = get_database()
    conv = await ConversationRepository(db).get_by_id_and_user(conversation_id, current_user.id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    folder_doc = await FolderRepository(db).get_by_id(str(conv["folder_id"]))
    if folder_doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    return StreamingResponse(
        stream_chat(
            conversation_id=conversation_id,
            user_query=body.content,
            folder_id=str(conv["folder_id"]),
            namespace=folder_doc["pinecone_namespace"],
            num_queries=body.num_queries,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
