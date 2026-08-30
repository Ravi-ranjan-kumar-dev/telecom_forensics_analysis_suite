# gui/api_client.py
"""API client for communicating with the FastAPI backend."""

from urllib import response

import requests
from typing import Optional, Any, Dict


class ApiClient:
    """Handles all backend HTTP requests and token management."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self.token: Optional[str] = None

    def set_base_url(self, url: str) -> None:
        """Update the backend base URL (e.g., when deployed to cloud)."""
        self.base_url = url.rstrip("/")

    def login(self, username: str, password: str) -> bool:
        """Authenticate user and store JWT token on success."""
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                data={"username": username, "password": password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
            if response.status_code == 200:
                self.token = response.json().get("access_token")
                return True
            return False
        except requests.RequestException:
            return False

    def _headers(self) -> Dict[str, str]:
        """Return headers with Bearer token."""
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def lookup_sdr(self, mobile: str) -> Optional[Dict[str, Any]]:
        """Fetch SDR profile for a given mobile number."""
        try:
            response = requests.get(
                f"{self.base_url}/api/lookup/sdr/{mobile}",
                headers=self._headers(),
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                return None
            raise Exception(f"API error: {response.status_code} - {response.text}")
        except requests.RequestException:
            return None

    def lookup_cgi(self, cgi: str) -> Optional[Dict[str, Any]]:
        """Fetch CGI tower details for a given CGI value."""
        try:
            response = requests.get(
                f"{self.base_url}/api/lookup/cgi/{cgi}",
                headers=self._headers(),
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                return None
            raise Exception(f"API error: {response.status_code} - {response.text}")
        except requests.RequestException:
            return None

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Fetch currently logged-in user details."""
        try:
            response = requests.get(
                f"{self.base_url}/api/auth/me",
                headers=self._headers(),
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()
            return None
        except requests.RequestException:
            return None

    def import_master_file(self, file_path: str) -> dict:
        """Upload and import a master data file to the backend."""
        with open(file_path, "rb") as f:
            response = requests.post(
            f"{self.base_url}/api/import/master",
            files={"file": f},
            headers=self._headers(),
            timeout=60,  # Longer timeout for complex files
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Import failed: {response.status_code} - {response.text}")