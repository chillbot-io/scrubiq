"""Tests for sensitivity label application."""

import pytest
from unittest.mock import patch
from datetime import datetime
from pathlib import Path

from scrubiq.labeler.labeler import (
    Labeler,
    LabelMapping,
    LabelResult,
    LabelSummary,
)
from scrubiq.scanner.results import (
    ScanResult,
    FileResult,
    Match,
    EntityType,
    LabelRecommendation,
)


class TestLabelMapping:
    """Tests for LabelMapping."""

    def test_set_and_get(self):
        """Test setting and getting mappings."""
        mapping = LabelMapping()
        mapping.set("confidential", "guid-123")

        assert mapping.get(LabelRecommendation.CONFIDENTIAL) == "guid-123"

    def test_case_insensitive(self):
        """Test case-insensitive lookup."""
        mapping = LabelMapping()
        mapping.set("CONFIDENTIAL", "guid-123")

        assert mapping.get(LabelRecommendation.CONFIDENTIAL) == "guid-123"

    def test_from_dict(self):
        """Test loading from dictionary."""
        mapping = LabelMapping().from_dict(
            {
                "highly_confidential": "guid-1",
                "confidential": "guid-2",
                "internal": "guid-3",
            }
        )

        assert mapping.get(LabelRecommendation.HIGHLY_CONFIDENTIAL) == "guid-1"
        assert mapping.get(LabelRecommendation.CONFIDENTIAL) == "guid-2"
        assert mapping.get(LabelRecommendation.INTERNAL) == "guid-3"

    def test_get_nonexistent(self):
        """Test getting mapping that doesn't exist."""
        mapping = LabelMapping()

        assert mapping.get(LabelRecommendation.PUBLIC) is None

    def test_configured_recommendations(self):
        """Test listing configured recommendations."""
        mapping = LabelMapping().from_dict(
            {
                "confidential": "guid-1",
                "internal": "guid-2",
            }
        )

        configured = mapping.configured_recommendations
        assert "confidential" in configured
        assert "internal" in configured
        assert len(configured) == 2


class TestLabelResult:
    """Tests for LabelResult."""

    def test_default_values(self):
        """Test default values."""
        result = LabelResult(path="/path/to/file.docx")

        assert result.path == "/path/to/file.docx"
        assert result.success is False
        assert result.dry_run is True
        assert result.error is None

    def test_successful_label(self):
        """Test successful labeling result."""
        result = LabelResult(
            path="/path/to/file.docx",
            site_id="site123",
            drive_id="drive456",
            item_id="item789",
            success=True,
            dry_run=False,
            previous_label=None,
            new_label="guid-confidential",
            new_label_name="Confidential",
        )

        assert result.success is True
        assert result.dry_run is False
        assert result.new_label_name == "Confidential"


class TestLabelSummary:
    """Tests for LabelSummary."""

    def test_default_values(self):
        """Test default values."""
        summary = LabelSummary()

        assert summary.total_files == 0
        assert summary.labeled == 0
        assert summary.skipped == 0
        assert summary.errors == 0
        assert summary.dry_run is True

    def test_duration_calculation(self):
        """Test duration calculation."""
        summary = LabelSummary()
        summary.started_at = datetime(2024, 1, 15, 10, 0, 0)
        summary.completed_at = datetime(2024, 1, 15, 10, 0, 30)

        assert summary.duration_seconds == 30.0

    def test_duration_incomplete(self):
        """Test duration when not complete."""
        summary = LabelSummary()

        assert summary.duration_seconds == 0.0


class TestLabelerInit:
    """Tests for Labeler initialization."""

    @pytest.fixture
    def mock_labeler(self):
        """Create labeler with mocked Graph client."""
        with patch("scrubiq.labeler.labeler.GraphClient") as mock_graph:
            mock_graph.return_value.get_sensitivity_labels.return_value = [
                {"id": "guid-1", "name": "Highly Confidential"},
                {"id": "guid-2", "name": "Confidential"},
                {"id": "guid-3", "name": "Internal"},
                {"id": "guid-4", "name": "Public"},
            ]

            labeler = Labeler(
                tenant_id="tenant123",
                client_id="client456",
                client_secret="secret789",
            )
            labeler._mock_client = mock_graph.return_value
            yield labeler

    def test_get_labels(self, mock_labeler):
        """Test getting labels."""
        labels = mock_labeler.get_labels()

        assert len(labels) == 4
        assert labels[0]["name"] == "Highly Confidential"

    def test_auto_map_labels(self, mock_labeler):
        """Test automatic label mapping."""
        mock_labeler.auto_map_labels()

        # Should map standard names
        assert mock_labeler.mapping.get(LabelRecommendation.HIGHLY_CONFIDENTIAL) == "guid-1"
        assert mock_labeler.mapping.get(LabelRecommendation.CONFIDENTIAL) == "guid-2"

    def test_resolve_label_id_guid(self, mock_labeler):
        """Test resolving a GUID directly."""
        guid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        resolved = mock_labeler.resolve_label_id(guid)

        assert resolved == guid

    def test_resolve_label_id_by_name(self, mock_labeler):
        """Test resolving by label name."""
        resolved = mock_labeler.resolve_label_id("Confidential")

        assert resolved == "guid-2"

    def test_resolve_label_id_by_recommendation(self, mock_labeler):
        """Test resolving by recommendation value."""
        mock_labeler.auto_map_labels()

        resolved = mock_labeler.resolve_label_id("confidential")

        assert resolved == "guid-2"


