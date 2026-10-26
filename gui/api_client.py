"""API client for VPS / backend communication with batch enrichment support."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


class ApiError(Exception):
    """Custom exception for API errors."""

    def __init__(self, message, status_code=None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ServiceUnavailableError(ApiError):
    """Raised when the API server is unreachable."""


class RecordNotFoundError(ApiError):
    """Raised when a record is not found."""


class AuthenticationError(ApiError):
    """Raised when login fails due to invalid credentials."""


class BackendConfigurationError(ApiError):
    """Raised when backend authentication is not configured."""


class SetupAlreadyCompletedError(ApiError):
    """Raised when first-time administrator setup is already complete."""


class PasswordResetError(ApiError):
    """Raised when password-reset credentials are invalid or expired."""


_ACTIVE_API_CLIENT: Optional["ApiClient"] = None


def set_active_api_client(client: Optional["ApiClient"]) -> None:
    """Register the authenticated API client for background report enrichment."""
    global _ACTIVE_API_CLIENT
    _ACTIVE_API_CLIENT = client


def get_active_api_client() -> Optional["ApiClient"]:
    """Return the active authenticated API client if logged in."""
    return _ACTIVE_API_CLIENT


def resolve_default_api_url() -> str:
    """Resolve VPS API URL from environment or config.json, defaulting to localhost."""
    env_url = os.getenv("TELECOM_API_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")

    config_candidates = [
        Path.cwd() / "config.json",
        Path(__file__).resolve().parents[1] / "config.json",
    ]
    for cfg_path in config_candidates:
        if cfg_path.is_file():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
                url = str(data.get("api_base_url", "")).strip()
                if url:
                    return url.rstrip("/")
            except Exception:
                pass

    return "http://localhost:8000"


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
    def __init__(self, base_url: str | None = None):
        resolved = base_url if base_url is not None else resolve_default_api_url()
        self.base_url = str(resolved).rstrip("/")
        self.token: Optional[str] = None

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def login(self, username: str, password: str) -> bool:
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
                set_active_api_client(self)
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

    def lookup_sdr_batch(self, numbers: List[str]) -> List[Dict[str, Any]]:
        """Fetch up to thousands of SDR profiles from VPS in 1000-number batches."""
        if not self.token or not numbers:
            return []
        results: List[Dict[str, Any]] = []
        for start in range(0, len(numbers), 1000):
            batch = numbers[start : start + 1000]
            try:
                response = requests.post(
                    f"{self.base_url}/api/lookup/sdr/batch",
                    json={"numbers": batch},
                    headers=self._headers(),
                    timeout=25,
                )
                if response.status_code == 200:
                    payload = response.json()
                    records = payload.get("records", []) if isinstance(payload, dict) else []
                    if isinstance(records, list):
                        results.extend(r for r in records if isinstance(r, dict))
            except requests.RequestException:
                break
        return results

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

    def lookup_cgi_batch(self, cgis: List[str]) -> List[Dict[str, Any]]:
        """Fetch up to thousands of CGI records from VPS in 1000-key batches."""
        if not self.token or not cgis:
            return []
        results: List[Dict[str, Any]] = []
        for start in range(0, len(cgis), 1000):
            batch = cgis[start : start + 1000]
            try:
                response = requests.post(
                    f"{self.base_url}/api/lookup/cgi/batch",
                    json={"cgis": batch},
                    headers=self._headers(),
                    timeout=25,
                )
                if response.status_code == 200:
                    payload = response.json()
                    records = payload.get("records", []) if isinstance(payload, dict) else []
                    if isinstance(records, list):
                        results.extend(r for r in records if isinstance(r, dict))
            except requests.RequestException:
                break
        return results

    def import_master_file(self, file_path: str) -> Dict[str, Any]:
        if not self.token:
            raise AuthenticationError("Not authenticated. Please login first.")

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
                raise ApiError(_response_message(response, f"Import failed ({response.status_code})."), response.status_code)
        except requests.RequestException as e:
            raise ServiceUnavailableError(f"Service unavailable: {e}")
        except FileNotFoundError:
            raise ApiError(f"File not found: {file_path}")

    def list_users(self) -> List[Dict[str, Any]]:
        try:
            response = requests.get(
                f"{self.base_url}/api/admin/users",
                headers=self._headers(),
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                return data if isinstance(data, list) else []
            raise ApiError(
                _response_message(response, f"Failed to list users ({response.status_code})"),
                response.status_code,
            )
        except requests.RequestException as error:
            raise ServiceUnavailableError("Backend service is unavailable.") from error

    def create_officer_user(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = requests.post(
                f"{self.base_url}/api/admin/users",
                json=payload,
                headers=self._headers(),
                timeout=10,
            )
            if response.status_code in {200, 201}:
                return response.json()
            raise ApiError(
                _response_message(response, f"Failed to create user ({response.status_code})"),
                response.status_code,
            )
        except requests.RequestException as error:
            raise ServiceUnavailableError("Backend service is unavailable.") from error

    def update_user_status(
        self,
        username: str,
        *,
        is_active: bool,
        expires_at: str | None = None,
    ) -> Dict[str, Any]:
        try:
            response = requests.put(
                f"{self.base_url}/api/admin/users/{username}/status",
                json={"is_active": is_active, "expires_at": expires_at},
                headers=self._headers(),
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()
            raise ApiError(
                _response_message(response, f"Failed to update status ({response.status_code})"),
                response.status_code,
            )
        except requests.RequestException as error:
            raise ServiceUnavailableError("Backend service is unavailable.") from error

    def update_user_role(self, username: str, role: str) -> Dict[str, Any]:
        try:
            response = requests.put(
                f"{self.base_url}/api/admin/user-role",
                json={"username": username, "role": role},
                headers=self._headers(),
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()
            raise ApiError(
                _response_message(response, f"Failed to update role ({response.status_code})"),
                response.status_code,
            )
        except requests.RequestException as error:
            raise ServiceUnavailableError("Backend service is unavailable.") from error

    def admin_reset_password(self, username: str, new_password: str) -> Dict[str, Any]:
        try:
            response = requests.post(
                f"{self.base_url}/api/admin/users/{username}/reset-password",
                json={"new_password": new_password},
                headers=self._headers(),
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()
            raise ApiError(
                _response_message(response, f"Failed to reset password ({response.status_code})"),
                response.status_code,
            )
        except requests.RequestException as error:
            raise ServiceUnavailableError("Backend service is unavailable.") from error


