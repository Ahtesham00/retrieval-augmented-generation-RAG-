from fastapi import APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.database import get_database
from app.models.user import UserCreate, UserOut, TokenResponse, RefreshRequest
from app.repositories import UserRepository

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate) -> UserOut:
    repo = UserRepository(get_database())
    if await repo.email_exists(body.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    doc = await repo.create(body.email, hash_password(body.password))
    return UserOut.model_validate(doc)


@router.post("/token", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    repo = UserRepository(get_database())
    user_doc = await repo.get_by_email(form.username)
    if not user_doc or not verify_password(form.password, user_doc["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = str(user_doc["_id"])
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest) -> TokenResponse:
    user_id = decode_token(body.refresh_token, expected_type="refresh")
    repo = UserRepository(get_database())
    if not await repo.get_by_id(user_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )
