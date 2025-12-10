"""Microsoft Graph API client for SharePoint/OneDrive operations.

This module provides authenticated access to Microsoft Graph API for:
- Listing SharePoint sites and document libraries
- Downloading file content
- Getting and applying sensitivity labels

Authentication uses MSAL with client credentials (app-only auth).
Requires an Azure AD app registration with appropriate permissions.

Required Graph API permissions:
- Sites.Read.All (list sites, download files)
- Files.Read.All (access file content)
- InformationProtectionPolicy.Read (get available labels)
- Sites.ReadWrite.All (apply labels) - only needed for --apply

Usage:
    client = GraphClient(tenant_id, client_id, client_secret)

    # List sites
    sites = client.list_sites()

    # Get labels
    labels = client.get_sensitivity_labels()

    # Apply label (requires Sites.ReadWrite.All)
    client.apply_label(site_id, drive_id, item_id, label_id)
"""

from dataclasses import dataclass
from typing import Optional, Iterator
from datetime import datetime, timedelta
import logging

try:
    from msal import ConfidentialClientApplication

    HAS_MSAL = True
except ImportError:
    HAS_MSAL = False
    ConfidentialClientApplication = None

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_BETA = "https://graph.microsoft.com/beta"


class GraphAuthError(Exception):
    """Authentication with Microsoft Graph failed."""

    pass


class GraphAPIError(Exception):
    """Microsoft Graph API request failed."""

    def __init__(self, message: str, status_code: int = None, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}


@dataclass
class DriveItem:
    """Represents a file or folder in SharePoint/OneDrive."""

    id: str
    name: str
    path: str
    size: int
    modified: datetime
    is_folder: bool
    site_id: str
    drive_id: str
    web_url: str = ""
    mime_type: str = ""

    @classmethod
    def from_api(cls, data: dict, site_id: str, drive_id: str) -> "DriveItem":
        """Create from Graph API response."""
        parent_path = data.get("parentReference", {}).get("path", "")
        # Path looks like /drive/root:/folder/subfolder
        if ":" in parent_path:
            parent_path = parent_path.split(":", 1)[1]

        return cls(
            id=data["id"],
            name=data["name"],
            path=f"{parent_path}/{data['name']}".lstrip("/"),
            size=data.get("size", 0),
            modified=(
                datetime.fromisoformat(data.get("lastModifiedDateTime", "").replace("Z", "+00:00"))
                if data.get("lastModifiedDateTime")
                else datetime.now()
            ),
            is_folder="folder" in data,
            site_id=site_id,
            drive_id=drive_id,
            web_url=data.get("webUrl", ""),
            mime_type=data.get("file", {}).get("mimeType", ""),
        )


