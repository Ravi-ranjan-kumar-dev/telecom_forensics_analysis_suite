"""API-client contract tests for authentication error categories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
import requests

from gui import api_client


@dataclass
class FakeResponse:
    status_code: int
    payload: Any

    def json(self):
        if isinstance(self.payload, BaseException):
            raise self.payload
        return self.payload


def test_login_keeps_wrong_password_separate_from_backend_down(
    monkeypatch,
) -> None:
    client = api_client.ApiClient()

    monkeypatch.setattr(
        api_client.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            401,
            {"detail": "Incorrect username or password"},
        ),
    )
    with pytest.raises(api_client.AuthenticationError):
        client.login("case_admin", "wrong")

    def backend_down(*args, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(
        api_client.requests,
        "post",
        backend_down,
    )
    with pytest.raises(api_client.ServiceUnavailableError):
        client.login("case_admin", "anything")


def test_login_reports_backend_configuration_and_validates_token(
    monkeypatch,
) -> None:
    client = api_client.ApiClient()

    monkeypatch.setattr(
        api_client.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            503,
            {"detail": "Backend authentication is not configured."},
        ),
    )
    with pytest.raises(api_client.BackendConfigurationError):
        client.login("case_admin", "valid password")

    monkeypatch.setattr(
        api_client.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            200,
            {"token_type": "bearer"},
        ),
    )
    with pytest.raises(api_client.ApiError):
        client.login("case_admin", "valid password")


def test_first_admin_setup_status_and_one_time_conflict(
    monkeypatch,
) -> None:
    client = api_client.ApiClient()

    monkeypatch.setattr(
        api_client.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            200,
            {"setup_required": True},
        ),
    )
    assert client.setup_status() is True

    monkeypatch.setattr(
        api_client.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            201,
            {
                "id": 1,
                "username": "case_admin",
                "role": "admin",
                "is_active": True,
            },
        ),
    )
    result = client.setup_first_admin(
        "case_admin",
        "Correct Horse Battery Staple",
    )
    assert result["role"] == "admin"

    monkeypatch.setattr(
        api_client.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            409,
            {"detail": "First-time setup has already been completed."},
        ),
    )
    with pytest.raises(
        api_client.SetupAlreadyCompletedError
    ):
        client.setup_first_admin(
            "second_admin",
            "Another Secure Password 2026",
        )


def test_password_reset_maps_invalid_token_without_leaking_detail(
    monkeypatch,
) -> None:
    client = api_client.ApiClient()

    monkeypatch.setattr(
        api_client.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            400,
            {"detail": "internal sensitive detail"},
        ),
    )
    with pytest.raises(
        api_client.PasswordResetError,
        match="invalid or expired",
    ):
        client.reset_password(
            username="case_admin",
            token="invalid-token-value-that-is-long-enough",
            new_password="A Different Long Password 2026",
        )

    monkeypatch.setattr(
        api_client.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(
            200,
            {"message": "Password reset successfully."},
        ),
    )
    assert client.reset_password(
        username="case_admin",
        token="valid-token-value-that-is-long-enough",
        new_password="A Different Long Password 2026",
    ) is True
