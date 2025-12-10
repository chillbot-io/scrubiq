"""Tests for the Scanner class."""

import pytest

from scrubiq import Scanner, ScanResult, FileResult, EntityType, LabelRecommendation


class TestScannerBasics:
    """Test basic scanner operations."""

    @pytest.fixture
    def scanner(self):
        return Scanner()

    @pytest.fixture
    def test_dir(self, tmp_path):
        """Create test directory with sample files."""
        # File with real SSN
        (tmp_path / "with_ssn.txt").write_text("Employee: John Smith\nSSN: 078-05-1120\n")

        # Clean file
        (tmp_path / "clean.txt").write_text("This is a normal document with no sensitive data.")

        # File with test SSN (should be flagged as test data)
        (tmp_path / "test_data.txt").write_text("Example SSN: 123-45-6789")

        # File with credit card
        (tmp_path / "payment.txt").write_text("Card: 4532015112830366")  # Valid Luhn

        # Empty file
        (tmp_path / "empty.txt").write_text("")

        return tmp_path

    def test_scan_directory(self, scanner, test_dir):
        """Should scan all files in directory."""
        result = scanner.scan(str(test_dir))

        assert isinstance(result, ScanResult)
        assert result.total_files == 5
        assert result.completed_at is not None

    def test_scan_detects_ssn(self, scanner, test_dir):
        """Should detect SSN in files."""
        result = scanner.scan(str(test_dir))

        ssn_file = next(f for f in result.files if f.path.name == "with_ssn.txt")

        assert ssn_file.has_sensitive_data
        assert len(ssn_file.matches) == 1
        assert ssn_file.matches[0].entity_type == EntityType.SSN
        assert ssn_file.matches[0].value == "078-05-1120"

    def test_scan_flags_test_data(self, scanner, test_dir):
        """Should flag test/example SSNs as test data."""
        result = scanner.scan(str(test_dir))

        test_file = next(f for f in result.files if f.path.name == "test_data.txt")

        # Has matches but they're test data
        assert len(test_file.matches) == 1
        assert test_file.matches[0].is_test_data
        assert not test_file.has_sensitive_data  # Excluded from real count

    def test_scan_clean_file(self, scanner, test_dir):
        """Should not find matches in clean file."""
        result = scanner.scan(str(test_dir))

        clean_file = next(f for f in result.files if f.path.name == "clean.txt")

        assert not clean_file.has_sensitive_data
        assert len(clean_file.matches) == 0

    def test_scan_single_file(self, scanner, test_dir):
        """Should scan a single file."""
        result = scanner.scan_file(test_dir / "with_ssn.txt")

        assert isinstance(result, FileResult)
        assert result.has_sensitive_data
        assert result.label_recommendation is not None

    def test_scan_result_stats(self, scanner, test_dir):
        """Should compute correct statistics."""
        result = scanner.scan(str(test_dir))

        # with_ssn.txt and payment.txt have real sensitive data
        assert result.files_with_matches == 2
        assert result.total_matches >= 2


class TestScannerProgress:
    """Test progress callbacks."""

    @pytest.fixture
    def scanner(self):
        return Scanner()

    @pytest.fixture
    def test_dir(self, tmp_path):
        for i in range(3):
            (tmp_path / f"file{i}.txt").write_text(f"Content {i}")
        return tmp_path

    def test_progress_callback(self, scanner, test_dir):
        """Should call progress callback for each file."""
        progress_calls = []

        def on_progress(current, total, filename):
            progress_calls.append((current, total, filename))

        scanner.scan(str(test_dir), on_progress=on_progress)

        assert len(progress_calls) == 3
        assert progress_calls[-1][0] == progress_calls[-1][1]  # Last: current == total

    def test_file_callback(self, scanner, test_dir):
        """Should call file callback with FileResult."""
        file_results = []

        def on_file(result):
            file_results.append(result)

        scanner.scan(str(test_dir), on_file=on_file)

        assert len(file_results) == 3
        assert all(isinstance(r, FileResult) for r in file_results)


