"""Credentials: owner passwords (Argon2id), owner session tokens, device tokens.

Device token format: "pcd_<device uuid>.<secret>". The secret is 32 random bytes
(256 bits), so a fast SHA-256 hash is enough to store it: it cannot be guessed or
brute-forced. Only the hash is stored. Owner session tokens are hashed the same way.
"""

import hashlib
import hmac
import secrets
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

DEVICE_PREFIX = "pcd_"
OWNER_PREFIX = "pco_"
_hasher = PasswordHasher()


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored: str) -> bool:
    try:
        return _hasher.verify(stored, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_device_token(device_id: uuid.UUID) -> tuple[str, str]:
    """Returns (token shown once to the owner, hash to store)."""
    secret = secrets.token_urlsafe(32)
    return f"{DEVICE_PREFIX}{device_id}.{secret}", sha256_hex(secret)


def parse_device_token(token: str) -> tuple[uuid.UUID, str] | None:
    if not token.startswith(DEVICE_PREFIX) or "." not in token:
        return None
    device_part, secret = token[len(DEVICE_PREFIX):].split(".", 1)
    try:
        return uuid.UUID(device_part), secret
    except ValueError:
        return None


def secret_matches(secret: str, stored_hash: str) -> bool:
    return hmac.compare_digest(sha256_hex(secret), stored_hash)


def new_owner_token() -> tuple[str, str]:
    token = OWNER_PREFIX + secrets.token_urlsafe(32)
    return token, sha256_hex(token)


def bearer(header: str | None) -> str:
    if header and header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip()
    return ""
