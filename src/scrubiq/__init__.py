"""scrubIQ - Find and protect sensitive data."""

__version__ = "0.1.0"

from scrubiq.scanner.results import (
    Confidence,
    EntityType,
    FileResult,
    LabelRecommendation,
    Match,
    ScanResult,
)

__all__ = [
    "Confidence",
    "EntityType",
    "FileResult",
    "LabelRecommendation",
    "Match",
    "ScanResult",
]
