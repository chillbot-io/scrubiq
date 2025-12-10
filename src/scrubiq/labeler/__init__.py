"""Sensitivity label application.

This module provides two methods for applying Microsoft sensitivity labels:

1. AIP Client (local files):
   - Uses Azure Information Protection PowerShell module
   - Labels embedded in file metadata
   - Works on Windows with AIP client installed

2. Graph API (SharePoint/OneDrive):
   - Uses Microsoft Graph API
   - Requires site_id, drive_id, item_id
   - Works cross-platform

Usage:
    from scrubiq.labeler import Labeler, AIPClient

    # For SharePoint files
    labeler = Labeler(tenant_id, client_id, client_secret)
    labeler.apply_label(site_id, drive_id, item_id, label_id)

    # For local files
    aip = AIPClient()
    if aip.is_available():
        aip.apply_label(Path("doc.docx"), label_id)
"""

from .labeler import Labeler, LabelResult, LabelSummary, LabelMapping
from .aip import AIPClient, AIPFileStatus, is_available as aip_is_available

__all__ = [
    "Labeler",
    "LabelResult",
    "LabelSummary",
    "LabelMapping",
    "AIPClient",
    "AIPFileStatus",
    "aip_is_available",
]
