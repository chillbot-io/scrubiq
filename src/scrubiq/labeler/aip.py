"""AIP Unified Labeling client for local file labeling.

Uses Microsoft's Azure Information Protection client (PowerShell module)
to apply sensitivity labels directly to files on disk.

The label metadata is embedded in the file and travels with it when
uploaded to SharePoint, emailed, etc.

Requirements:
- Windows OS
- PowerShell 5.1+ or PowerShell Core
- AzureInformationProtection module installed
- User authenticated to Azure AD (or service principal)

Installation:
    # PowerShell (as admin)
    Install-Module -Name AzureInformationProtection

Usage:
    from scrubiq.labeler.aip import AIPClient

    client = AIPClient()
    if client.is_available():
        success, msg = client.apply_label(Path("doc.docx"), "label-guid")
"""

import subprocess
import shutil
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class AIPFileStatus:
    """Status of a file's sensitivity label."""

    path: str
    label_id: Optional[str] = None
    label_name: Optional[str] = None
    owner: Optional[str] = None
    is_labeled: bool = False
    is_protected: bool = False  # RMS protection
    error: Optional[str] = None


class AIPClient:
    """
    Apply sensitivity labels using AIP Unified Labeling client.

    This shells out to PowerShell to use the AzureInformationProtection
    module cmdlets:
    - Set-AIPFileLabel: Apply a label
    - Get-AIPFileStatus: Get current label
    - Remove-AIPFileLabel: Remove label

    Labels are embedded in the file metadata and persist when the file
    is moved, copied, or uploaded to SharePoint.

    Usage:
        client = AIPClient()

        # Check if AIP is available
        if not client.is_available():
            print("Install AIP client first")
            return

        # Apply label
        success, message = client.apply_label(
            Path("document.docx"),
            label_id="guid-here"
        )

        # Check current label
        status = client.get_status(Path("document.docx"))
        print(f"Current label: {status.label_name}")
    """

    def __init__(self):
        self._powershell: Optional[str] = None
        self._aip_available: Optional[bool] = None
        self._aip_version: Optional[str] = None

    @property
    def powershell_path(self) -> Optional[str]:
        """Find PowerShell executable."""
        if self._powershell is None:
            # Prefer PowerShell Core, fall back to Windows PowerShell
            for name in ["pwsh", "powershell.exe", "powershell"]:
                path = shutil.which(name)
                if path:
                    self._powershell = path
                    break
        return self._powershell

    def is_available(self) -> bool:
        """
        Check if AIP client is installed and available.

        Returns True if:
        - PowerShell is available
        - AzureInformationProtection module is installed
        """
        if self._aip_available is not None:
            return self._aip_available

        if not self.powershell_path:
            logger.debug("PowerShell not found")
            self._aip_available = False
            return False

        # Check for AIP module
        result = self._run_ps(
            "Get-Module -ListAvailable AzureInformationProtection | Select-Object -First 1 | ConvertTo-Json"
        )

        if result.returncode != 0 or not result.stdout.strip():
            logger.debug("AIP module not found")
            self._aip_available = False
            return False

        try:
            module_info = json.loads(result.stdout)
            self._aip_version = module_info.get("Version", "unknown")
            logger.debug(f"AIP module version: {self._aip_version}")
            self._aip_available = True
        except json.JSONDecodeError:
            # Module exists but couldn't parse version
            self._aip_available = True

        return self._aip_available

    @property
    def version(self) -> Optional[str]:
        """Get AIP module version."""
        self.is_available()  # Ensure we've checked
        return self._aip_version

    def _run_ps(self, command: str, timeout: int = 60) -> subprocess.CompletedProcess:
        """Run a PowerShell command."""
        return subprocess.run(
            [self.powershell_path, "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def apply_label(
        self,
        file_path: Path,
        label_id: str,
        justification: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Apply sensitivity label to a file.

        Args:
            file_path: Path to the file
            label_id: Sensitivity label GUID
            justification: Required if downgrading or removing label
            owner: Override the Rights Management owner

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.is_available():
            return (
                False,
                "AIP client not installed. Install with: Install-Module AzureInformationProtection",
            )

        file_path = Path(file_path).resolve()

        if not file_path.exists():
            return False, f"File not found: {file_path}"

        # Build command
        cmd_parts = [
            "Set-AIPFileLabel",
            f'-Path "{file_path}"',
            f'-LabelId "{label_id}"',
        ]

        if justification:
            # Escape quotes in justification
            safe_justification = justification.replace('"', '`"')
            cmd_parts.append(f'-JustificationMessage "{safe_justification}"')

        if owner:
            cmd_parts.append(f'-Owner "{owner}"')

        cmd = " ".join(cmd_parts)

        logger.debug(f"Running: {cmd}")

        try:
            result = self._run_ps(cmd)
        except subprocess.TimeoutExpired:
            return False, "Command timed out"

        if result.returncode == 0:
            logger.info(f"Label applied to {file_path}")
            return True, "Label applied successfully"
        else:
            error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            # Clean up PowerShell error formatting
            error = self._clean_ps_error(error)
            logger.error(f"Failed to label {file_path}: {error}")
            return False, error

    def get_status(self, file_path: Path) -> AIPFileStatus:
        """
        Get current label status of a file.

        Args:
            file_path: Path to the file

        Returns:
            AIPFileStatus with label information
        """
        file_path = Path(file_path).resolve()

        status = AIPFileStatus(path=str(file_path))

        if not self.is_available():
            status.error = "AIP client not installed"
            return status

        if not file_path.exists():
            status.error = f"File not found: {file_path}"
            return status

        cmd = f'Get-AIPFileStatus -Path "{file_path}" | ConvertTo-Json -Depth 3'

        try:
            result = self._run_ps(cmd)
        except subprocess.TimeoutExpired:
            status.error = "Command timed out"
            return status

        if result.returncode != 0:
            status.error = self._clean_ps_error(result.stderr or result.stdout)
            return status

        if not result.stdout.strip():
            # No output usually means no label
            return status

        try:
            data = json.loads(result.stdout)

            # Handle both single file and array response
            if isinstance(data, list):
                data = data[0] if data else {}

            status.label_id = data.get("MainLabelId") or data.get("LabelId")
            status.label_name = data.get("MainLabelName") or data.get("LabelName")
            status.owner = data.get("Owner")
            status.is_labeled = bool(status.label_id)
            status.is_protected = data.get("IsProtected", False)

        except json.JSONDecodeError as e:
            status.error = f"Failed to parse response: {e}"

        return status

    def remove_label(
        self,
        file_path: Path,
        justification: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Remove sensitivity label from a file.

        Args:
            file_path: Path to the file
            justification: May be required by policy

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.is_available():
            return False, "AIP client not installed"

        file_path = Path(file_path).resolve()

        if not file_path.exists():
            return False, f"File not found: {file_path}"

        cmd_parts = [
            "Remove-AIPFileLabel",
            f'-Path "{file_path}"',
        ]

        if justification:
            safe_justification = justification.replace('"', '`"')
            cmd_parts.append(f'-JustificationMessage "{safe_justification}"')

        cmd = " ".join(cmd_parts)

        try:
            result = self._run_ps(cmd)
        except subprocess.TimeoutExpired:
            return False, "Command timed out"

        if result.returncode == 0:
            return True, "Label removed successfully"
        else:
            error = self._clean_ps_error(result.stderr or result.stdout)
            return False, error

    def get_labels(self) -> list[dict]:
        """
        Get available sensitivity labels.

        Returns list of label dictionaries with id, name, description.
        """
        if not self.is_available():
            return []

        cmd = "Get-AIPLabel | Select-Object Id, Name, Description, ParentId | ConvertTo-Json"

        try:
            result = self._run_ps(cmd, timeout=30)
        except subprocess.TimeoutExpired:
            logger.error("Timeout getting labels")
            return []

        if result.returncode != 0:
            logger.error(f"Failed to get labels: {result.stderr}")
            return []

        if not result.stdout.strip():
            return []

        try:
            data = json.loads(result.stdout)
            # Ensure it's a list
            if isinstance(data, dict):
                data = [data]
            return data
        except json.JSONDecodeError:
            return []

    def authenticate(self, service_principal: bool = False) -> Tuple[bool, str]:
        """
        Authenticate to Azure AD for labeling.

        Args:
            service_principal: If True, use service principal auth
                              (requires SCRUBIQ_CLIENT_ID, SCRUBIQ_CLIENT_SECRET, SCRUBIQ_TENANT_ID)

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.is_available():
            return False, "AIP client not installed"

        if service_principal:
            # Service principal authentication
            import os

            tenant_id = os.environ.get("SCRUBIQ_TENANT_ID")
            client_id = os.environ.get("SCRUBIQ_CLIENT_ID")
            client_secret = os.environ.get("SCRUBIQ_CLIENT_SECRET")

            if not all([tenant_id, client_id, client_secret]):
                return False, "Missing environment variables for service principal auth"

            cmd = f"""
                $secureSecret = ConvertTo-SecureString "{client_secret}" -AsPlainText -Force
                $credential = New-Object System.Management.Automation.PSCredential("{client_id}", $secureSecret)
                Set-AIPAuthentication -TenantId "{tenant_id}" -ServicePrincipal -Credential $credential
            """
        else:
            # Interactive authentication
            cmd = "Set-AIPAuthentication"

        try:
            result = self._run_ps(cmd, timeout=120)
        except subprocess.TimeoutExpired:
            return False, "Authentication timed out"

        if result.returncode == 0:
            return True, "Authentication successful"
        else:
            error = self._clean_ps_error(result.stderr or result.stdout)
            return False, error

    def _clean_ps_error(self, error: str) -> str:
        """Clean up PowerShell error formatting."""
        if not error:
            return "Unknown error"

        # Remove common PowerShell noise
        error = re.sub(r"At line:\d+ char:\d+", "", error)
        error = re.sub(r"\+ .*\n", "", error)
        error = re.sub(r"\+ ~~+", "", error)
        error = re.sub(r"CategoryInfo\s*:.*", "", error)
        error = re.sub(r"FullyQualifiedErrorId\s*:.*", "", error)

        # Get just the message
        lines = [line.strip() for line in error.split("\n") if line.strip()]
        if lines:
            return lines[0]

        return "Unknown error"


def is_available() -> bool:
    """Check if AIP client is available."""
    return AIPClient().is_available()
