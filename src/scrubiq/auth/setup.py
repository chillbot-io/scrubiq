"""Azure App Registration setup wizard.

This module automates the creation of an Azure AD app registration
in the customer's tenant. It uses a "bootstrap" app (multi-tenant)
to authenticate an admin, then creates the actual scrubIQ app
registration with the correct permissions.

Flow:
1. Admin runs `scrubiq setup`
2. Device code flow authenticates admin via browser
3. Uses admin's token to create app registration
4. Grants admin consent for required permissions
5. Creates client secret
6. Saves credentials to config

Required Graph API permissions for the created app:
- Sites.Read.All: List SharePoint sites, read files
- Files.Read.All: Read file content
- InformationProtectionPolicy.Read: Get sensitivity labels
- Sites.ReadWrite.All: Apply labels (optional, for Graph API labeling)

The bootstrap app needs:
- Application.ReadWrite.All (delegated): Create app registrations
- DelegatedPermissionGrant.ReadWrite.All (delegated): Grant consent
"""

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Callable
import logging

logger = logging.getLogger(__name__)

# Well-known Microsoft Graph app ID
GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"

# Permission IDs for Microsoft Graph
# https://learn.microsoft.com/en-us/graph/permissions-reference
GRAPH_PERMISSIONS = {
    # Application permissions (Role)
    "Sites.Read.All": "332a536c-c7ef-4017-ab91-336970924f0d",
    "Sites.ReadWrite.All": "9492366f-7969-46a4-8d15-ed1a20078fff",
    "Files.Read.All": "01d4889c-1287-42c6-ac1f-5d1e02578ef6",
    "Files.ReadWrite.All": "75359482-378d-4052-8f01-80520e7db3cd",
    "InformationProtectionPolicy.Read.All": "19da66cb-0fb0-4390-b071-ebc76a349482",
    # Delegated permissions (Scope) - for setup
    "Application.ReadWrite.All": "1bfefb4e-e0b5-418b-a88f-73c46d2cc8e9",
    "Directory.Read.All": "06da0dbc-49e2-44d2-8312-53f166ab848a",
}

# Permissions needed by scrubIQ app
SCRUBIQ_APP_PERMISSIONS = [
    ("Sites.Read.All", "Role"),
    ("Files.Read.All", "Role"),
    ("InformationProtectionPolicy.Read.All", "Role"),
]

# Optional: for Graph API labeling (not AIP client)
SCRUBIQ_LABELING_PERMISSIONS = [
    ("Sites.ReadWrite.All", "Role"),
]


@dataclass
class SetupResult:
    """Result of app registration setup."""

    success: bool
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    app_object_id: Optional[str] = None
    error: Optional[str] = None


