from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..auth.core import AUTH_USERNAME, AUTH_PASSWORD_HASH, create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/token", response_model=TokenOut)
def login(payload: LoginIn):
    if payload.username != AUTH_USERNAME or not verify_password(payload.password, AUTH_PASSWORD_HASH):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(payload.username)
    return TokenOut(access_token=token)
