"""Authentication and security utilities."""

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from src.core.config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str
    tenant_id: Optional[str] = None
    roles: list[str] = []
    exp: datetime
    iat: datetime
    # Optional fields for client tokens
    user_type: Optional[str] = None  # "staff" or "client"
    client_id: Optional[str] = None  # Only for client tokens


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def generate_temp_password(length: int = 12) -> str:
    """Generate a secure temporary password.
    
    Format: Mix of letters, digits, and special characters.
    Avoids confusing characters (0, O, l, 1, I).
    """
    # Characters that are easy to read and type
    letters = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ'
    digits = '23456789'
    special = '!@#$%&*'
    
    # Ensure at least one of each type
    password = [
        secrets.choice(letters),
        secrets.choice(letters.upper()),
        secrets.choice(digits),
        secrets.choice(special),
    ]
    
    # Fill the rest
    all_chars = letters + digits + special
    password.extend(secrets.choice(all_chars) for _ in range(length - 4))
    
    # Shuffle
    secrets.SystemRandom().shuffle(password)
    
    return ''.join(password)


def create_access_token(
    subject: str,
    tenant_id: Optional[str],
    roles: list[str],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: dict[str, Any] = {
        "sub": subject,
        "tenant_id": tenant_id,
        "roles": roles,
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(subject: str, tenant_id: Optional[str]) -> str:
    """Create a JWT refresh token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode: dict[str, Any] = {
        "sub": subject,
        "tenant_id": tenant_id,
        "type": "refresh",
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def create_client_access_token(
    client_user_id: str,
    client_id: str,
    tenant_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token for client users."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: dict[str, Any] = {
        "sub": client_user_id,
        "tenant_id": tenant_id,
        "client_id": client_id,
        "user_type": "client",
        "roles": ["client"],
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def create_client_refresh_token(client_user_id: str, client_id: str, tenant_id: str) -> str:
    """Create a JWT refresh token for client users."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode: dict[str, Any] = {
        "sub": client_user_id,
        "tenant_id": tenant_id,
        "client_id": client_id,
        "user_type": "client",
        "type": "refresh",
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[TokenPayload]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return TokenPayload(**payload)
    except JWTError:
        return None

