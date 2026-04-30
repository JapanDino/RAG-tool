"""
JWT authentication utilities.

Credentials are read from environment variables:
  AUTH_USERNAME        — login name (default: Letovo_teacher_demo!)
  AUTH_PASSWORD_HASH   — bcrypt hash of the password
  AUTH_SECRET_KEY      — HS256 signing secret (generate with: openssl rand -hex 32)
  AUTH_TOKEN_EXPIRE_H  — token lifetime in hours (default: 24)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

AUTH_USERNAME = os.getenv("AUTH_USERNAME", "Letovo_teacher_demo!")
AUTH_PASSWORD_HASH = os.getenv(
    "AUTH_PASSWORD_HASH",
    "$2b$12$CbrQ2EUWc07/gDZWgm3ygejXf8h3mUBc9wdDztgHcwq8T9l5GobTO",  # K3rnel_Bl00m!
)
SECRET_KEY = os.getenv(
    "AUTH_SECRET_KEY",
    "294d2fd19675fa3666c64fd07c1fe02c1f76d006fbdd3be4cb0ecacb6a62ee25",
)
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = int(os.getenv("AUTH_TOKEN_EXPIRE_H", "24"))


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    """Return username if token is valid, else None."""
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return data.get("sub")
    except JWTError:
        return None
