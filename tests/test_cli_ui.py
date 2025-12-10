"""Tests for CLI UI components."""

import pytest
from datetime import datetime

from scrubiq.cli.ui import ScanUI, ScanStats
from scrubiq.scanner.results import ScanResult, FileResult, Match, EntityType, LabelRecommendation


class TestScanStats:
    """Test ScanStats dataclass."""

    def test_default_values(self):
        stats = ScanStats()

        assert stats.total_files == 0
        assert stats.scanned == 0
        assert stats.with_matches == 0
        assert stats.errors == 0
        assert stats.entity_counts == {}
        assert stats.recent_matches == []

    def test_with_values(self):
        stats = ScanStats(
            total_files=100,
            scanned=50,
            with_matches=10,
            errors=2,
        )

        assert stats.total_files == 100
        assert stats.scanned == 50


class TestScanUI:
    """Test ScanUI class."""

    @pytest.fixture
    def ui(self):
        return ScanUI(quiet=True)  # Quiet mode for testing

    @pytest.fixture
    def sample_file_result(self, tmp_path):
        return FileResult(
            path=tmp_path / "test.txt",
            source="filesystem",
            size_bytes=100,
            modified=datetime.now(),
            matches=[
                Match(
                    entity_type=EntityType.SSN,
                    value="078-05-1120",
                    start=10,
                    end=21,
                    confidence=0.75,
                    detector="regex",
                )
            ],
            label_recommendation=LabelRecommendation.CONFIDENTIAL,
        )

    @pytest.fixture
    def sample_scan_result(self, tmp_path, sample_file_result):
        result = ScanResult(
            source_path=str(tmp_path),
            source_type="filesystem",
        )
        result.add_file(sample_file_result)
        result.complete()
        return result

    def test_start_initializes_stats(self, ui):
        ui.start(total=100, source_path="/test")

        assert ui.stats.total_files == 100
        assert ui.stats.scanned == 0
        assert ui.start_time is not None

    def test_update_increments_scanned(self, ui, sample_file_result):
        ui.start(total=10)
        ui.update(sample_file_result)

        assert ui.stats.scanned == 1

    def test_update_tracks_matches(self, ui, sample_file_result):
        ui.start(total=10)
        ui.update(sample_file_result)

        assert ui.stats.with_matches == 1
        assert "ssn" in ui.stats.entity_counts
        assert ui.stats.entity_counts["ssn"] == 1

    def test_update_tracks_recent_matches(self, ui, sample_file_result):
        ui.start(total=10)
        ui.update(sample_file_result)

        assert len(ui.stats.recent_matches) == 1
        assert ui.stats.recent_matches[0]["file"] == "test.txt"

    def test_update_limits_recent_matches(self, ui, tmp_path):
        ui.start(total=10)

        # Add 5 files with matches
        for i in range(5):
            result = FileResult(
                path=tmp_path / f"file{i}.txt",
                source="filesystem",
                size_bytes=100,
                modified=datetime.now(),
                matches=[
                    Match(
                        entity_type=EntityType.SSN,
                        value="078-05-1120",
                        start=0,
                        end=11,
                        confidence=0.75,
                        detector="regex",
                    )
                ],
            )
            ui.update(result)

        # Should only keep last 3
        assert len(ui.stats.recent_matches) == 3

    def test_update_tracks_errors(self, ui, tmp_path):
        ui.start(total=10)

        error_result = FileResult(
            path=tmp_path / "error.txt",
            source="filesystem",
            size_bytes=0,
            modified=datetime.now(),
            error="File not found",
        )
        ui.update(error_result)

        assert ui.stats.errors == 1
        assert ui.stats.with_matches == 0

    def test_complete_works_in_quiet_mode(self, ui, sample_scan_result):
        ui.start(total=1)
        ui.complete(sample_scan_result)

        # Should not raise any errors
        assert True

    def test_render_summary_with_matches(self, sample_scan_result):
        ui = ScanUI(quiet=False)
        panel = ui._render_summary(sample_scan_result)

        # Panel should be red for findings
        assert panel.border_style == "red"
        assert "Sensitive Data Found" in panel.title

    def test_render_summary_without_matches(self, tmp_path):
        ui = ScanUI(quiet=False)

        # Create clean result
        result = ScanResult(source_path=str(tmp_path), source_type="filesystem")
        result.add_file(
            FileResult(
                path=tmp_path / "clean.txt",
                source="filesystem",
                size_bytes=100,
                modified=datetime.now(),
                matches=[],
            )
        )
        result.complete()

        panel = ui._render_summary(result)

        # Panel should be green for no findings
        assert panel.border_style == "green"
        assert "No Sensitive Data" in panel.title


class TestUIIntegration:
    """Test UI integration with scanner."""

    def test_full_scan_flow(self, tmp_path):
        from scrubiq import Scanner

        # Create test file
        (tmp_path / "test.txt").write_text("SSN: 078-05-1120")

        scanner = Scanner()
        ui = ScanUI(quiet=True)

        files = list(scanner._iter_files(tmp_path))
        ui.start(total=len(files))

        def on_file(result):
            ui.update(result)

        result = scanner.scan(str(tmp_path), on_file=on_file)
        ui.complete(result)

        # Verify stats were tracked
        assert ui.stats.scanned == 1
        assert ui.stats.with_matches == 1