class TestScannerFiltering:
    """Test file filtering and exclusion."""

    @pytest.fixture
    def scanner(self):
        return Scanner()

    def test_excludes_git_directory(self, scanner, tmp_path):
        """Should skip .git directories."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("git config")
        (tmp_path / "code.py").write_text("# code")

        result = scanner.scan(str(tmp_path))

        paths = [f.path.name for f in result.files]
        assert "config" not in paths
        assert "code.py" in paths

    def test_excludes_node_modules(self, scanner, tmp_path):
        """Should skip node_modules directories."""
        node_dir = tmp_path / "node_modules"
        node_dir.mkdir()
        (node_dir / "package.json").write_text("{}")
        (tmp_path / "app.js").write_text("// app")

        result = scanner.scan(str(tmp_path))

        paths = [f.path.name for f in result.files]
        assert "package.json" not in paths
        assert "app.js" in paths

    def test_excludes_pycache(self, scanner, tmp_path):
        """Should skip __pycache__ directories."""
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "module.pyc").write_text("bytecode")
        (tmp_path / "module.py").write_text("# module")

        result = scanner.scan(str(tmp_path))

        paths = [f.path.name for f in result.files]
        assert "module.pyc" not in paths
        assert "module.py" in paths

    def test_skips_unsupported_extensions(self, scanner, tmp_path):
        """Should skip files with unsupported extensions."""
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        (tmp_path / "data.bin").write_bytes(b"\x00\x01\x02")
        (tmp_path / "doc.txt").write_text("text file")

        result = scanner.scan(str(tmp_path))

        paths = [f.path.name for f in result.files]
        assert "image.png" not in paths
        assert "data.bin" not in paths
        assert "doc.txt" in paths

    def test_custom_exclude_patterns(self, tmp_path):
        """Should respect custom exclude patterns."""
        scanner = Scanner(exclude_patterns=["secret", "*.log"])

        (tmp_path / "secret").mkdir()
        (tmp_path / "secret" / "keys.txt").write_text("keys")
        (tmp_path / "app.log").write_text("log")
        (tmp_path / "readme.txt").write_text("readme")

        result = scanner.scan(str(tmp_path))

        paths = [f.path.name for f in result.files]
        assert "keys.txt" not in paths
        assert "app.log" not in paths
        assert "readme.txt" in paths


class TestScannerLabelRecommendation:
    """Test sensitivity label recommendations."""

    @pytest.fixture
    def scanner(self):
        return Scanner()

    def test_confidential_for_ssn(self, scanner, tmp_path):
        """SSN should be at least CONFIDENTIAL."""
        (tmp_path / "hr.txt").write_text("Employee SSN: 078-05-1120")

        result = scanner.scan_file(tmp_path / "hr.txt")

        # SSN regex confidence is 0.75, so it's CONFIDENTIAL (not HIGHLY)
        # HIGHLY_CONFIDENTIAL requires confidence >= 0.85
        assert result.label_recommendation in [
            LabelRecommendation.CONFIDENTIAL,
            LabelRecommendation.HIGHLY_CONFIDENTIAL,
        ]

    def test_no_label_for_clean_file(self, scanner, tmp_path):
        """Clean files should have no label recommendation."""
        (tmp_path / "clean.txt").write_text("No sensitive data here.")

        result = scanner.scan_file(tmp_path / "clean.txt")

        assert result.label_recommendation is None

    def test_no_label_for_test_data_only(self, scanner, tmp_path):
        """Files with only test data should have no label."""
        (tmp_path / "test.txt").write_text("Test SSN: 123-45-6789")

        result = scanner.scan_file(tmp_path / "test.txt")

        # Has matches but all test data
        assert len(result.matches) == 1
        assert result.matches[0].is_test_data
        assert result.label_recommendation is None


class TestScannerErrors:
    """Test error handling."""

    @pytest.fixture
    def scanner(self):
        return Scanner()

    def test_handles_missing_file(self, scanner, tmp_path):
        """Should handle missing files gracefully."""
        result = scanner.scan_file(tmp_path / "nonexistent.txt")

        assert result.error is not None
        assert "Cannot access" in result.error

    def test_handles_oversized_file(self, tmp_path):
        """Should skip files over size limit."""
        scanner = Scanner(max_file_size_mb=0.001)  # 1KB limit

        # Create 2KB file
        (tmp_path / "big.txt").write_text("x" * 2048)

        result = scanner.scan_file(tmp_path / "big.txt")

        assert result.error is not None
        assert "too large" in result.error


class TestScannerStreaming:
    """Test streaming/iterator interface."""

    @pytest.fixture
    def scanner(self):
        return Scanner()

    @pytest.fixture
    def test_dir(self, tmp_path):
        for i in range(5):
            (tmp_path / f"file{i}.txt").write_text(f"Content {i}")
        return tmp_path

    def test_scan_iter_yields_results(self, scanner, test_dir):
        """scan_iter should yield FileResult objects."""
        results = list(scanner.scan_iter(str(test_dir)))

        assert len(results) == 5
        assert all(isinstance(r, FileResult) for r in results)

    def test_scan_iter_is_lazy(self, scanner, test_dir):
        """scan_iter should be a generator, not loading all at once."""
        gen = scanner.scan_iter(str(test_dir))

        # Should be a generator
        assert hasattr(gen, "__next__")

        # First next() should work
        first = next(gen)
        assert isinstance(first, FileResult)
