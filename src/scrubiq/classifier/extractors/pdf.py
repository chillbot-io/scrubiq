"""PDF document extraction."""

from pathlib import Path

from .base import Extractor, ExtractionError

try:
    from pypdf import PdfReader

    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


class PdfExtractor(Extractor):
    """Extract text from PDF documents."""

    @property
    def extensions(self) -> list[str]:
        return [".pdf"]

    def extract(self, path: Path) -> str:
        """Extract text from all pages."""
        if not HAS_PYPDF:
            raise ExtractionError("pypdf not installed. Run: pip install pypdf")

        try:
            reader = PdfReader(path)
            text_parts = []

            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text and text.strip():
                    text_parts.append(f"[Page {i + 1}]")
                    text_parts.append(text)

            return "\n".join(text_parts)

        except Exception as e:
            raise ExtractionError(f"Failed to extract from {path}: {e}")
