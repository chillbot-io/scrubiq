"""Multi-layer classification pipeline."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from .detectors.regex import RegexDetector
from .detectors.presidio import PresidioDetector, HAS_PRESIDIO
from ..scanner.results import Match, LabelRecommendation, EntityType


# Check for TP/FP classifier availability
try:
    from ..training.model import TPFPClassifier, is_available as tpfp_available

    HAS_TPFP = tpfp_available()
except ImportError:
    HAS_TPFP = False
    TPFPClassifier = None


# High-sensitivity entity types requiring stricter labels
HIGH_SENSITIVITY_TYPES = {
    EntityType.SSN,
    EntityType.CREDIT_CARD,
    EntityType.MRN,
    EntityType.HEALTH_PLAN_ID,
    EntityType.CVV,
    EntityType.PRIVATE_KEY,
}


@dataclass
class ClassificationResult:
    """Result of classifying text content."""

    matches: list[Match]
    label_recommendation: Optional[LabelRecommendation]

    @property
    def has_sensitive_data(self) -> bool:
        """Check if any real (non-test) sensitive data found."""
        return any(not m.is_test_data for m in self.matches)

    @property
    def real_matches(self) -> list[Match]:
        """Get matches excluding test data."""
        return [m for m in self.matches if not m.is_test_data]


class ClassifierPipeline:
    """
    Multi-layer classification pipeline.

    Combines multiple detection strategies:
        1. Regex patterns (SSN, CC, email, phone) - fast, precise
        2. Presidio NER (names, addresses) - slower, catches more
        3. TP/FP filter (optional) - reduces false positives

    Results are deduplicated to avoid double-counting when both
    detectors find the same entity.

    Usage:
        pipeline = ClassifierPipeline()
        result = pipeline.classify("John Smith SSN: 078-05-1120")

        for match in result.matches:
            print(f"{match.entity_type}: {match.value}")

    Without Presidio:
        pipeline = ClassifierPipeline(enable_presidio=False)

    With TP/FP filter:
        pipeline = ClassifierPipeline(tpfp_model_path="./models/tpfp-v1")
    """

    def __init__(
        self,
        enable_presidio: bool = True,
        presidio_threshold: float = 0.5,
        tpfp_model_path: Optional[Union[str, Path]] = None,
        tpfp_threshold: float = 0.5,
    ):
        """
        Initialize classification pipeline.

        Args:
            enable_presidio: Whether to use Presidio NER (if available).
            presidio_threshold: Minimum confidence for Presidio matches.
            tpfp_model_path: Path to trained TP/FP classifier model.
            tpfp_threshold: Confidence threshold for TP/FP filter.
        """
        # Layer 1: Regex (always available)
        self.regex_detector = RegexDetector()

        # Layer 2: Presidio NER (optional)
        self.presidio_detector: Optional[PresidioDetector] = None
        if enable_presidio and HAS_PRESIDIO:
            try:
                self.presidio_detector = PresidioDetector(score_threshold=presidio_threshold)
            except Exception:
                # Presidio init failed (e.g., spaCy model not downloaded)
                pass

        # Layer 3: TP/FP filter (optional)
        self.tpfp_classifier: Optional[TPFPClassifier] = None
        self.tpfp_threshold = tpfp_threshold
        if tpfp_model_path and HAS_TPFP:
            try:
                self.tpfp_classifier = TPFPClassifier.load(tpfp_model_path)
            except Exception:
                # Model load failed
                pass

    @property
    def has_presidio(self) -> bool:
        """Check if Presidio is active."""
        return self.presidio_detector is not None

    @property
    def has_tpfp_filter(self) -> bool:
        """Check if TP/FP filter is active."""
        return self.tpfp_classifier is not None

    def classify(self, text: str, filename: str = "") -> ClassificationResult:
        """
        Classify text content for sensitive data.

        Args:
            text: Text content to analyze.
            filename: Optional filename for context.

        Returns:
            ClassificationResult with matches and label recommendation.
        """
        all_matches: list[Match] = []

        # Layer 1: Regex patterns
        regex_matches = self.regex_detector.detect(text)
        all_matches.extend(regex_matches)

        # Layer 2: Presidio NER
        if self.presidio_detector:
            try:
                presidio_matches = self.presidio_detector.detect(text)
                all_matches.extend(presidio_matches)
            except Exception:
                # Don't fail the whole scan if Presidio errors
                pass

        # Deduplicate overlapping matches
        matches = self._deduplicate(all_matches)

        # Layer 3: TP/FP filter
        if self.tpfp_classifier:
            matches = self._apply_tpfp_filter(matches)

        # Determine label recommendation
        label = self._recommend_label(matches)

        return ClassificationResult(
            matches=matches,
            label_recommendation=label,
        )

    def _apply_tpfp_filter(self, matches: list[Match]) -> list[Match]:
        """
        Apply TP/FP classifier to filter false positives.

        Updates match.is_test_data based on model prediction.
        """
        if not matches or not self.tpfp_classifier:
            return matches

        # Format contexts for batch prediction
        contexts = []
        for match in matches:
            # Format: replace value with [TOKEN]
            formatted = self.tpfp_classifier.format_match_context(
                context=match.context,
                value=match.value,
                entity_type=match.entity_type.value,
            )
            contexts.append(formatted)

        # Batch predict
        results = self.tpfp_classifier.predict_batch(contexts)

        # Update matches
        for match, result in zip(matches, results):
            if result.is_false_positive and result.confidence >= self.tpfp_threshold:
                # Mark as test data (will be filtered from real_matches)
                match.is_test_data = True

        return matches

    def _deduplicate(self, matches: list[Match]) -> list[Match]:
        """
        Remove overlapping matches, keeping highest confidence.

        When regex and Presidio both detect the same span, we keep
        the one with higher confidence.
        """
        if not matches:
            return []

        # Sort by start position, then by confidence (descending)
        # This ensures when we hit overlaps, we've already kept the best one
        sorted_matches = sorted(matches, key=lambda m: (m.start, -m.confidence))

        result = []
        last_end = -1

        for match in sorted_matches:
            # Skip if overlaps with previous match
            if match.start < last_end:
                continue

            result.append(match)
            last_end = match.end

        return result

    def _recommend_label(self, matches: list[Match]) -> Optional[LabelRecommendation]:
        """
        Determine sensitivity label based on matches.

        Labels (from most to least sensitive):
            - HIGHLY_CONFIDENTIAL: High-sensitivity PII with high confidence
            - CONFIDENTIAL: High-sensitivity PII with lower confidence
            - INTERNAL: Other PII with moderate confidence
            - PUBLIC: Low-confidence matches only
        """
        if not matches:
            return None

        # Filter out test data
        real_matches = [m for m in matches if not m.is_test_data]
        if not real_matches:
            return None

        # Check for high-sensitivity data
        has_high_sensitivity = any(m.entity_type in HIGH_SENSITIVITY_TYPES for m in real_matches)

        max_confidence = max(m.confidence for m in real_matches)

        if has_high_sensitivity and max_confidence >= 0.85:
            return LabelRecommendation.HIGHLY_CONFIDENTIAL
        elif has_high_sensitivity:
            return LabelRecommendation.CONFIDENTIAL
        elif max_confidence >= 0.70:
            return LabelRecommendation.INTERNAL
        else:
            return LabelRecommendation.PUBLIC
