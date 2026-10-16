"""JWT creation and validation for access and password-reset tokens."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from .security import hash_password

load_dotenv()

DEFAULT_ACCESS_TOKEN_MINUTES = 1440
DEFAULT_RESET_TOKEN_MINUTES = 15
MINIMUM_SECRET_KEY_LENGTH = 32

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login"
)


class InvalidTokenError(ValueError):
    """Raised when a JWT is invalid or has the wrong purpose."""


def _algorithm() -> str:
    return os.getenv("ALGORITHM", "HS256").strip() or "HS256"


def _secret_key() -> str:
    key = os.getenv("SECRET_KEY", "")
    if len(key) < MINIMUM_SECRET_KEY_LENGTH:
        raise RuntimeError(
            "SECRET_KEY is missing or too short. Configure a random "
            f"secret containing at least {MINIMUM_SECRET_KEY_LENGTH} characters."
        )
    return key


def _positive_minutes(
    environment_name: str,
    default: int,
) -> int:
    raw_value = os.getenv(
        environment_name,
        str(default),
    )
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            f"{environment_name} must be a positive integer."
        ) from error
    if value <= 0:
        raise RuntimeError(
            f"{environment_name} must be a positive integer."
        )
    return value


def _encode_token(
    claims: dict[str, Any],
    *,
    token_type: str,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(timezone.utc)
    payload = dict(claims)
    payload.update(
        {
            "token_type": token_type,
            "iat": now,
            "exp": now + expires_delta,
        }
    )
    return jwt.encode(
        payload,
        _secret_key(),
        algorithm=_algorithm(),
    )


def _decode_token(
    token: str,
    *,
    expected_type: str,
) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            _secret_key(),
            algorithms=[_algorithm()],
        )
    except (JWTError, RuntimeError) as error:
        raise InvalidTokenError("Invalid or expired token.") from error

    if payload.get("token_type") != expected_type:
        raise InvalidTokenError("Token cannot be used for this operation.")
    if not str(payload.get("sub", "")).strip():
        raise InvalidTokenError("Token subject is missing.")
    return payload


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed access token."""

    lifetime = expires_delta or timedelta(
        minutes=_positive_minutes(
            "ACCESS_TOKEN_EXPIRE_MINUTES",
            DEFAULT_ACCESS_TOKEN_MINUTES,
        )
    )
    return _encode_token(
        data,
        token_type="access",
        expires_delta=lifetime,
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode an access token and reject tokens with another purpose."""

    return _decode_token(
        token,
        expected_type="access",
    )


def _password_fingerprint(password_hash: str) -> str:
    return hashlib.sha256(
        password_hash.encode("utf-8")
    ).hexdigest()


def create_password_reset_token(
    *,
    username: str,
    password_hash: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a short-lived token tied to the current password hash."""

    lifetime = expires_delta or timedelta(
        minutes=password_reset_token_minutes()
    )
    return _encode_token(
        {
            "sub": username,
            "password_fingerprint": _password_fingerprint(
                password_hash
            ),
        },
        token_type="password_reset",
        expires_delta=lifetime,
    )


def password_reset_token_minutes() -> int:
    """Return the configured password-reset token lifetime."""

    return _positive_minutes(
        "PASSWORD_RESET_TOKEN_EXPIRE_MINUTES",
        DEFAULT_RESET_TOKEN_MINUTES,
    )


def validate_password_reset_token(
    token: str,
    *,
    username: str,
    password_hash: str,
) -> None:
    """Validate a reset token against the account's current password."""

    payload = _decode_token(
        token,
        expected_type="password_reset",
    )
    token_username = str(payload.get("sub", ""))
    token_fingerprint = str(
        payload.get("password_fingerprint", "")
    )
    if not hmac.compare_digest(
        token_username,
        username,
    ):
        raise InvalidTokenError("Invalid or expired reset token.")
    if not hmac.compare_digest(
        token_fingerprint,
        _password_fingerprint(password_hash),
    ):
        raise InvalidTokenError("Invalid or expired reset token.")


# Backward-compatible names used by existing callers.
get_password_hash = hash_password
