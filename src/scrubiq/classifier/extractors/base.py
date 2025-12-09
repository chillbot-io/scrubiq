"""Base extractor interface."""

from abc import ABC, abstractmethod
from pathlib import Path


class ExtractionError(Exception):
    """Failed to extract text from file."""

    pass


class Extractor(ABC):
    """Base class for text extractors."""

    @property
    @abstractmethod
    def extensions(self) -> list[str]:
        """File extensions this extractor handles (lowercase, with dot)."""
        pass

    @abstractmethod
    def extract(self, path: Path) -> str:
        """
        Extract text from file.

        Args:
            path: Path to file to extract.

        Returns:
            Extracted text content.

        Raises:
            ExtractionError: If extraction fails.
        """
        pass

    def can_handle(self, path: Path) -> bool:
        """Check if this extractor can handle the file."""
        suffix = path.suffix.lower()

        # Handle hidden files like .env, .gitignore (no suffix, name starts with dot)
        if not suffix and path.name.startswith("."):
            suffix = path.name.lower()  # Use whole name as "extension"

        return suffix in self.extensions
