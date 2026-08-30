"""Password hashing and session-token generation. Stdlib only --
hashlib.pbkdf2_hmac needs no third-party dependency (no passlib/bcrypt),
and secrets.token_urlsafe is a cryptographically secure RNG suitable for
a bearer session token."""

import hashlib
import hmac
import secrets

_PBKDF2_ITERATIONS = 260_000
_ALGORITHM = "sha256"


def hash_password(password: str) -> tuple[str, str]:
    """Returns (salt_hex, hash_hex). A fresh random salt every call --
    two users with the same password never produce the same hash."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        _ALGORITHM, password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    )
    return salt, digest.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    digest = hashlib.pbkdf2_hmac(
        _ALGORITHM, password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(digest.hex(), expected_hash)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)
