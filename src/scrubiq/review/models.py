"""Data models for human review system."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Verdict(Enum):
    """Human verdict on a detection."""

    CORRECT = "TP"  # True positive - detector was right
    WRONG = "FP"  # False positive - detector was wrong
    SKIP = "skip"  # Reviewer unsure or skipped


@dataclass
class ReviewSample:
    """A single sample for human review."""

    # Identity
    id: int  # Database match ID
    scan_id: str

    # The match being reviewed
    entity_type: str  # e.g., "ssn", "email"
    value: str  # Real value (for display only)
    value_redacted: str  # For safe display
    confidence: float  # 0.0 - 1.0
    detector: str  # "regex", "presidio"

    # Context
    context: str  # Surrounding text with match
    file_path: str  # Source file
    file_type: str  # Extension

    # After review
    verdict: Optional[Verdict] = None
    reviewed_at: Optional[datetime] = None

    @property
    def confidence_pct(self) -> int:
        """Confidence as percentage."""
        return int(self.confidence * 100)

    def anonymize_context(self) -> str:
        """
        Replace the actual value with a token for training data.

        "Employee SSN: 123-45-6789 on file"
        becomes
        "Employee SSN: [SSN] on file"
        """
        token = f"[{self.entity_type.upper()}]"
        return self.context.replace(self.value, token)

    def to_training_dict(self) -> dict:
        """
        Convert to training-ready format.

        This is what gets written to reviews.jsonl.
        Values are anonymized - no PII in training data.
        """
        return {
            "entity_type": self.entity_type,
            "context": self.anonymize_context(),
            "confidence": self.confidence,
            "detector": self.detector,
            "verdict": self.verdict.value if self.verdict else None,
            "file_type": self.file_type,
            "timestamp": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }
