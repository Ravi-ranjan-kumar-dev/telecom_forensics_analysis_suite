"""Password hashing and validation helpers."""

from __future__ import annotations

import bcrypt

MINIMUM_PASSWORD_LENGTH = 12
MAXIMUM_PASSWORD_LENGTH = 72


def validate_password(password: str) -> str:
    """Return the password after enforcing the application policy."""

    if not isinstance(password, str):
        raise ValueError("Password must be text.")
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must contain at least {MINIMUM_PASSWORD_LENGTH} characters."
        )
    if len(password.encode("utf-8")) > MAXIMUM_PASSWORD_LENGTH:
        raise ValueError(
            "Password is too long for secure bcrypt hashing. "
            f"Use at most {MAXIMUM_PASSWORD_LENGTH} UTF-8 bytes."
        )
    return password


def hash_password(password: str) -> str:
    """Hash a policy-compliant password with bcrypt."""

    password_bytes = validate_password(password).encode(
        "utf-8"
    )
    return bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt(),
    ).decode("ascii")


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """Safely compare a password with a stored bcrypt hash."""

    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("ascii"),
        )
    except (AttributeError, TypeError, UnicodeError, ValueError):
        return False
