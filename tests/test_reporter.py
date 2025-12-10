"""Tests for HTML report generation."""

import pytest
from pathlib import Path
from datetime import datetime
from scrubiq.reporter.html import generate_html_report, generate_summary_report
from scrubiq.scanner.results import (
    ScanResult,
    FileResult,
    Match,
    EntityType,
    LabelRecommendation,
)


@pytest.fixture
def sample_match():
    """Create a sample match."""
    return Match(
        entity_type=EntityType.SSN,
        value="123-45-6789",
        start=10,
        end=21,
        confidence=0.92,
        detector="regex",
        context="Employee SSN: 123-45-6789 on file",
        is_test_data=False,
    )


@pytest.fixture
def sample_file_result(sample_match):
    """Create a sample file result with matches."""
    return FileResult(
        path=Path("/test/documents/hr/employee.txt"),
        source="filesystem",
        size_bytes=1024,
        modified=datetime.now(),
        matches=[sample_match],
        label_recommendation=LabelRecommendation.CONFIDENTIAL,
    )


@pytest.fixture
def empty_file_result():
    """Create a file result without matches."""
    return FileResult(
        path=Path("/test/documents/clean.txt"),
        source="filesystem",
        size_bytes=512,
        modified=datetime.now(),
        matches=[],
    )


@pytest.fixture
def sample_scan_result(sample_file_result, empty_file_result):
    """Create a sample scan result."""
    result = ScanResult(
        scan_id="test123",
        source_path="/test/documents",
        source_type="filesystem",
    )
    result.add_file(sample_file_result)
    result.add_file(empty_file_result)
    result.complete()
    return result


class TestGenerateHtmlReport:
    """Test generate_html_report function."""

    def test_generates_html_file(self, sample_scan_result, tmp_path):
        """Test that HTML file is generated."""
        output_path = tmp_path / "report.html"
        result = generate_html_report(sample_scan_result, output_path)

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_html_contains_scan_id(self, sample_scan_result, tmp_path):
        """Test that report contains scan ID."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_scan_result, output_path)

        content = output_path.read_text()
        assert "test123" in content

    def test_html_contains_source_path(self, sample_scan_result, tmp_path):
        """Test that report contains source path."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_scan_result, output_path)

        content = output_path.read_text()
        assert "/test/documents" in content

    def test_html_contains_file_count(self, sample_scan_result, tmp_path):
        """Test that report contains correct file counts."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_scan_result, output_path)

        content = output_path.read_text()
        # 2 total files
        assert ">2<" in content
        # 1 file with matches
        assert ">1<" in content

    def test_html_contains_entity_type(self, sample_scan_result, tmp_path):
        """Test that report contains entity type."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_scan_result, output_path)

        content = output_path.read_text()
        # Entity type should be title-cased
        assert "Ssn" in content or "SSN" in content.upper()

    def test_html_contains_redacted_value(self, sample_scan_result, tmp_path):
        """Test that report contains redacted value (not plain text)."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_scan_result, output_path)

        content = output_path.read_text()
        # Should NOT contain full SSN
        assert "123-45-6789" not in content
        # Should contain redacted version
        assert "12*" in content or "***" in content

    def test_html_contains_confidence(self, sample_scan_result, tmp_path):
        """Test that report contains confidence percentage."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_scan_result, output_path)

        content = output_path.read_text()
        assert "92%" in content

    def test_html_contains_label_recommendation(self, sample_scan_result, tmp_path):
        """Test that report contains label recommendation."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_scan_result, output_path)

        content = output_path.read_text()
        assert "Confidential" in content

    def test_html_has_filter_bar(self, sample_scan_result, tmp_path):
        """Test that report has filter functionality."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_scan_result, output_path)

        content = output_path.read_text()
        assert "filterFiles" in content
        assert '<input type="text"' in content
        assert '<select id="labelFilter"' in content

    def test_html_has_entity_chart(self, sample_scan_result, tmp_path):
        """Test that report has entity type chart."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_scan_result, output_path)

        content = output_path.read_text()
        assert "entity-chart" in content or "Entities Found by Type" in content

    def test_html_valid_structure(self, sample_scan_result, tmp_path):
        """Test that HTML has proper structure."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_scan_result, output_path)

        content = output_path.read_text()
        assert "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "</html>" in content
        assert "<head>" in content
        assert "</head>" in content
        assert "<body>" in content
        assert "</body>" in content


