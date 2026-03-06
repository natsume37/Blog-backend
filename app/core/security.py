from datetime import datetime, timedelta
from typing import Optional
import hmac
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode a JWT access token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def hash_protection_answer(answer: str) -> str:
    """Hash article protection answer."""
    return pwd_context.hash(answer)


def verify_protection_answer(answer: str, stored_answer: Optional[str]) -> bool:
    """Verify protection answer; supports legacy plaintext values."""
    if not stored_answer:
        return False

    # bcrypt hash prefix; keep legacy plaintext fallback for existing records.
    if stored_answer.startswith("$2"):
        return pwd_context.verify(answer, stored_answer)

    return hmac.compare_digest(answer, stored_answer)
