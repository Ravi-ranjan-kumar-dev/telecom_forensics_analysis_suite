# gui/api_client.py
"""API client for backend communication with robust error handling."""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests


class ApiError(Exception):
    """Custom exception for API errors."""

    def __init__(self, message, status_code=None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ServiceUnavailableError(ApiError):
    """Raised when the API server is unreachable."""

    pass


class RecordNotFoundError(ApiError):
    """Raised when a record is not found."""

    pass


class AuthenticationError(ApiError):
    """Raised when login fails due to invalid credentials."""

    pass


class BackendConfigurationError(ApiError):
    """Raised when backend authentication is not configured."""


class SetupAlreadyCompletedError(ApiError):
    """Raised when first-time administrator setup is already complete."""


class PasswordResetError(ApiError):
    """Raised when password-reset credentials are invalid or expired."""


def _response_message(
    response: requests.Response,
    fallback: str,
) -> str:
    """Extract a readable FastAPI error without exposing raw responses."""

    try:
        payload = response.json()
    except ValueError:
        return fallback
    if not isinstance(payload, dict):
        return fallback

    detail = payload.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    if isinstance(detail, list):
        messages = [
            str(item.get("msg", "")).strip()
            for item in detail
            if isinstance(item, dict)
            and str(item.get("msg", "")).strip()
        ]
        if messages:
            return " ".join(messages)
    return fallback


class ApiClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self.token: Optional[str] = None

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def login(self, username: str, password: str) -> bool:
        """
        Authenticate user and store JWT token.
        Raises:
            ServiceUnavailableError – when backend is unreachable
            AuthenticationError    – when credentials are invalid
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                data={"username": username, "password": password},
                timeout=10,
            )
            if response.status_code == 200:
                try:
                    token = response.json().get("access_token")
                except (AttributeError, ValueError) as error:
                    raise ApiError(
                        "Backend returned an invalid login response.",
                        response.status_code,
                    ) from error
                if not isinstance(token, str) or not token.strip():
                    raise ApiError(
                        "Backend returned an invalid login response.",
                        response.status_code,
                    )
                self.token = token
                return True
            elif response.status_code == 401:
                raise AuthenticationError("Invalid username or password")
            elif response.status_code == 503:
                raise BackendConfigurationError(
                    _response_message(
                        response,
                        "Backend authentication is not configured.",
                    ),
                    response.status_code,
                )
            else:
                raise ApiError(
                    _response_message(
                        response,
                        f"Login failed with status {response.status_code}.",
                    ),
                    response.status_code,
                )
        except requests.RequestException as error:
            raise ServiceUnavailableError(
                "Backend service is unavailable."
            ) from error

    def setup_status(self) -> bool:
        """Return True when the first administrator must be created."""

        try:
            response = requests.get(
                f"{self.base_url}/api/auth/setup-status",
                timeout=5,
            )
        except requests.RequestException as error:
            raise ServiceUnavailableError(
                "Backend service is unavailable."
            ) from error

        if response.status_code != 200:
            raise ApiError(
                _response_message(
                    response,
                    "Could not read first-time setup status.",
                ),
                response.status_code,
            )
        try:
            value = response.json().get("setup_required")
        except (AttributeError, ValueError) as error:
            raise ApiError(
                "Backend returned an invalid setup response.",
                response.status_code,
            ) from error
        if not isinstance(value, bool):
            raise ApiError(
                "Backend returned an invalid setup response.",
                response.status_code,
            )
        return value

    def setup_first_admin(
        self,
        username: str,
        password: str,
    ) -> Dict[str, Any]:
        """Create the first administrator when setup is still open."""

        try:
            response = requests.post(
                f"{self.base_url}/api/auth/setup-admin",
                json={
                    "username": username,
                    "password": password,
                },
                timeout=10,
            )
        except requests.RequestException as error:
            raise ServiceUnavailableError(
                "Backend service is unavailable."
            ) from error

        if response.status_code == 201:
            try:
                payload = response.json()
            except ValueError as error:
                raise ApiError(
                    "Backend returned an invalid setup response.",
                    response.status_code,
                ) from error
            if not isinstance(payload, dict):
                raise ApiError(
                    "Backend returned an invalid setup response.",
                    response.status_code,
                )
            return payload
        if response.status_code == 409:
            raise SetupAlreadyCompletedError(
                _response_message(
                    response,
                    "First-time setup has already been completed.",
                ),
                response.status_code,
            )
        raise ApiError(
            _response_message(
                response,
                f"First-time setup failed with status {response.status_code}.",
            ),
            response.status_code,
        )

    def reset_password(
        self,
        *,
        username: str,
        token: str,
        new_password: str,
    ) -> bool:
        """Reset an account password with a host-issued token."""

        try:
            response = requests.post(
                f"{self.base_url}/api/auth/reset-password",
                json={
                    "username": username,
                    "token": token,
                    "new_password": new_password,
                },
                timeout=10,
            )
        except requests.RequestException as error:
            raise ServiceUnavailableError(
                "Backend service is unavailable."
            ) from error

        if response.status_code == 200:
            return True
        if response.status_code in {400, 401}:
            raise PasswordResetError(
                "The reset token is invalid or expired.",
                response.status_code,
            )
        raise ApiError(
            _response_message(
                response,
                f"Password reset failed with status {response.status_code}.",
            ),
            response.status_code,
        )

    def lookup_sdr(self, mobile: str) -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(
                f"{self.base_url}/api/lookup/sdr/{mobile}",
                headers=self._headers(),
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                raise RecordNotFoundError("Record not found")
            else:
                raise ApiError(f"API error: {response.status_code}", response.status_code)
        except requests.RequestException as e:
            raise ServiceUnavailableError(f"Service unavailable: {e}")

    def lookup_cgi(self, cgi: str) -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(
                f"{self.base_url}/api/lookup/cgi/{cgi}",
                headers=self._headers(),
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                raise RecordNotFoundError("Record not found")
            else:
                raise ApiError(f"API error: {response.status_code}", response.status_code)
        except requests.RequestException as e:
            raise ServiceUnavailableError(f"Service unavailable: {e}")

    def import_master_file(self, file_path: str) -> Dict[str, Any]:
        """
        Upload a master data file (SDR/CGI) to the backend for import.
        Returns the JSON response from the API.
        """
        if not self.token:
            raise ServiceUnavailableError("Not authenticated. Please login first.")

        try:
            with open(file_path, "rb") as f:
                response = requests.post(
                    f"{self.base_url}/api/import/master",
                    files={"file": f},
                    headers=self._headers(),
                    timeout=120,
                )
            if response.status_code == 200:
                return response.json()
            else:
                raise ApiError(
                    f"Import failed: {response.status_code} - {response.text}",
                    response.status_code,
                )
        except requests.RequestException as e:
            raise ServiceUnavailableError(f"Service unavailable: {e}")
        except FileNotFoundError:
            raise ApiError(f"File not found: {file_path}")
