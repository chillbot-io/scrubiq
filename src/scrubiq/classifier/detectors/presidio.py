"""Presidio NER-based detector for names, addresses, and other entities."""

from typing import Optional
from ...scanner.results import Match, EntityType

# Optional import - gracefully handle if not installed
try:
    from presidio_analyzer import AnalyzerEngine

    HAS_PRESIDIO = True
except ImportError:
    HAS_PRESIDIO = False
    AnalyzerEngine = None


# Map Presidio entity types to our EntityType enum
PRESIDIO_ENTITY_MAP = {
    # PII
    "PERSON": EntityType.NAME,
    "EMAIL_ADDRESS": EntityType.EMAIL,
    "PHONE_NUMBER": EntityType.PHONE,
    "US_SSN": EntityType.SSN,
    "CREDIT_CARD": EntityType.CREDIT_CARD,
    "LOCATION": EntityType.ADDRESS,
    "DATE_TIME": EntityType.DOB,
    # Additional US-specific
    "US_DRIVER_LICENSE": EntityType.SSN,  # Treat as high-sensitivity PII
    "US_BANK_NUMBER": EntityType.CREDIT_CARD,
    "US_ITIN": EntityType.SSN,
    "US_PASSPORT": EntityType.SSN,
    # Healthcare
    "MEDICAL_LICENSE": EntityType.MRN,
    # Technical
    "IP_ADDRESS": EntityType.API_KEY,
    # Misc
    "NRP": EntityType.NAME,  # Nationality, religion, political group
}


class PresidioDetector:
    """
    Detect sensitive data using Microsoft Presidio NER.

    Presidio uses spaCy NLP models to identify entities like names
    and addresses that regex patterns can't reliably catch.

    Usage:
        if HAS_PRESIDIO:
            detector = PresidioDetector()
            matches = detector.detect("John Smith lives at 123 Main St")

    Note:
        Requires `presidio-analyzer` and a spaCy model to be installed:

            pip install presidio-analyzer
            python -m spacy download en_core_web_lg
    """

    def __init__(
        self,
        score_threshold: float = 0.5,
        entities: Optional[list[str]] = None,
    ):
        """
        Initialize Presidio detector.

        Args:
            score_threshold: Minimum confidence score (0.0-1.0).
            entities: List of Presidio entity types to detect.
                     None means detect all supported types.

        Raises:
            RuntimeError: If presidio-analyzer is not installed.
        """
        if not HAS_PRESIDIO:
            raise RuntimeError(
                "presidio-analyzer not installed. "
                "Install with: pip install presidio-analyzer && "
                "python -m spacy download en_core_web_lg"
            )

        self.score_threshold = score_threshold
        self.entities = entities

        # Initialize analyzer (loads spaCy model)
        self.analyzer = AnalyzerEngine()

    def detect(self, text: str) -> list[Match]:
        """
        Detect sensitive entities in text.

        Args:
            text: Text content to analyze.

        Returns:
            List of Match objects for detected entities.
        """
        # Run Presidio analysis
        results = self.analyzer.analyze(
            text=text,
            language="en",
            entities=self.entities,
            score_threshold=self.score_threshold,
        )

        matches = []
        for result in results:
            # Map Presidio type to our EntityType
            entity_type = PRESIDIO_ENTITY_MAP.get(result.entity_type)
            if not entity_type:
                # Skip unknown entity types
                continue

            # Extract the matched value
            value = text[result.start : result.end]

            # Get surrounding context (50 chars each side)
            ctx_start = max(0, result.start - 50)
            ctx_end = min(len(text), result.end + 50)
            context = text[ctx_start:ctx_end]

            matches.append(
                Match(
                    entity_type=entity_type,
                    value=value,
                    start=result.start,
                    end=result.end,
                    confidence=result.score,
                    detector="presidio",
                    context=context,
                )
            )

        return matches

    @property
    def supported_entities(self) -> list[str]:
        """Get list of Presidio entity types we support."""
        return list(PRESIDIO_ENTITY_MAP.keys())


def is_available() -> bool:
    """Check if Presidio is available."""
    return HAS_PRESIDIO
