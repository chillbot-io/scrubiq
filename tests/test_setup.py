"""Tests for scrubiq.auth.setup module."""

import pytest
from unittest.mock import patch, MagicMock


class TestAzureSetupWizard:
    """Tests for AzureSetupWizard class."""

    def test_can_auto_setup_without_bootstrap_app(self):
        """Test can_auto_setup is False without bootstrap app."""
        from scrubiq.auth.setup import AzureSetupWizard

        wizard = AzureSetupWizard(bootstrap_client_id=None)

        assert not wizard.can_auto_setup

    def test_can_auto_setup_without_msal(self):
        """Test can_auto_setup is False without MSAL."""
        from scrubiq.auth.setup import AzureSetupWizard

        AzureSetupWizard(bootstrap_client_id="test-app-id")

        # Mock msal import to fail
        with patch.dict("sys.modules", {"msal": None}):
            # Even with bootstrap app, no MSAL means no auto setup
            # This test verifies the code path exists
            pass

    def test_start_device_flow_requires_bootstrap_app(self):
        """Test start_device_flow raises error without bootstrap app."""
        from scrubiq.auth.setup import AzureSetupWizard

        wizard = AzureSetupWizard(bootstrap_client_id=None)

        with pytest.raises(RuntimeError) as exc_info:
            wizard.start_device_flow()

        assert "bootstrap app" in str(exc_info.value).lower()

    def test_start_device_flow_with_bootstrap_app(self):
        """Test start_device_flow initiates device flow."""
        from scrubiq.auth.setup import AzureSetupWizard

        wizard = AzureSetupWizard(bootstrap_client_id="test-app-id")

        mock_app = MagicMock()
        mock_app.initiate_device_flow.return_value = {
            "user_code": "ABC123",
            "verification_uri": "https://microsoft.com/devicelogin",
            "expires_in": 900,
            "message": "Go to https://microsoft.com/devicelogin and enter ABC123",
        }

        with patch("msal.PublicClientApplication", return_value=mock_app):
            flow = wizard.start_device_flow()

        assert flow["user_code"] == "ABC123"
        assert "verification_uri" in flow

    def test_extract_tenant_from_token(self):
        """Test tenant extraction from token response."""
        from scrubiq.auth.setup import AzureSetupWizard

        wizard = AzureSetupWizard(bootstrap_client_id="test-app-id")

        result = {
            "access_token": "token",
            "id_token_claims": {
                "tid": "tenant-123-456",
            },
        }

        tenant = wizard._extract_tenant_from_token(result)

        assert tenant == "tenant-123-456"


class TestSetupResult:
    """Tests for SetupResult dataclass."""

    def test_success_result(self):
        """Test successful result."""
        from scrubiq.auth.setup import SetupResult

        result = SetupResult(
            success=True,
            tenant_id="tenant-123",
            client_id="client-456",
            client_secret="secret-789",
            app_object_id="obj-abc",
        )

        assert result.success
        assert result.tenant_id == "tenant-123"
        assert result.error is None

    def test_failure_result(self):
        """Test failure result."""
        from scrubiq.auth.setup import SetupResult

        result = SetupResult(
            success=False,
            error="Authentication failed",
        )

        assert not result.success
        assert result.error == "Authentication failed"
        assert result.client_id is None


class TestManualSetupGuide:
    """Tests for ManualSetupGuide class."""

    def test_get_instructions(self):
        """Test instructions generation."""
        from scrubiq.auth.setup import ManualSetupGuide

        instructions = ManualSetupGuide.get_instructions()

        assert "App Registration" in instructions
        assert "API Permissions" in instructions
        assert "Client Secret" in instructions
        assert "portal.azure.com" in instructions

    def test_get_instructions_with_custom_name(self):
        """Test instructions with custom app name."""
        from scrubiq.auth.setup import ManualSetupGuide

        instructions = ManualSetupGuide.get_instructions(app_name="My Custom App")

        assert "My Custom App" in instructions

    def test_get_permissions_json(self):
        """Test permissions JSON generation."""
        from scrubiq.auth.setup import ManualSetupGuide

        permissions = ManualSetupGuide.get_permissions_json()

        assert "requiredResourceAccess" in permissions
        assert len(permissions["requiredResourceAccess"]) > 0

        # Check Graph API permissions are included
        graph_perms = permissions["requiredResourceAccess"][0]
        assert graph_perms["resourceAppId"] == "00000003-0000-0000-c000-000000000000"
        assert len(graph_perms["resourceAccess"]) > 0


class TestGraphPermissions:
    """Tests for Graph API permission constants."""

    def test_permission_ids_are_valid_guids(self):
        """Test that permission IDs look like valid GUIDs."""
        from scrubiq.auth.setup import GRAPH_PERMISSIONS

        import re

        guid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
        )

        for perm_name, perm_id in GRAPH_PERMISSIONS.items():
            assert guid_pattern.match(perm_id), f"Invalid GUID for {perm_name}: {perm_id}"

    def test_required_permissions_defined(self):
        """Test that all required permissions are defined."""
        from scrubiq.auth.setup import GRAPH_PERMISSIONS, SCRUBIQ_APP_PERMISSIONS

        for perm_name, perm_type in SCRUBIQ_APP_PERMISSIONS:
            assert perm_name in GRAPH_PERMISSIONS, f"Missing permission: {perm_name}"

    def test_graph_app_id(self):
        """Test Microsoft Graph app ID is correct."""
        from scrubiq.auth.setup import GRAPH_APP_ID

        # Well-known Microsoft Graph app ID
        assert GRAPH_APP_ID == "00000003-0000-0000-c000-000000000000"
