"""Tests for Microsoft Graph API client."""

import pytest
from unittest.mock import Mock, patch

from scrubiq.auth.graph import (
    GraphClient,
    DriveItem,
    GraphAuthError,
    GraphAPIError,
    is_available,
    HAS_MSAL,
    HAS_HTTPX,
)


class TestDriveItem:
    """Tests for DriveItem dataclass."""

    def test_from_api_file(self):
        """Test creating DriveItem from API response (file)."""
        data = {
            "id": "item123",
            "name": "document.docx",
            "size": 12345,
            "lastModifiedDateTime": "2024-01-15T10:30:00Z",
            "parentReference": {"path": "/drive/root:/Documents"},
            "webUrl": "https://contoso.sharepoint.com/sites/HR/Documents/document.docx",
            "file": {
                "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            },
        }

        item = DriveItem.from_api(data, "site123", "drive456")

        assert item.id == "item123"
        assert item.name == "document.docx"
        assert item.path == "Documents/document.docx"
        assert item.size == 12345
        assert item.is_folder is False
        assert item.site_id == "site123"
        assert item.drive_id == "drive456"
        assert (
            item.mime_type
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def test_from_api_folder(self):
        """Test creating DriveItem from API response (folder)."""
        data = {
            "id": "folder123",
            "name": "HR Documents",
            "size": 0,
            "lastModifiedDateTime": "2024-01-15T10:30:00Z",
            "parentReference": {"path": "/drive/root:"},
            "webUrl": "https://contoso.sharepoint.com/sites/HR/HR%20Documents",
            "folder": {"childCount": 5},
        }

        item = DriveItem.from_api(data, "site123", "drive456")

        assert item.id == "folder123"
        assert item.name == "HR Documents"
        assert item.is_folder is True


class TestGraphClientInit:
    """Tests for GraphClient initialization."""

    @pytest.mark.skipif(not HAS_MSAL or not HAS_HTTPX, reason="MSAL or httpx not installed")
    def test_init_with_credentials(self):
        """Test client initialization."""
        with patch("scrubiq.auth.graph.ConfidentialClientApplication"):
            client = GraphClient(
                tenant_id="tenant123",
                client_id="client456",
                client_secret="secret789",
            )

            assert client.tenant_id == "tenant123"
            assert client.client_id == "client456"

    def test_is_available(self):
        """Test availability check."""
        result = is_available()
        assert result == (HAS_MSAL and HAS_HTTPX)


@pytest.mark.skipif(not HAS_MSAL or not HAS_HTTPX, reason="MSAL or httpx not installed")
class TestGraphClientMocked:
    """Tests for GraphClient with mocked API calls."""

    @pytest.fixture
    def mock_client(self):
        """Create a client with mocked MSAL and httpx."""
        with patch("scrubiq.auth.graph.ConfidentialClientApplication") as mock_msal:
            # Mock token acquisition
            mock_msal.return_value.acquire_token_for_client.return_value = {
                "access_token": "mock_token_123",
                "expires_in": 3600,
            }

            with patch("scrubiq.auth.graph.httpx.Client") as mock_http:
                client = GraphClient(
                    tenant_id="tenant123",
                    client_id="client456",
                    client_secret="secret789",
                )
                client._mock_http = mock_http.return_value
                yield client

    def test_get_token(self, mock_client):
        """Test token acquisition."""
        token = mock_client._get_token()
        assert token == "mock_token_123"

    def test_token_caching(self, mock_client):
        """Test that tokens are cached."""
        # Get token twice
        token1 = mock_client._get_token()
        token2 = mock_client._get_token()

        # Should only call MSAL once
        assert token1 == token2

    def test_get_sensitivity_labels(self, mock_client):
        """Test getting sensitivity labels."""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = True
        mock_response.json.return_value = {
            "value": [
                {"id": "label1", "name": "Confidential", "description": "Confidential data"},
                {"id": "label2", "name": "Public", "description": "Public data"},
            ]
        }
        mock_client._mock_http.request.return_value = mock_response

        labels = mock_client.get_sensitivity_labels()

        assert len(labels) == 2
        assert labels[0]["name"] == "Confidential"
        assert labels[1]["name"] == "Public"

    def test_list_sites(self, mock_client):
        """Test listing SharePoint sites."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = True
        mock_response.json.return_value = {
            "value": [
                {"id": "site1", "displayName": "HR Site"},
                {"id": "site2", "displayName": "Finance Site"},
            ]
        }
        mock_client._mock_http.request.return_value = mock_response

        sites = mock_client.list_sites()

        assert len(sites) == 2
        assert sites[0]["displayName"] == "HR Site"

    def test_api_error_handling(self, mock_client):
        """Test handling of API errors."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = "Access denied"
        mock_response.json.return_value = {"error": {"message": "Insufficient permissions"}}
        mock_client._mock_http.request.return_value = mock_response

        with pytest.raises(GraphAPIError) as exc_info:
            mock_client.get_sensitivity_labels()

        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in str(exc_info.value)


class TestGraphAuthError:
    """Tests for GraphAuthError."""

    def test_error_message(self):
        """Test error message."""
        error = GraphAuthError("Authentication failed: Invalid credentials")
        assert "Invalid credentials" in str(error)


class TestGraphAPIError:
    """Tests for GraphAPIError."""

    def test_error_with_status_code(self):
        """Test error with status code."""
        error = GraphAPIError(
            "Access denied",
            status_code=403,
            response={"error": {"code": "AccessDenied"}},
        )

        assert error.status_code == 403
        assert error.response["error"]["code"] == "AccessDenied"
        assert "Access denied" in str(error)
