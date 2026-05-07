from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import decode_token
from app.database import get_database
from app.models.folder import Folder
from app.models.user import User
from app.repositories import FolderRepository, UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    user_id = decode_token(token, expected_type="access")
    repo = UserRepository(get_database())
    doc = await repo.get_by_id(user_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return User.model_validate(doc)


async def get_folder_for_user(
    folder_id: str,
    current_user: User = Depends(get_current_user),
) -> Folder:
    repo = FolderRepository(get_database())
    doc = await repo.get_by_id_and_user(folder_id, current_user.id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    return Folder.model_validate(doc)
