"""Sample low-confidence matches for human review."""

from typing import Iterator, Optional
from pathlib import Path

from .models import ReviewSample
from ..storage.database import FindingsDatabase


class ReviewSampler:
    """
    Sample matches from database for human review.

    Focuses on low-confidence matches where human feedback
    is most valuable for training.

    Usage:
        sampler = ReviewSampler(db)
        for sample in sampler.get_samples("abc123", max_confidence=0.85):
            # Show to reviewer
            pass
    """

    def __init__(self, db: FindingsDatabase):
        self.db = db

    def get_samples(
        self,
        scan_id: str,
        max_confidence: float = 0.85,
        limit: Optional[int] = None,
    ) -> Iterator[ReviewSample]:
        """
        Get samples for review from a scan.

        Args:
            scan_id: Scan to review
            max_confidence: Only return matches below this threshold
            limit: Maximum number of samples (None = all)

        Yields:
            ReviewSample objects sorted by confidence (lowest first)
        """
        # Get all findings for this scan, decrypted
        findings = list(
            self.db.get_findings(
                scan_id=scan_id,
                min_confidence=0.0,
                include_test_data=False,
                decrypt=True,
            )
        )

        # Filter by max confidence and sort by confidence ascending
        filtered = [f for f in findings if f["confidence"] < max_confidence]
        filtered.sort(key=lambda f: f["confidence"])

        # Apply limit
        if limit:
            filtered = filtered[:limit]

        # Convert to ReviewSample objects
        for f in filtered:
            yield ReviewSample(
                id=f["id"],
                scan_id=scan_id,
                entity_type=f["entity_type"],
                value=f.get("value", f["value_redacted"]),
                value_redacted=f["value_redacted"],
                confidence=f["confidence"],
                detector=f.get("detector", "unknown"),
                context=f.get("context", ""),
                file_path=f["file_path"],
                file_type=Path(f["file_path"]).suffix,
            )

    def count_reviewable(
        self,
        scan_id: str,
        max_confidence: float = 0.85,
    ) -> int:
        """Count how many matches are below the confidence threshold."""
        findings = list(
            self.db.get_findings(
                scan_id=scan_id,
                min_confidence=0.0,
                include_test_data=False,
                decrypt=False,  # Don't need values for counting
            )
        )

        return sum(1 for f in findings if f["confidence"] < max_confidence)

    def get_scan_summary(self, scan_id: str) -> Optional[dict]:
        """Get scan info for display."""
        return self.db.get_scan(scan_id)
