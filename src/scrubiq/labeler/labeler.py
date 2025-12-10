"""Apply Microsoft sensitivity labels based on scan results.

This module provides the Labeler class which:
1. Maps scrubIQ label recommendations to Microsoft sensitivity labels
2. Applies labels to SharePoint/OneDrive files via Graph API
3. Supports dry-run mode (default) for safety

Usage:
    from scrubiq.labeler import Labeler
    from scrubiq.scanner import Scanner

    # Scan files
    scanner = Scanner()
    scan_result = scanner.scan("./documents")

    # Apply labels (dry run first)
    labeler = Labeler(tenant_id, client_id, client_secret)
    results = labeler.apply_from_scan(scan_result, dry_run=True)

    # Review results, then apply for real
    results = labeler.apply_from_scan(scan_result, dry_run=False)
"""

from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import datetime
import logging

from ..scanner.results import ScanResult, FileResult, LabelRecommendation
from ..auth.graph import GraphClient, GraphAPIError

logger = logging.getLogger(__name__)


@dataclass
class LabelMapping:
    """
    Maps scrubIQ recommendations to Microsoft sensitivity label IDs.

    Microsoft labels are tenant-specific - the actual GUIDs differ
    per organization. This class handles the mapping.

    Usage:
        mapping = LabelMapping()
        mapping.set("highly_confidential", "a1b2c3d4-...")
        mapping.set("confidential", "e5f6g7h8-...")

        label_id = mapping.get(LabelRecommendation.HIGHLY_CONFIDENTIAL)
    """

    # Map recommendation name to label ID (GUID)
    _mappings: dict[str, str] = field(default_factory=dict)

    # Available labels from tenant (cached)
    _available_labels: list[dict] = field(default_factory=list)

    def set(self, recommendation: str, label_id: str):
        """Set mapping from recommendation name to label ID."""
        self._mappings[recommendation.lower()] = label_id

    def get(self, recommendation: LabelRecommendation) -> Optional[str]:
        """Get label ID for a recommendation."""
        return self._mappings.get(recommendation.value)

    def load_from_tenant(self, client: GraphClient) -> "LabelMapping":
        """
        Auto-map by matching recommendation names to tenant label names.

        This works if your Microsoft labels are named:
        - "Highly Confidential" or "highly_confidential"
        - "Confidential"
        - "Internal"
        - "Public"

        Returns self for chaining.
        """
        self._available_labels = client.get_sensitivity_labels()

        for label in self._available_labels:
            label_name = label.get("name", "").lower().replace(" ", "_")
            label_id = label.get("id")

            # Try to match to our recommendations
            for rec in LabelRecommendation:
                if rec.value == label_name or rec.value.replace("_", "") == label_name.replace(
                    "_", ""
                ):
                    self._mappings[rec.value] = label_id
                    logger.debug(f"Mapped {rec.value} -> {label_id}")

        return self

    def from_dict(self, mappings: dict[str, str]) -> "LabelMapping":
        """Load mappings from dictionary."""
        for k, v in mappings.items():
            self._mappings[k.lower()] = v
        return self

    @property
    def available_labels(self) -> list[dict]:
        """Labels available in the tenant."""
        return self._available_labels

    @property
    def configured_recommendations(self) -> list[str]:
        """Recommendations that have label mappings."""
        return list(self._mappings.keys())


@dataclass
class LabelResult:
    """Result of labeling a single file."""

    # File identification
    path: str
    site_id: str = ""
    drive_id: str = ""
    item_id: str = ""

    # Operation result
    success: bool = False
    dry_run: bool = True

    # Labels
    previous_label: Optional[str] = None
    previous_label_name: Optional[str] = None
    new_label: Optional[str] = None
    new_label_name: Optional[str] = None
    recommendation: Optional[str] = None

    # Error info
    error: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None