class AzureSetupWizard:
    """
    Automated Azure AD app registration wizard.

    Creates an app registration in the customer's tenant with
    the correct permissions for scrubIQ to function.

    Usage:
        wizard = AzureSetupWizard(
            bootstrap_client_id="your-multi-tenant-app-id"
        )

        # Start device code flow
        code_info = wizard.start_device_flow()
        print(f"Go to {code_info['verification_uri']}")
        print(f"Enter code: {code_info['user_code']}")

        # Wait for user to authenticate
        result = wizard.complete_setup(
            code_info,
            include_labeling_permissions=True
        )

        if result.success:
            print(f"App created: {result.client_id}")

    If you don't have a bootstrap app, you can use manual setup
    where the user creates the app registration themselves.
    """

    # Default bootstrap app - replace with your own multi-tenant app
    # This app only needs delegated Application.ReadWrite.All permission
    DEFAULT_BOOTSTRAP_APP = None  # Set this when you register your bootstrap app

    def __init__(
        self,
        bootstrap_client_id: Optional[str] = None,
    ):
        """
        Initialize the setup wizard.

        Args:
            bootstrap_client_id: Client ID of multi-tenant bootstrap app.
                                If None, will use manual setup flow.
        """
        self.bootstrap_client_id = bootstrap_client_id or self.DEFAULT_BOOTSTRAP_APP
        self._msal_app = None
        self._access_token = None
        self._tenant_id = None

    @property
    def can_auto_setup(self) -> bool:
        """Check if automated setup is available."""
        if not self.bootstrap_client_id:
            return False
        import importlib.util

        return importlib.util.find_spec("msal") is not None

    def start_device_flow(self) -> dict:
        """
        Start device code authentication flow.

        Returns dict with:
        - verification_uri: URL to open in browser
        - user_code: Code to enter
        - message: Full message to display
        - expires_in: Seconds until code expires

        Raises:
            RuntimeError: If bootstrap app not configured or MSAL not available
        """
        if not self.bootstrap_client_id:
            raise RuntimeError(
                "Bootstrap app not configured. Use manual setup or configure "
                "SCRUBIQ_BOOTSTRAP_APP_ID environment variable."
            )

        try:
            from msal import PublicClientApplication
        except ImportError:
            raise RuntimeError("MSAL not installed. Run: pip install msal")

        self._msal_app = PublicClientApplication(
            client_id=self.bootstrap_client_id,
            authority="https://login.microsoftonline.com/common",
        )

        flow = self._msal_app.initiate_device_flow(
            scopes=[
                "https://graph.microsoft.com/Application.ReadWrite.All",
                "https://graph.microsoft.com/Directory.Read.All",
            ]
        )

        if "error" in flow:
            raise RuntimeError(
                f"Failed to start device flow: {flow.get('error_description', flow['error'])}"
            )

        return flow

    def wait_for_authentication(
        self,
        flow: dict,
        on_waiting: Optional[Callable[[int], None]] = None,
        timeout: int = 300,
    ) -> bool:
        """
        Wait for user to complete authentication.

        Args:
            flow: Flow dict from start_device_flow()
            on_waiting: Callback(seconds_elapsed) while waiting
            timeout: Max seconds to wait

        Returns:
            True if authenticated successfully
        """
        if not self._msal_app:
            raise RuntimeError("Call start_device_flow first")

        start = time.time()

        while time.time() - start < timeout:
            if on_waiting:
                on_waiting(int(time.time() - start))

            result = self._msal_app.acquire_token_by_device_flow(flow)

            if "access_token" in result:
                self._access_token = result["access_token"]
                # Extract tenant from token
                self._tenant_id = self._extract_tenant_from_token(result)
                logger.info(f"Authenticated to tenant: {self._tenant_id}")
                return True

            if result.get("error") == "authorization_pending":
                time.sleep(flow.get("interval", 5))
                continue

            # Real error
            logger.error(f"Authentication failed: {result}")
            return False

        logger.error("Authentication timed out")
        return False

    def _extract_tenant_from_token(self, result: dict) -> Optional[str]:
        """Extract tenant ID from token response."""
        # Try id_token_claims first
        claims = result.get("id_token_claims", {})
        tenant = claims.get("tid")
        if tenant:
            return tenant

        # Try decoding access token (not recommended but works)
        try:
            import base64
            import json

            token = result["access_token"]
            payload = token.split(".")[1]
            # Add padding
            payload += "=" * (4 - len(payload) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(payload))
            return decoded.get("tid")
        except Exception:
            pass

        return None

    def complete_setup(
        self,
        flow: dict,
        app_name: str = "scrubIQ",
        include_labeling_permissions: bool = True,
        secret_validity_days: int = 365,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> SetupResult:
        """
        Complete the setup after authentication.

        This creates the app registration, grants permissions,
        and generates a client secret.

        Args:
            flow: Flow dict from start_device_flow()
            app_name: Display name for the app
            include_labeling_permissions: Include Sites.ReadWrite.All for Graph labeling
            secret_validity_days: How long the client secret should be valid
            on_progress: Callback(status_message) for progress updates

        Returns:
            SetupResult with credentials or error
        """

        def progress(msg: str):
            logger.info(msg)
            if on_progress:
                on_progress(msg)

        # Wait for authentication if not already done
        if not self._access_token:
            progress("Waiting for authentication...")
            if not self.wait_for_authentication(flow):
                return SetupResult(success=False, error="Authentication failed")

        progress("Creating app registration...")

        try:
            import httpx
        except ImportError:
            return SetupResult(success=False, error="httpx not installed")

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

        # Build required permissions
        permissions = list(SCRUBIQ_APP_PERMISSIONS)
        if include_labeling_permissions:
            permissions.extend(SCRUBIQ_LABELING_PERMISSIONS)

        resource_access = [
            {
                "id": GRAPH_PERMISSIONS[perm],
                "type": perm_type,
            }
            for perm, perm_type in permissions
        ]

        # Create app registration
        app_payload = {
            "displayName": app_name,
            "signInAudience": "AzureADMyOrg",  # Single tenant
            "requiredResourceAccess": [
                {
                    "resourceAppId": GRAPH_APP_ID,
                    "resourceAccess": resource_access,
                }
            ],
        }

        try:
            response = httpx.post(
                "https://graph.microsoft.com/v1.0/applications",
                headers=headers,
                json=app_payload,
                timeout=30.0,
            )

            if response.status_code != 201:
                error = response.json().get("error", {}).get("message", response.text)
                return SetupResult(success=False, error=f"Failed to create app: {error}")

            app_data = response.json()
            app_object_id = app_data["id"]
            client_id = app_data["appId"]

            progress(f"App created: {client_id}")

        except Exception as e:
            return SetupResult(success=False, error=f"Failed to create app: {e}")

        # Create service principal
        progress("Creating service principal...")

        try:
            sp_response = httpx.post(
                "https://graph.microsoft.com/v1.0/servicePrincipals",
                headers=headers,
                json={"appId": client_id},
                timeout=30.0,
            )

            if sp_response.status_code not in (201, 200):
                # Service principal might already exist, try to find it
                pass
            else:
                sp_data = sp_response.json()
                sp_data["id"]

        except Exception as e:
            logger.warning(f"Service principal creation issue: {e}")

        # Grant admin consent
        progress("Granting admin consent...")

        try:
            # Get the Microsoft Graph service principal ID in this tenant
            graph_sp_response = httpx.get(
                f"https://graph.microsoft.com/v1.0/servicePrincipals?$filter=appId eq '{GRAPH_APP_ID}'",
                headers=headers,
                timeout=30.0,
            )

            if graph_sp_response.status_code == 200:
                graph_sps = graph_sp_response.json().get("value", [])
                if graph_sps:
                    graph_sp_id = graph_sps[0]["id"]

                    # Get our service principal
                    our_sp_response = httpx.get(
                        f"https://graph.microsoft.com/v1.0/servicePrincipals?$filter=appId eq '{client_id}'",
                        headers=headers,
                        timeout=30.0,
                    )

                    if our_sp_response.status_code == 200:
                        our_sps = our_sp_response.json().get("value", [])
                        if our_sps:
                            our_sp_id = our_sps[0]["id"]

                            # Grant app role assignments
                            for perm, perm_type in permissions:
                                if perm_type == "Role":
                                    grant_response = httpx.post(
                                        f"https://graph.microsoft.com/v1.0/servicePrincipals/{our_sp_id}/appRoleAssignments",
                                        headers=headers,
                                        json={
                                            "principalId": our_sp_id,
                                            "resourceId": graph_sp_id,
                                            "appRoleId": GRAPH_PERMISSIONS[perm],
                                        },
                                        timeout=30.0,
                                    )

                                    if grant_response.status_code in (200, 201):
                                        progress(f"  ✓ {perm}")
                                    else:
                                        logger.warning(
                                            f"Failed to grant {perm}: {grant_response.text}"
                                        )

        except Exception as e:
            logger.warning(f"Admin consent issue: {e}")
            # Continue anyway - admin can grant consent manually

        # Create client secret
        progress("Creating client secret...")

        try:
            secret_end_date = datetime.utcnow() + timedelta(days=secret_validity_days)

            secret_response = httpx.post(
                f"https://graph.microsoft.com/v1.0/applications/{app_object_id}/addPassword",
                headers=headers,
                json={
                    "passwordCredential": {
                        "displayName": "scrubIQ secret",
                        "endDateTime": secret_end_date.isoformat() + "Z",
                    }
                },
                timeout=30.0,
            )

            if secret_response.status_code not in (200, 201):
                error = secret_response.json().get("error", {}).get("message", secret_response.text)
                return SetupResult(
                    success=False,
                    error=f"Failed to create secret: {error}",
                    tenant_id=self._tenant_id,
                    client_id=client_id,
                    app_object_id=app_object_id,
                )

            secret_data = secret_response.json()
            client_secret = secret_data["secretText"]

            progress("✓ Client secret created")

        except Exception as e:
            return SetupResult(
                success=False,
                error=f"Failed to create secret: {e}",
                tenant_id=self._tenant_id,
                client_id=client_id,
                app_object_id=app_object_id,
            )

        progress("✓ Setup complete!")

        return SetupResult(
            success=True,
            tenant_id=self._tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            app_object_id=app_object_id,
        )

    def delete_app(self, app_object_id: str) -> bool:
        """
        Delete an app registration.

        Used for cleanup if setup fails partway through.
        """
        if not self._access_token:
            return False

        try:
            import httpx

            response = httpx.delete(
                f"https://graph.microsoft.com/v1.0/applications/{app_object_id}",
                headers={"Authorization": f"Bearer {self._access_token}"},
                timeout=30.0,
            )
            return response.status_code in (200, 204)
        except Exception:
            return False


class ManualSetupGuide:
    """
    Guide for manual app registration when automated setup isn't available.

    Generates step-by-step instructions for the user.
    """

    @staticmethod
    def get_instructions(app_name: str = "scrubIQ") -> str:
        """Get manual setup instructions."""
        permissions = [
            "Sites.Read.All",
            "Files.Read.All",
            "InformationProtectionPolicy.Read.All",
            "Sites.ReadWrite.All (optional, for Graph API labeling)",
        ]

        return f"""
╔══════════════════════════════════════════════════════════════════════╗
║                    Manual App Registration Setup                       ║
╚══════════════════════════════════════════════════════════════════════╝

STEP 1: Create App Registration
────────────────────────────────
1. Go to: https://portal.azure.com
2. Navigate to: Azure Active Directory → App registrations → New registration
3. Name: {app_name}
4. Supported account types: "Accounts in this organizational directory only"
5. Click "Register"

STEP 2: Note the IDs
────────────────────
From the app's Overview page, copy:
• Application (client) ID: ________________________________
• Directory (tenant) ID:   ________________________________

STEP 3: Add API Permissions
───────────────────────────
1. Go to: API permissions → Add a permission → Microsoft Graph
2. Select "Application permissions"
3. Add these permissions:
   {chr(10).join(f'   • {p}' for p in permissions)}
4. Click "Grant admin consent for [Your Organization]"

STEP 4: Create Client Secret
────────────────────────────
1. Go to: Certificates & secrets → Client secrets → New client secret
2. Description: "scrubIQ"
3. Expiration: 12 months (or as needed)
4. Click "Add"
5. COPY THE SECRET VALUE NOW (it won't be shown again!)

STEP 5: Configure scrubIQ
─────────────────────────
Run: scrubiq config set tenant_id <your-tenant-id>
Run: scrubiq config set client_id <your-client-id>
Run: scrubiq config set client_secret <your-secret>

Or set environment variables:
  export SCRUBIQ_TENANT_ID=<your-tenant-id>
  export SCRUBIQ_CLIENT_ID=<your-client-id>
  export SCRUBIQ_CLIENT_SECRET=<your-secret>

═══════════════════════════════════════════════════════════════════════
"""

    @staticmethod
    def get_permissions_json() -> dict:
        """Get permissions in manifest format for copy/paste."""
        return {
            "requiredResourceAccess": [
                {
                    "resourceAppId": GRAPH_APP_ID,
                    "resourceAccess": [
                        {"id": GRAPH_PERMISSIONS[p], "type": "Role"}
                        for p, _ in SCRUBIQ_APP_PERMISSIONS + SCRUBIQ_LABELING_PERMISSIONS
                    ],
                }
            ]
        }