class GraphClient:
    """
    Microsoft Graph API client for SharePoint/OneDrive operations.

    Handles authentication via MSAL and provides methods for:
    - Listing SharePoint sites and drives
    - Browsing and downloading files
    - Getting and applying sensitivity labels

    Authentication:
        Uses client credentials flow (app-only).
        Requires Azure AD app with appropriate permissions.

    Usage:
        client = GraphClient(tenant_id, client_id, client_secret)

        # Check connection
        if client.test_connection():
            print("Connected!")

        # List sites
        for site in client.list_sites():
            print(site["displayName"])

        # Get sensitivity labels
        labels = client.get_sensitivity_labels()

        # Apply label to file
        client.apply_label(site_id, drive_id, item_id, label_id)
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
    ):
        """
        Initialize Graph client.

        Args:
            tenant_id: Azure AD tenant ID (GUID or domain)
            client_id: Azure AD application (client) ID
            client_secret: Client secret for the application

        Raises:
            ImportError: If msal or httpx not installed
        """
        if not HAS_MSAL:
            raise ImportError("msal required for Graph API. Install with: pip install msal")
        if not HAS_HTTPX:
            raise ImportError("httpx required for Graph API. Install with: pip install httpx")

        self.tenant_id = tenant_id
        self.client_id = client_id

        self._app = ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )

        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None

        # HTTP client with reasonable defaults
        self._http = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
        )

    def _get_token(self) -> str:
        """
        Acquire or refresh access token.

        Returns:
            Access token string

        Raises:
            GraphAuthError: If authentication fails
        """
        # Check if current token is still valid (with 5 min buffer)
        if self._token and self._token_expires:
            if datetime.now() < self._token_expires - timedelta(minutes=5):
                return self._token

        # Acquire new token
        result = self._app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

        if "access_token" not in result:
            error = result.get("error_description", result.get("error", "Unknown error"))
            raise GraphAuthError(f"Authentication failed: {error}")

        self._token = result["access_token"]
        # Tokens typically expire in 1 hour
        expires_in = result.get("expires_in", 3600)
        self._token_expires = datetime.now() + timedelta(seconds=expires_in)

        logger.debug(f"Acquired token, expires in {expires_in}s")
        return self._token

    @property
    def _headers(self) -> dict:
        """Get request headers with current auth token."""
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        json: dict = None,
        params: dict = None,
        beta: bool = False,
    ) -> dict:
        """
        Make authenticated request to Graph API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            json: Request body for POST/PATCH
            params: Query parameters
            beta: Use beta endpoint instead of v1.0

        Returns:
            Response JSON as dict

        Raises:
            GraphAPIError: If request fails
        """
        base = GRAPH_BETA if beta else GRAPH_BASE
        url = f"{base}{endpoint}"

        try:
            response = self._http.request(
                method=method,
                url=url,
                headers=self._headers,
                json=json,
                params=params,
            )

            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", response.text)
                except (ValueError, KeyError):
                    error_msg = response.text

                raise GraphAPIError(
                    f"Graph API error: {error_msg}",
                    status_code=response.status_code,
                    response=error_data if "error_data" in dir() else {},
                )

            if response.content:
                return response.json()
            return {}

        except httpx.RequestError as e:
            raise GraphAPIError(f"Request failed: {e}")

    def test_connection(self) -> bool:
        """
        Test if credentials are valid.

        Returns:
            True if authentication succeeds
        """
        try:
            self._get_token()
            # Try a simple API call
            self._request("GET", "/me")
            return True
        except (GraphAuthError, GraphAPIError):
            # /me fails with app-only auth, try organization instead
            try:
                self._request("GET", "/organization")
                return True
            except (GraphAuthError, GraphAPIError):
                return False

    # =========================================================================
    # Sites and Drives
    # =========================================================================

    def list_sites(self, search: str = "*") -> list[dict]:
        """
        List SharePoint sites.

        Args:
            search: Search query (default: all sites)

        Returns:
            List of site objects with id, displayName, webUrl
        """
        response = self._request("GET", "/sites", params={"search": search})
        return response.get("value", [])

    def get_site(self, site_id: str) -> dict:
        """Get site by ID."""
        return self._request("GET", f"/sites/{site_id}")

    def get_site_by_url(self, hostname: str, site_path: str) -> dict:
        """
        Get site by URL components.

        Args:
            hostname: e.g., "contoso.sharepoint.com"
            site_path: e.g., "/sites/HR" or "/teams/Project"

        Returns:
            Site object
        """
        return self._request("GET", f"/sites/{hostname}:{site_path}")

    def list_drives(self, site_id: str) -> list[dict]:
        """
        List document libraries (drives) in a site.

        Args:
            site_id: SharePoint site ID

        Returns:
            List of drive objects
        """
        response = self._request("GET", f"/sites/{site_id}/drives")
        return response.get("value", [])

    # =========================================================================
    # Files and Folders
    # =========================================================================

    def list_items(
        self,
        site_id: str,
        drive_id: str,
        folder_id: str = "root",
    ) -> list[DriveItem]:
        """
        List items in a folder.

        Args:
            site_id: SharePoint site ID
            drive_id: Document library ID
            folder_id: Folder ID or "root" for root folder

        Returns:
            List of DriveItem objects
        """
        response = self._request(
            "GET",
            f"/sites/{site_id}/drives/{drive_id}/items/{folder_id}/children",
        )

        return [DriveItem.from_api(item, site_id, drive_id) for item in response.get("value", [])]

    def list_items_recursive(
        self,
        site_id: str,
        drive_id: str,
        folder_id: str = "root",
    ) -> Iterator[DriveItem]:
        """
        Recursively list all items in a folder.

        Args:
            site_id: SharePoint site ID
            drive_id: Document library ID
            folder_id: Starting folder ID

        Yields:
            DriveItem for each file (not folders)
        """
        items = self.list_items(site_id, drive_id, folder_id)

        for item in items:
            if item.is_folder:
                yield from self.list_items_recursive(site_id, drive_id, item.id)
            else:
                yield item

    def get_item(self, site_id: str, drive_id: str, item_id: str) -> DriveItem:
        """Get item metadata."""
        response = self._request(
            "GET",
            f"/sites/{site_id}/drives/{drive_id}/items/{item_id}",
        )
        return DriveItem.from_api(response, site_id, drive_id)

    def download_file(
        self,
        site_id: str,
        drive_id: str,
        item_id: str,
    ) -> bytes:
        """
        Download file content.

        Args:
            site_id: SharePoint site ID
            drive_id: Document library ID
            item_id: File item ID

        Returns:
            File content as bytes
        """
        url = f"{GRAPH_BASE}/sites/{site_id}/drives/{drive_id}/items/{item_id}/content"

        response = self._http.get(
            url,
            headers=self._headers,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.content

    # =========================================================================
    # Sensitivity Labels
    # =========================================================================

    def get_sensitivity_labels(self) -> list[dict]:
        """
        Get available sensitivity labels.

        Returns:
            List of label objects with id, name, description, color

        Note:
            Requires InformationProtectionPolicy.Read permission
        """
        response = self._request(
            "GET",
            "/informationProtection/policy/labels",
        )
        return response.get("value", [])

    def get_file_label(
        self,
        site_id: str,
        drive_id: str,
        item_id: str,
    ) -> Optional[dict]:
        """
        Get current sensitivity label on a file.

        Args:
            site_id: SharePoint site ID
            drive_id: Document library ID
            item_id: File item ID

        Returns:
            Label info dict or None if no label
        """
        try:
            response = self._request(
                "GET",
                f"/sites/{site_id}/drives/{drive_id}/items/{item_id}/extractSensitivityLabels",
            )
            labels = response.get("labels", [])
            return labels[0] if labels else None
        except GraphAPIError as e:
            if e.status_code == 404:
                return None
            raise

    def apply_label(
        self,
        site_id: str,
        drive_id: str,
        item_id: str,
        label_id: str,
        justification: str = "Applied by scrubIQ",
    ) -> dict:
        """
        Apply sensitivity label to a file.

        Args:
            site_id: SharePoint site ID
            drive_id: Document library ID
            item_id: File item ID
            label_id: Sensitivity label GUID
            justification: Reason for applying label

        Returns:
            API response dict

        Note:
            Requires Sites.ReadWrite.All permission
        """
        return self._request(
            "POST",
            f"/sites/{site_id}/drives/{drive_id}/items/{item_id}/assignSensitivityLabel",
            json={
                "sensitivityLabelId": label_id,
                "assignmentMethod": "auto",
                "justificationText": justification,
            },
        )

    def remove_label(
        self,
        site_id: str,
        drive_id: str,
        item_id: str,
        justification: str = "Removed by scrubIQ",
    ) -> dict:
        """
        Remove sensitivity label from a file.

        Args:
            site_id: SharePoint site ID
            drive_id: Document library ID
            item_id: File item ID
            justification: Reason for removal

        Returns:
            API response dict
        """
        return self._request(
            "POST",
            f"/sites/{site_id}/drives/{drive_id}/items/{item_id}/assignSensitivityLabel",
            json={
                "sensitivityLabelId": "",
                "assignmentMethod": "auto",
                "justificationText": justification,
            },
        )

    def close(self):
        """Close HTTP client."""
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def is_available() -> bool:
    """Check if Graph API dependencies are installed."""
    return HAS_MSAL and HAS_HTTPX