@dataclass
class LabelSummary:
    """Summary of labeling operation."""

    total_files: int = 0
    labeled: int = 0
    skipped: int = 0
    errors: int = 0
    dry_run: bool = True

    by_label: dict[str, int] = field(default_factory=dict)
    results: list[LabelResult] = field(default_factory=list)

    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    @property
    def duration_seconds(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0


class Labeler:
    """
    Apply Microsoft sensitivity labels to SharePoint/OneDrive files.

    This is the main class for the labeling workflow:
    1. Connect to Microsoft Graph API
    2. Get available labels from tenant
    3. Map scrubIQ recommendations to label IDs
    4. Apply labels based on scan results

    DRY-RUN BY DEFAULT:
        All operations default to dry_run=True.
        You must explicitly pass dry_run=False to make changes.

    Usage:
        # Initialize with credentials
        labeler = Labeler(tenant_id, client_id, client_secret)

        # See available labels
        labels = labeler.get_labels()
        for label in labels:
            print(f"{label['name']}: {label['id']}")

        # Configure mapping (or use auto-mapping)
        labeler.mapping.set("highly_confidential", "guid-here")
        # OR
        labeler.auto_map_labels()  # Matches by name

        # Apply from scan results
        scanner = Scanner()
        scan_result = scanner.scan_sharepoint(site_id, drive_id)

        summary = labeler.apply_from_scan(scan_result, dry_run=True)
        print(f"Would label {summary.labeled} files")

        # Actually apply
        summary = labeler.apply_from_scan(scan_result, dry_run=False)
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
    ):
        """
        Initialize labeler with Microsoft credentials.

        Args:
            tenant_id: Azure AD tenant ID
            client_id: Azure AD application ID
            client_secret: Application client secret
        """
        self.client = GraphClient(tenant_id, client_id, client_secret)
        self.mapping = LabelMapping()
        self._labels_cache: Optional[list[dict]] = None

    def test_connection(self) -> bool:
        """Test if credentials are valid."""
        return self.client.test_connection()

    def get_labels(self, refresh: bool = False) -> list[dict]:
        """
        Get available sensitivity labels from tenant.

        Args:
            refresh: Force refresh from API

        Returns:
            List of label objects with id, name, description
        """
        if self._labels_cache is None or refresh:
            self._labels_cache = self.client.get_sensitivity_labels()
        return self._labels_cache

    def auto_map_labels(self) -> LabelMapping:
        """
        Automatically map recommendations to labels by name.

        Looks for labels named "Highly Confidential", "Confidential", etc.

        Returns:
            The configured LabelMapping
        """
        return self.mapping.load_from_tenant(self.client)

    def resolve_label_id(self, label: str) -> Optional[str]:
        """
        Resolve a label name or ID to an ID.

        Args:
            label: Label name, ID (GUID), or recommendation value

        Returns:
            Label ID (GUID) or None if not found
        """
        # If it looks like a GUID, return as-is
        if len(label) == 36 and label.count("-") == 4:
            return label

        # Check mapping first
        for rec in LabelRecommendation:
            if rec.value == label.lower():
                mapped = self.mapping.get(rec)
                if mapped:
                    return mapped

        # Check against available labels by name
        labels = self.get_labels()
        for lbl in labels:
            if lbl.get("name", "").lower() == label.lower():
                return lbl.get("id")

        return None

    def apply_label(
        self,
        site_id: str,
        drive_id: str,
        item_id: str,
        label_id: str,
        dry_run: bool = True,
        justification: str = "Applied by scrubIQ",
    ) -> LabelResult:
        """
        Apply a sensitivity label to a single file.

        Args:
            site_id: SharePoint site ID
            drive_id: Document library ID
            item_id: File item ID
            label_id: Sensitivity label GUID
            dry_run: If True, don't actually apply
            justification: Reason for labeling

        Returns:
            LabelResult with operation details
        """
        result = LabelResult(
            path=f"{site_id}/{drive_id}/{item_id}",
            site_id=site_id,
            drive_id=drive_id,
            item_id=item_id,
            new_label=label_id,
            dry_run=dry_run,
        )

        try:
            # Get current label
            current = self.client.get_file_label(site_id, drive_id, item_id)
            if current:
                result.previous_label = current.get("sensitivityLabelId")
                result.previous_label_name = current.get("name")

            if dry_run:
                result.success = True
                result.error = "DRY RUN - no changes made"
            else:
                self.client.apply_label(site_id, drive_id, item_id, label_id, justification)
                result.success = True

        except GraphAPIError as e:
            result.success = False
            result.error = str(e)
            logger.error(f"Failed to label {item_id}: {e}")

        return result

    def apply_from_scan(
        self,
        scan_result: ScanResult,
        dry_run: bool = True,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        on_file: Optional[Callable[[LabelResult], None]] = None,
        skip_already_labeled: bool = True,
        skip_no_recommendation: bool = True,
    ) -> LabelSummary:
        """
        Apply labels based on scan results.

        Args:
            scan_result: Results from Scanner
            dry_run: If True, don't actually apply (DEFAULT!)
            on_progress: Callback(current, total, path)
            on_file: Callback(LabelResult) after each file
            skip_already_labeled: Skip files that already have labels
            skip_no_recommendation: Skip files without recommendations

        Returns:
            LabelSummary with all results
        """
        summary = LabelSummary(dry_run=dry_run)

        # Filter to files that need labeling
        files_to_label = []
        for f in scan_result.files:
            if not f.has_sensitive_data:
                continue
            if skip_no_recommendation and not f.label_recommendation:
                continue
            files_to_label.append(f)

        summary.total_files = len(files_to_label)

        for i, file_result in enumerate(files_to_label):
            if on_progress:
                on_progress(i + 1, summary.total_files, str(file_result.path))

            result = self._label_file(
                file_result,
                dry_run=dry_run,
                skip_already_labeled=skip_already_labeled,
            )

            summary.results.append(result)

            if result.skipped:
                summary.skipped += 1
            elif result.success:
                summary.labeled += 1
                label_name = result.new_label_name or result.recommendation or "unknown"
                summary.by_label[label_name] = summary.by_label.get(label_name, 0) + 1
            else:
                summary.errors += 1

            if on_file:
                on_file(result)

        summary.completed_at = datetime.now()
        return summary

    def _label_file(
        self,
        file_result: FileResult,
        dry_run: bool,
        skip_already_labeled: bool,
    ) -> LabelResult:
        """Label a single file from scan results."""

        result = LabelResult(
            path=str(file_result.path),
            recommendation=(
                file_result.label_recommendation.value if file_result.label_recommendation else None
            ),
            dry_run=dry_run,
        )

        # Check for SharePoint metadata
        # The FileResult needs site_id, drive_id, item_id to apply labels
        # These would be set when scanning SharePoint (not local files)
        site_id = getattr(file_result, "site_id", None)
        drive_id = getattr(file_result, "drive_id", None)
        item_id = getattr(file_result, "item_id", None)

        if not all([site_id, drive_id, item_id]):
            result.skipped = True
            result.skip_reason = "Not a SharePoint file (missing site/drive/item IDs)"
            return result

        result.site_id = site_id
        result.drive_id = drive_id
        result.item_id = item_id

        # Resolve label ID
        if not file_result.label_recommendation:
            result.skipped = True
            result.skip_reason = "No label recommendation"
            return result

        label_id = self.mapping.get(file_result.label_recommendation)
        if not label_id:
            # Try to resolve by name
            label_id = self.resolve_label_id(file_result.label_recommendation.value)

        if not label_id:
            result.success = False
            result.error = f"Could not resolve label for: {file_result.label_recommendation.value}"
            return result

        result.new_label = label_id

        # Get current label name for reporting
        labels = self.get_labels()
        for lbl in labels:
            if lbl.get("id") == label_id:
                result.new_label_name = lbl.get("name")
                break

        try:
            # Check current label
            current = self.client.get_file_label(site_id, drive_id, item_id)
            if current:
                result.previous_label = current.get("sensitivityLabelId")
                result.previous_label_name = current.get("name")

                if skip_already_labeled:
                    result.skipped = True
                    result.skip_reason = f"Already labeled: {result.previous_label_name}"
                    return result

            if dry_run:
                result.success = True
                result.error = "DRY RUN - no changes made"
            else:
                self.client.apply_label(site_id, drive_id, item_id, label_id)
                result.success = True

        except GraphAPIError as e:
            result.success = False
            result.error = str(e)

        return result

    def label_sharepoint_folder(
        self,
        site_id: str,
        drive_id: str,
        folder_id: str = "root",
        label_id: str = None,
        label_name: str = None,
        dry_run: bool = True,
        recursive: bool = True,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> LabelSummary:
        """
        Apply a label to all files in a SharePoint folder.

        Args:
            site_id: SharePoint site ID
            drive_id: Document library ID
            folder_id: Folder ID or "root"
            label_id: Label GUID (or use label_name)
            label_name: Label name to resolve
            dry_run: If True, don't actually apply
            recursive: Include subfolders
            on_progress: Progress callback

        Returns:
            LabelSummary with results
        """
        # Resolve label
        if not label_id and label_name:
            label_id = self.resolve_label_id(label_name)

        if not label_id:
            raise ValueError("Must provide label_id or resolvable label_name")

        summary = LabelSummary(dry_run=dry_run)

        # Get files
        if recursive:
            items = list(self.client.list_items_recursive(site_id, drive_id, folder_id))
        else:
            items = [
                i for i in self.client.list_items(site_id, drive_id, folder_id) if not i.is_folder
            ]

        summary.total_files = len(items)

        for i, item in enumerate(items):
            if on_progress:
                on_progress(i + 1, summary.total_files, item.path)

            result = self.apply_label(
                site_id=site_id,
                drive_id=drive_id,
                item_id=item.id,
                label_id=label_id,
                dry_run=dry_run,
            )
            result.path = item.path

            summary.results.append(result)

            if result.success:
                summary.labeled += 1
            elif result.skipped:
                summary.skipped += 1
            else:
                summary.errors += 1

        summary.completed_at = datetime.now()
        return summary

    def close(self):
        """Close connections."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
