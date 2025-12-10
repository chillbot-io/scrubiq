"""Storage for review verdicts - feeds into training pipeline."""

import json
import os
from pathlib import Path
from typing import Iterator, Optional

from .models import ReviewSample, Verdict


def get_reviews_path() -> Path:
    """Get path to reviews JSONL file."""
    if os.name == "nt":  # Windows
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    else:  # Unix
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))

    reviews_dir = Path(base) / "scrubiq"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    return reviews_dir / "reviews.jsonl"


class ReviewStorage:
    """
    Store review verdicts for training pipeline.

    Verdicts are anonymized (no PII) and stored in JSONL format.
    Each line is a training example.

    Usage:
        storage = ReviewStorage()
        storage.save_verdict(sample)

        # Later, for training
        for example in storage.load_all():
            train(example)
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = path or get_reviews_path()

    def save_verdict(self, sample: ReviewSample) -> None:
        """
        Save an anonymized verdict to storage.

        The sample's context is anonymized (value replaced with [TOKEN])
        before writing. No PII is stored.
        """
        if sample.verdict is None:
            return  # Don't save unreviewed samples

        if sample.verdict == Verdict.SKIP:
            return  # Don't save skipped samples

        # Get anonymized training data
        record = sample.to_training_dict()

        # Append to JSONL
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def load_all(self) -> Iterator[dict]:
        """Load all saved verdicts for training."""
        if not self.path.exists():
            return

        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def get_stats(self) -> dict:
        """Get statistics about saved verdicts."""
        total = 0
        tp = 0
        fp = 0
        by_entity = {}

        for record in self.load_all():
            total += 1
            verdict = record.get("verdict")
            if verdict == "TP":
                tp += 1
            elif verdict == "FP":
                fp += 1

            entity = record.get("entity_type", "unknown")
            by_entity[entity] = by_entity.get(entity, 0) + 1

        return {
            "total": total,
            "true_positives": tp,
            "false_positives": fp,
            "accuracy": tp / total if total > 0 else 0.0,
            "by_entity_type": by_entity,
        }

    def clear(self) -> int:
        """Clear all stored verdicts. Returns count deleted."""
        if not self.path.exists():
            return 0

        count = sum(1 for _ in self.load_all())
        self.path.unlink()
        return count
