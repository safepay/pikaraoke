"""One password-hashing path, shared by the admin and singer locks.

Extracted from AdminAuth so both derive and verify the same way -- one crypto
path to audit, and no second hashing dependency.
"""

import hashlib
import hmac
import secrets

# Login only, never per request: ~90ms on a desktop, roughly 0.3s on a Pi 4.
_PBKDF2_ITERATIONS = 100_000


def hash_password(password: str) -> str:
    """Return a fresh `salt:hash` for a password, salt and digest hex-encoded."""
    salt = secrets.token_bytes(16)
    return f"{salt.hex()}:{_derive(password, salt).hex()}"


def verify_password(password: str, stored: str) -> bool:
    """True when password matches a `salt:hash`; False on an empty or malformed one."""
    salt, _, expected = (stored or "").partition(":")
    if not salt or not expected:
        return False
    return hmac.compare_digest(_derive(password, bytes.fromhex(salt)), bytes.fromhex(expected))


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
