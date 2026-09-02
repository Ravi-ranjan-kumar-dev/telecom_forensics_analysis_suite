"""Behavioral tests for first-time setup, login and password recovery."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import auth, crud, models, schemas
from backend.app.routers import auth as auth_router
from backend.app.security import verify_password

TEST_SECRET = "test-only-secret-key-with-more-than-32-characters"
OLD_PASSWORD = "Correct Horse Battery Staple"
NEW_PASSWORD = "A Different Long Password 2026"


@pytest.fixture(autouse=True)
def configure_test_secret(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("ALGORITHM", "HS256")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    monkeypatch.setenv(
        "PASSWORD_RESET_TOKEN_EXPIRE_MINUTES",
        "15",
    )


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        yield session
    models.Base.metadata.drop_all(engine)
    engine.dispose()


def _create_first_admin(
    db_session: Session,
    *,
    username: str = "case_admin",
):
    return auth_router.setup_admin(
        schemas.FirstAdminCreate(
            username=username,
            password=OLD_PASSWORD,
        ),
        db_session,
    )


def test_first_admin_setup_is_one_time_and_hashes_password(
    db_session: Session,
) -> None:
    assert auth_router.setup_status(db_session) == {
        "setup_required": True,
    }

    user = _create_first_admin(db_session)

    assert user.username == "case_admin"
    assert user.role == models.UserRole.admin.value
    assert user.password_hash != OLD_PASSWORD
    assert verify_password(
        OLD_PASSWORD,
        user.password_hash,
    )
    assert auth_router.setup_status(db_session) == {
        "setup_required": False,
    }

    with pytest.raises(HTTPException) as captured:
        _create_first_admin(
            db_session,
            username="second_admin",
        )

    assert captured.value.status_code == 409
    assert crud.user_count(db_session) == 1


def test_login_distinguishes_credentials_and_configuration(
    db_session: Session,
    monkeypatch,
) -> None:
    user = _create_first_admin(db_session)

    token_response = auth_router.login(
        SimpleNamespace(
            username="case_admin",
            password=OLD_PASSWORD,
        ),
        db_session,
    )
    payload = auth.decode_token(
        token_response["access_token"]
    )
    assert payload["sub"] == "case_admin"
    assert payload["role"] == "admin"

    with pytest.raises(HTTPException) as wrong_password:
        auth_router.login(
            SimpleNamespace(
                username="case_admin",
                password="wrong password",
            ),
            db_session,
        )
    assert wrong_password.value.status_code == 401

    monkeypatch.delenv("SECRET_KEY")
    with pytest.raises(HTTPException) as missing_secret:
        auth_router.login(
            SimpleNamespace(
                username="case_admin",
                password=OLD_PASSWORD,
            ),
            db_session,
        )
    assert missing_secret.value.status_code == 503

    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    user.is_active = False
    db_session.commit()
    with pytest.raises(HTTPException) as inactive_user:
        auth_router.login(
            SimpleNamespace(
                username="case_admin",
                password=OLD_PASSWORD,
            ),
            db_session,
        )
    assert inactive_user.value.status_code == 401


def test_host_issued_reset_token_is_one_time_by_password_state(
    db_session: Session,
) -> None:
    user = _create_first_admin(db_session)
    reset_token = auth.create_password_reset_token(
        username=user.username,
        password_hash=user.password_hash,
    )

    with pytest.raises(auth.InvalidTokenError):
        auth.decode_token(reset_token)

    result = auth_router.reset_password(
        schemas.PasswordResetConfirm(
            username=user.username,
            token=reset_token,
            new_password=NEW_PASSWORD,
        ),
        db_session,
    )

    assert result == {
        "message": "Password reset successfully.",
    }
    db_session.refresh(user)
    assert verify_password(
        NEW_PASSWORD,
        user.password_hash,
    )
    assert not verify_password(
        OLD_PASSWORD,
        user.password_hash,
    )

    with pytest.raises(HTTPException) as reused_token:
        auth_router.reset_password(
            schemas.PasswordResetConfirm(
                username=user.username,
                token=reset_token,
                new_password="Another Secure Password 2026",
            ),
            db_session,
        )
    assert reused_token.value.status_code == 400


def test_access_token_cannot_reset_password(
    db_session: Session,
) -> None:
    user = _create_first_admin(db_session)
    access_token = auth.create_access_token(
        {
            "sub": user.username,
            "role": user.role,
        }
    )

    with pytest.raises(HTTPException) as captured:
        auth_router.reset_password(
            schemas.PasswordResetConfirm(
                username=user.username,
                token=access_token,
                new_password=NEW_PASSWORD,
            ),
            db_session,
        )

    assert captured.value.status_code == 400
    db_session.refresh(user)
    assert verify_password(
        OLD_PASSWORD,
        user.password_hash,
    )


def test_forgot_password_never_returns_account_or_token_details() -> None:
    result = auth_router.forgot_password(
        schemas.PasswordResetRequest(
            username="unknown_user",
        )
    )

    assert set(result) == {"message"}
    assert "unknown_user" not in result["message"]


@pytest.mark.parametrize(
    "password",
    [
        "short",
        "क" * 40,
    ],
    ids=[
        "too-short",
        "more-than-72-utf8-bytes",
    ],
)
def test_password_policy_rejects_unsafe_bcrypt_inputs(
    password: str,
) -> None:
    with pytest.raises(ValidationError):
        schemas.FirstAdminCreate(
            username="case_admin",
            password=password,
        )