class TestLabelerApply:
    """Tests for Labeler.apply_from_scan."""

    @pytest.fixture
    def mock_labeler(self):
        """Create labeler with mocked Graph client."""
        with patch("scrubiq.labeler.labeler.GraphClient") as mock_graph:
            mock_client = mock_graph.return_value
            mock_client.get_sensitivity_labels.return_value = [
                {"id": "guid-1", "name": "Highly Confidential"},
                {"id": "guid-2", "name": "Confidential"},
            ]
            mock_client.get_file_label.return_value = None
            mock_client.apply_label.return_value = {}

            labeler = Labeler(
                tenant_id="tenant123",
                client_id="client456",
                client_secret="secret789",
            )
            labeler._mock_client = mock_client
            yield labeler

    @pytest.fixture
    def sample_scan_result(self):
        """Create a sample scan result."""
        result = ScanResult(
            scan_id="test123",
            source_path="/test/path",
            source_type="filesystem",
        )

        # File with sensitive data (but no SharePoint metadata)
        file1 = FileResult(
            path=Path("/test/document1.docx"),
            source="filesystem",
            size_bytes=1000,
            modified=datetime.now(),
            matches=[
                Match(
                    entity_type=EntityType.SSN,
                    value="078-05-1120",
                    start=10,
                    end=21,
                    confidence=0.92,
                    detector="regex",
                )
            ],
            label_recommendation=LabelRecommendation.HIGHLY_CONFIDENTIAL,
        )

        # Clean file
        file2 = FileResult(
            path=Path("/test/document2.docx"),
            source="filesystem",
            size_bytes=500,
            modified=datetime.now(),
            matches=[],
        )

        result.files = [file1, file2]
        return result

    def test_apply_dry_run_default(self, mock_labeler, sample_scan_result):
        """Test that dry_run is True by default."""
        summary = mock_labeler.apply_from_scan(sample_scan_result)

        assert summary.dry_run is True

    def test_apply_skips_local_files(self, mock_labeler, sample_scan_result):
        """Test that local files are skipped (no SharePoint metadata)."""
        summary = mock_labeler.apply_from_scan(sample_scan_result)

        # Should skip because no site_id/drive_id/item_id
        assert summary.skipped == 1  # The file with sensitive data

        # Check skip reason
        skipped = [r for r in summary.results if r.skipped]
        assert len(skipped) == 1
        assert "SharePoint" in skipped[0].skip_reason

    def test_apply_progress_callback(self, mock_labeler, sample_scan_result):
        """Test progress callback is called."""
        progress_calls = []

        def on_progress(current, total, path):
            progress_calls.append((current, total, path))

        mock_labeler.apply_from_scan(
            sample_scan_result,
            on_progress=on_progress,
        )

        # Should be called for files with recommendations
        assert len(progress_calls) >= 1

    def test_apply_file_callback(self, mock_labeler, sample_scan_result):
        """Test per-file callback is called."""
        file_results = []

        def on_file(result):
            file_results.append(result)

        mock_labeler.apply_from_scan(
            sample_scan_result,
            on_file=on_file,
        )

        assert len(file_results) >= 1


class TestLabelerSharePointFolder:
    """Tests for labeling SharePoint folders."""

    @pytest.fixture
    def mock_labeler(self):
        """Create labeler with mocked Graph client."""
        with patch("scrubiq.labeler.labeler.GraphClient") as mock_graph:
            from scrubiq.auth.graph import DriveItem

            mock_client = mock_graph.return_value
            mock_client.get_sensitivity_labels.return_value = [
                {"id": "guid-conf", "name": "Confidential"},
            ]
            mock_client.list_items_recursive.return_value = [
                DriveItem(
                    id="item1",
                    name="doc1.docx",
                    path="folder/doc1.docx",
                    size=1000,
                    modified=datetime.now(),
                    is_folder=False,
                    site_id="site123",
                    drive_id="drive456",
                ),
                DriveItem(
                    id="item2",
                    name="doc2.xlsx",
                    path="folder/doc2.xlsx",
                    size=2000,
                    modified=datetime.now(),
                    is_folder=False,
                    site_id="site123",
                    drive_id="drive456",
                ),
            ]
            mock_client.get_file_label.return_value = None
            mock_client.apply_label.return_value = {}

            labeler = Labeler("tenant", "client", "secret")
            labeler._mock_client = mock_client
            yield labeler

    def test_label_folder_dry_run(self, mock_labeler):
        """Test labeling folder in dry-run mode."""
        summary = mock_labeler.label_sharepoint_folder(
            site_id="site123",
            drive_id="drive456",
            folder_id="root",
            label_name="Confidential",
            dry_run=True,
        )

        assert summary.total_files == 2
        assert summary.labeled == 2
        assert summary.dry_run is True

        # Verify apply_label was NOT called
        mock_labeler._mock_client.apply_label.assert_not_called()

    def test_label_folder_apply(self, mock_labeler):
        """Test actually applying labels."""
        summary = mock_labeler.label_sharepoint_folder(
            site_id="site123",
            drive_id="drive456",
            folder_id="root",
            label_name="Confidential",
            dry_run=False,
        )

        assert summary.total_files == 2
        assert summary.labeled == 2
        assert summary.dry_run is False

        # Verify apply_label was called for each file
        assert mock_labeler._mock_client.apply_label.call_count == 2

    def test_label_folder_requires_label(self, mock_labeler):
        """Test that label_id or label_name is required."""
        with pytest.raises(ValueError, match="Must provide"):
            mock_labeler.label_sharepoint_folder(
                site_id="site123",
                drive_id="drive456",
            )