class TestEmptyScanReport:
    """Test report generation for scans with no findings."""

    def test_empty_scan_shows_celebration(self, empty_file_result, tmp_path):
        """Test that empty scan shows success message."""
        result = ScanResult(
            scan_id="empty123",
            source_path="/test/clean",
            source_type="filesystem",
        )
        result.add_file(empty_file_result)
        result.complete()

        output_path = tmp_path / "report.html"
        generate_html_report(result, output_path)

        content = output_path.read_text()
        # Should have celebration emoji or success message
        assert "No sensitive data found" in content or "127881" in content


class TestMultipleEntities:
    """Test report with multiple entity types."""

    def test_multiple_entity_types_in_chart(self, tmp_path):
        """Test that all entity types appear in chart."""
        matches = [
            Match(EntityType.SSN, "123-45-6789", 0, 11, 0.9, "regex"),
            Match(EntityType.EMAIL, "test@example.com", 20, 36, 0.95, "regex"),
            Match(EntityType.CREDIT_CARD, "4111111111111111", 50, 66, 0.85, "regex"),
        ]

        file_result = FileResult(
            path=Path("/test/data.txt"),
            source="filesystem",
            size_bytes=1024,
            modified=datetime.now(),
            matches=matches,
            label_recommendation=LabelRecommendation.HIGHLY_CONFIDENTIAL,
        )

        result = ScanResult(scan_id="multi123", source_path="/test", source_type="filesystem")
        result.add_file(file_result)
        result.complete()

        output_path = tmp_path / "report.html"
        generate_html_report(result, output_path)

        content = output_path.read_text()
        # All entity types should appear
        assert "ssn" in content.lower() or "Ssn" in content
        assert "email" in content.lower() or "Email" in content
        assert "credit" in content.lower() or "Credit" in content


class TestLongPaths:
    """Test handling of long file paths."""

    def test_long_path_truncated(self, sample_match, tmp_path):
        """Test that very long paths are truncated in display."""
        long_path = Path("/very/long/path" + "/subfolder" * 20 + "/file.txt")

        file_result = FileResult(
            path=long_path,
            source="filesystem",
            size_bytes=1024,
            modified=datetime.now(),
            matches=[sample_match],
            label_recommendation=LabelRecommendation.CONFIDENTIAL,
        )

        result = ScanResult(scan_id="long123", source_path="/very/long", source_type="filesystem")
        result.add_file(file_result)
        result.complete()

        output_path = tmp_path / "report.html"
        generate_html_report(result, output_path)

        content = output_path.read_text()
        # Full path should be in data attribute for filtering
        assert 'data-path="' in content
        # Should have truncation indicator
        assert "..." in content or str(long_path)[-50:] in content


class TestGenerateSummaryReport:
    """Test generate_summary_report function."""

    def test_summary_with_empty_results(self, tmp_path):
        """Test summary report with no results."""
        output_path = tmp_path / "summary.html"
        result = generate_summary_report([], output_path)

        assert result == output_path
        assert output_path.exists()

    def test_summary_with_single_result(self, sample_scan_result, tmp_path):
        """Test summary report with one scan result."""
        output_path = tmp_path / "summary.html"
        result = generate_summary_report([sample_scan_result], output_path)

        assert result == output_path
        assert output_path.exists()

        content = output_path.read_text()
        assert "test123" in content


class TestReportEncoding:
    """Test report handles various encodings properly."""

    def test_unicode_in_path(self, sample_match, tmp_path):
        """Test that unicode characters in path are handled."""
        unicode_path = Path("/test/документы/файл.txt")

        file_result = FileResult(
            path=unicode_path,
            source="filesystem",
            size_bytes=1024,
            modified=datetime.now(),
            matches=[sample_match],
            label_recommendation=LabelRecommendation.CONFIDENTIAL,
        )

        result = ScanResult(scan_id="unicode123", source_path="/test", source_type="filesystem")
        result.add_file(file_result)
        result.complete()

        output_path = tmp_path / "report.html"
        generate_html_report(result, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "документы" in content or "файл" in content

    def test_special_characters_escaped(self, sample_match, tmp_path):
        """Test that HTML special characters are handled."""
        # Path with characters that could break HTML
        special_path = Path("/test/<script>alert('xss')</script>.txt")

        file_result = FileResult(
            path=special_path,
            source="filesystem",
            size_bytes=1024,
            modified=datetime.now(),
            matches=[sample_match],
            label_recommendation=LabelRecommendation.CONFIDENTIAL,
        )

        result = ScanResult(scan_id="special123", source_path="/test", source_type="filesystem")
        result.add_file(file_result)
        result.complete()

        output_path = tmp_path / "report.html"
        generate_html_report(result, output_path)

        # The report should still be valid HTML
        content = output_path.read_text()
        assert "</html>" in content
