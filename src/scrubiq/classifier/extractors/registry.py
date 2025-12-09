"""Registry of all text extractors."""

from pathlib import Path
from typing import Optional

from .base import Extractor, ExtractionError
from .text import TextExtractor
from .docx import DocxExtractor
from .xlsx import XlsxExtractor
from .pdf import PdfExtractor
from .pptx import PptxExtractor
from .msg import MsgExtractor
from .rtf import RtfExtractor
from .eml import EmlExtractor


class ExtractorRegistry:
    """
    Registry of all text extractors.

    Routes files to the appropriate extractor based on extension.

    Usage:
        registry = ExtractorRegistry()

        # Check if we can handle a file
        if registry.can_extract(Path("document.docx")):
            text = registry.extract(Path("document.docx"))

        # List supported extensions
        print(registry.supported_extensions)
    """

    def __init__(self):
        self.extractors: list[Extractor] = [
            TextExtractor(),
            DocxExtractor(),
            XlsxExtractor(),
            PdfExtractor(),
            PptxExtractor(),
            MsgExtractor(),
            RtfExtractor(),
            EmlExtractor(),
        ]

    def get_extractor(self, path: Path) -> Optional[Extractor]:
        """Find extractor for file type."""
        for extractor in self.extractors:
            if extractor.can_handle(path):
                return extractor
        return None

    def can_extract(self, path: Path) -> bool:
        """Check if we can extract text from this file."""
        return self.get_extractor(path) is not None

    def extract(self, path: Path) -> str:
        """
        Extract text from file.

        Args:
            path: Path to file.

        Returns:
            Extracted text content.

        Raises:
            ExtractionError: If no extractor found or extraction fails.
        """
        extractor = self.get_extractor(path)
        if not extractor:
            raise ExtractionError(f"No extractor for {path.suffix}")
        return extractor.extract(path)

    @property
    def supported_extensions(self) -> list[str]:
        """All supported file extensions."""
        extensions = []
        for extractor in self.extractors:
            extensions.extend(extractor.extensions)
        return sorted(set(extensions))
