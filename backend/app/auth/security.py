from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(subject: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": subject, "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes)},
        settings.secret_key,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> str:
    return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])["sub"]
