"""Plain text file extraction."""

from pathlib import Path

from .base import Extractor, ExtractionError


class TextExtractor(Extractor):
    """Extract text from plain text files."""

    @property
    def extensions(self) -> list[str]:
        return [
            # Text
            ".txt",
            ".text",
            ".log",
            ".md",
            ".markdown",
            ".rst",
            # Data
            ".csv",
            ".tsv",
            ".json",
            ".jsonl",
            ".yaml",
            ".yml",
            ".xml",
            ".html",
            ".htm",
            # Code
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".cs",
            ".go",
            ".rs",
            ".rb",
            ".php",
            ".sql",
            ".sh",
            ".bash",
            ".ps1",
            ".bat",
            ".cmd",
            # Config
            ".ini",
            ".cfg",
            ".conf",
            ".config",
            ".env",
            ".properties",
            ".toml",
        ]

    def extract(self, path: Path) -> str:
        """Extract text with encoding fallback."""
        try:
            # Try UTF-8 first (most common)
            try:
                return path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                pass

            # Try UTF-8 with BOM
            try:
                return path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                pass

            # Fall back to latin-1 (never fails, but may mangle non-latin chars)
            return path.read_text(encoding="latin-1")

        except Exception as e:
            raise ExtractionError(f"Failed to read {path}: {e}")
