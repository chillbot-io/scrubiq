"""Main scanner - finds sensitive data in files."""

from pathlib import Path
from datetime import datetime
from typing import Iterator, Optional, Callable
import os

from .results import ScanResult, FileResult
from ..classifier.extractors.registry import ExtractorRegistry
from ..classifier.extractors.base import ExtractionError
from ..classifier.pipeline import ClassifierPipeline


# Default directories to skip
DEFAULT_EXCLUDE_PATTERNS = [
    "node_modules",
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    ".env",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    "*.egg-info",
]


class Scanner:
    """
    Main scanner - finds sensitive data in files.

    Walks directories, extracts text from files, and detects
    sensitive data patterns. Results can be stored in encrypted
    database for later review.

    Usage:
        scanner = Scanner()
        results = scanner.scan("./documents")

        for file in results.files:
            if file.has_sensitive_data:
                print(f"{file.path}: {len(file.matches)} matches")

    With progress callback:
        def on_progress(current, total, filename):
            print(f"{current}/{total}: {filename}")

        results = scanner.scan("./docs", on_progress=on_progress)

    Streaming results:
        for file_result in scanner.scan_iter("./docs"):
            process(file_result)
    """

    def __init__(
        self,
        exclude_patterns: Optional[list[str]] = None,
        max_file_size_mb: int = 100,
        enable_presidio: bool = True,
        presidio_threshold: float = 0.5,
    ):
        """
        Initialize scanner.

        Args:
            exclude_patterns: Directory/file patterns to skip.
            max_file_size_mb: Maximum file size to scan (default 100MB).
            enable_presidio: Use Presidio NER for names/addresses (if available).
            presidio_threshold: Minimum confidence for Presidio matches.
        """
        self.extractor_registry = ExtractorRegistry()
        self.classifier = ClassifierPipeline(
            enable_presidio=enable_presidio,
            presidio_threshold=presidio_threshold,
        )
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self.exclude_patterns = exclude_patterns or DEFAULT_EXCLUDE_PATTERNS

    def scan(
        self,
        path: str,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        on_file: Optional[Callable[[FileResult], None]] = None,
    ) -> ScanResult:
        """
        Scan a directory for sensitive data.

        Args:
            path: Directory or file path to scan.
            on_progress: Callback(current, total, filename) for progress.
            on_file: Callback(FileResult) after each file completes.

        Returns:
            ScanResult with all findings.
        """
        path_obj = Path(path).resolve()
        result = ScanResult(source_path=str(path_obj), source_type="filesystem")

        # Collect files first to know total count
        files = list(self._iter_files(path_obj))
        total = len(files)

        for i, file_path in enumerate(files):
            if on_progress:
                on_progress(i + 1, total, str(file_path))

            file_result = self.scan_file(file_path)
            result.add_file(file_result)

            if on_file:
                on_file(file_result)

        result.complete()
        return result

    def scan_file(self, path: Path) -> FileResult:
        """
        Scan a single file for sensitive data.

        Args:
            path: Path to the file.

        Returns:
            FileResult with matches (if any) or error.
        """
        start_time = datetime.now()

        # Get file metadata
        try:
            stat = path.stat()
            size = stat.st_size
            modified = datetime.fromtimestamp(stat.st_mtime)
        except OSError as e:
            return FileResult(
                path=path,
                source="filesystem",
                size_bytes=0,
                modified=datetime.now(),
                error=f"Cannot access file: {e}",
            )

        # Check size limit
        if size > self.max_file_size:
            return FileResult(
                path=path,
                source="filesystem",
                size_bytes=size,
                modified=modified,
                error=f"File too large ({size / 1024 / 1024:.1f} MB > {self.max_file_size / 1024 / 1024:.0f} MB limit)",
            )

        # Check if we can extract this file type
        if not self.extractor_registry.can_extract(path):
            return FileResult(
                path=path,
                source="filesystem",
                size_bytes=size,
                modified=modified,
                error=f"Unsupported file type: {path.suffix or '(no extension)'}",
            )

        # Extract text
        try:
            text = self.extractor_registry.extract(path)
        except ExtractionError as e:
            return FileResult(
                path=path,
                source="filesystem",
                size_bytes=size,
                modified=modified,
                error=str(e),
            )
        except Exception as e:
            return FileResult(
                path=path,
                source="filesystem",
                size_bytes=size,
                modified=modified,
                error=f"Extraction failed: {type(e).__name__}: {e}",
            )

        # Skip empty files
        if not text or not text.strip():
            return FileResult(
                path=path,
                source="filesystem",
                size_bytes=size,
                modified=modified,
                matches=[],
                scan_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
            )

        # Detect sensitive data
        try:
            result = self.classifier.classify(text, filename=path.name)
            matches = result.matches
        except Exception as e:
            return FileResult(
                path=path,
                source="filesystem",
                size_bytes=size,
                modified=modified,
                error=f"Detection failed: {type(e).__name__}: {e}",
            )

        # Calculate scan time
        scan_time = int((datetime.now() - start_time).total_seconds() * 1000)

        # Use pipeline's label recommendation
        label = result.label_recommendation

        return FileResult(
            path=path,
            source="filesystem",
            size_bytes=size,
            modified=modified,
            matches=matches,
            label_recommendation=label,
            scan_time_ms=scan_time,
        )

    def scan_iter(self, path: str) -> Iterator[FileResult]:
        """
        Yield file results as they're scanned.

        Useful for streaming/real-time progress without
        loading all results into memory.

        Args:
            path: Directory or file path to scan.

        Yields:
            FileResult for each scanned file.
        """
        path_obj = Path(path).resolve()
        for file_path in self._iter_files(path_obj):
            yield self.scan_file(file_path)

    def _iter_files(self, path: Path) -> Iterator[Path]:
        """
        Iterate over all scannable files in a directory.

        Skips excluded patterns and unsupported file types.
        """
        # Handle single file
        if path.is_file():
            yield path
            return

        # Handle directory
        if not path.is_dir():
            return

        for root, dirs, files in os.walk(path):
            # Filter out excluded directories (modifies dirs in-place)
            dirs[:] = [d for d in dirs if not self._should_exclude(d)]

            for filename in files:
                # Skip excluded files
                if self._should_exclude(filename):
                    continue

                file_path = Path(root) / filename

                # Only yield files we can extract
                if self.extractor_registry.can_extract(file_path):
                    yield file_path

    def _should_exclude(self, name: str) -> bool:
        """Check if a file/directory should be excluded."""
        for pattern in self.exclude_patterns:
            if pattern.startswith("*"):
                # Glob-style suffix match
                if name.endswith(pattern[1:]):
                    return True
            elif pattern in name:
                return True
        return False

    @property
    def supported_extensions(self) -> list[str]:
        """List of file extensions this scanner can process."""
        return self.extractor_registry.supported_extensions
