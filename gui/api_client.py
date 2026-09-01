# gui/api_client.py
"""API client for backend communication with robust error handling."""

import requests
from typing import Optional, Dict, Any

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

class ApiClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self.token: Optional[str] = None

    def _headers(self) -> Dict[str, str]:
        """Return headers with Bearer token if available."""
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def login(self, username: str, password: str) -> bool:
        """Authenticate user and store JWT token on success."""
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                data={"username": username, "password": password},
                timeout=10,
            )
            if response.status_code == 200:
                self.token = response.json().get("access_token")
                return True
            return False
        except requests.RequestException:
            return False

    def lookup_sdr(self, mobile: str) -> Optional[Dict[str, Any]]:
        """Fetch SDR profile for a mobile number."""
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
        """Fetch CGI tower details for a CGI value."""
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
                    timeout=120,  # Longer timeout for large files
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