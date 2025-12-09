"""Core data models for scan results."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
import uuid


class EntityType(Enum):
    """Types of sensitive data we detect."""

    # PII
    SSN = "ssn"
    NAME = "name"
    EMAIL = "email"
    PHONE = "phone"
    ADDRESS = "address"
    DOB = "date_of_birth"

    # PHI
    MRN = "medical_record_number"
    HEALTH_PLAN_ID = "health_plan_id"
    DIAGNOSIS = "diagnosis"
    MEDICATION = "medication"

    # PCI
    CREDIT_CARD = "credit_card"
    CVV = "cvv"
    EXPIRATION = "expiration_date"

    # Secrets
    API_KEY = "api_key"
    PASSWORD = "password"
    PRIVATE_KEY = "private_key"


class Confidence(Enum):
    """Confidence levels for matches."""

    LOW = "low"  # 50-70%
    MEDIUM = "medium"  # 70-85%
    HIGH = "high"  # 85-95%
    VERY_HIGH = "very_high"  # 95%+

    @classmethod
    def from_score(cls, score: float) -> "Confidence":
        if score >= 0.95:
            return cls.VERY_HIGH
        elif score >= 0.85:
            return cls.HIGH
        elif score >= 0.70:
            return cls.MEDIUM
        else:
            return cls.LOW


class LabelRecommendation(Enum):
    """Microsoft sensitivity label recommendations."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    HIGHLY_CONFIDENTIAL = "highly_confidential"


@dataclass
class Match:
    """A single detected sensitive data match."""

    entity_type: EntityType
    value: str  # The matched text (redact in reports!)
    start: int  # Character offset in extracted text
    end: int
    confidence: float  # 0.0 - 1.0
    detector: str  # Which detector found it ("regex", "presidio", "setfit")
    context: str = ""  # Surrounding text for review
    is_test_data: bool = False  # Detected as test/example data
    model_version: Optional[str] = None  # For trained model traceability

    @property
    def confidence_level(self) -> Confidence:
        return Confidence.from_score(self.confidence)

    @property
    def redacted_value(self) -> str:
        """Return value with middle characters redacted."""
        if len(self.value) <= 4:
            return "*" * len(self.value)
        return self.value[:2] + "*" * (len(self.value) - 4) + self.value[-2:]


@dataclass
class FileResult:
    """Results for a single scanned file."""

    path: Path
    source: str  # "filesystem", "sharepoint", "onedrive"
    size_bytes: int
    modified: datetime
    matches: list[Match] = field(default_factory=list)
    label_recommendation: Optional[LabelRecommendation] = None
    current_label: Optional[str] = None
    error: Optional[str] = None  # If extraction/scan failed
    scan_time_ms: int = 0

    @property
    def has_sensitive_data(self) -> bool:
        return len(self.matches) > 0 and not all(m.is_test_data for m in self.matches)

    @property
    def highest_confidence(self) -> float:
        if not self.matches:
            return 0.0
        return max(m.confidence for m in self.matches)

    @property
    def entity_types_found(self) -> set[EntityType]:
        return {m.entity_type for m in self.matches}

    @property
    def real_matches(self) -> list[Match]:
        """Matches excluding test data."""
        return [m for m in self.matches if not m.is_test_data]


@dataclass
class ScanResult:
    """Complete results from a scan operation."""

    scan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    source_path: str = ""
    source_type: str = ""

    files: list[FileResult] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def files_with_matches(self) -> int:
        return sum(1 for f in self.files if f.has_sensitive_data)

    @property
    def files_errored(self) -> int:
        return sum(1 for f in self.files if f.error)

    @property
    def total_matches(self) -> int:
        return sum(len(f.real_matches) for f in self.files)

    def add_file(self, result: FileResult):
        self.files.append(result)

    def complete(self):
        self.completed_at = datetime.now()

    def to_dict(self) -> dict:
        """Serialize for JSON export."""
        return {
            "scan_id": self.scan_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "source_path": self.source_path,
            "source_type": self.source_type,
            "summary": {
                "total_files": self.total_files,
                "files_with_matches": self.files_with_matches,
                "files_errored": self.files_errored,
                "total_matches": self.total_matches,
            },
            "files": [
                {
                    "path": str(f.path),
                    "size_bytes": f.size_bytes,
                    "modified": f.modified.isoformat(),
                    "has_sensitive_data": f.has_sensitive_data,
                    "label_recommendation": (
                        f.label_recommendation.value if f.label_recommendation else None
                    ),
                    "error": f.error,
                    "matches": [
                        {
                            "entity_type": m.entity_type.value,
                            "value": m.redacted_value,
                            "confidence": m.confidence,
                            "confidence_level": m.confidence_level.value,
                            "detector": m.detector,
                            "is_test_data": m.is_test_data,
                            "model_version": m.model_version,
                        }
                        for m in f.matches
                    ],
                }
                for f in self.files
            ],
        }
