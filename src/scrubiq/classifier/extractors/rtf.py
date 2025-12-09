"""Rich Text Format (.rtf) extraction."""

from pathlib import Path

from .base import Extractor, ExtractionError

try:
    from striprtf.striprtf import rtf_to_text

    HAS_STRIPRTF = True
except ImportError:
    HAS_STRIPRTF = False


class RtfExtractor(Extractor):
    """Extract text from RTF files."""

    @property
    def extensions(self) -> list[str]:
        return [".rtf"]

    def extract(self, path: Path) -> str:
        """Strip RTF formatting and return plain text."""
        if not HAS_STRIPRTF:
            raise ExtractionError("striprtf not installed. Run: pip install striprtf")

        try:
            # Read raw RTF content
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="latin-1")

            # Strip RTF formatting
            text = rtf_to_text(content)
            return text

        except Exception as e:
            raise ExtractionError(f"Failed to extract from {path}: {e}")
