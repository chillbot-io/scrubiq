"""Tests for training pipeline."""

import pytest

from scrubiq.training.data import (
    TrainingExample,
    Label,
    generate_false_positives,
    FP_TEMPLATES,
)


class TestTrainingExample:
    """Test TrainingExample dataclass."""

    def test_create_example(self):
        ex = TrainingExample(
            text="Employee [SSN] enrolled in benefits",
            label=1,
            entity_type="ssn",
            source="test",
        )
        assert ex.label == 1
        assert ex.entity_type == "ssn"

    def test_to_dict(self):
        ex = TrainingExample(
            text="Test [SSN]",
            label=0,
            entity_type="ssn",
            source="synthetic",
        )
        d = ex.to_dict()
        assert d["text"] == "Test [SSN]"
        assert d["label"] == 0

    def test_from_dict(self):
        d = {
            "text": "Patient [NAME] admitted",
            "label": 1,
            "entity_type": "name",
            "source": "user_feedback",
        }
        ex = TrainingExample.from_dict(d)
        assert ex.text == "Patient [NAME] admitted"
        assert ex.label == 1

    def test_jsonl_round_trip(self):
        original = TrainingExample(
            text="Card [CREDIT_CARD] charged",
            label=1,
            entity_type="credit_card",
            source="nemotron",
        )
        jsonl = original.to_jsonl()
        restored = TrainingExample.from_jsonl(jsonl)
        assert restored.text == original.text
        assert restored.label == original.label
        assert restored.entity_type == original.entity_type


class TestFalsePositiveGeneration:
    """Test synthetic FP generation."""

    def test_generate_fps(self):
        fps = list(generate_false_positives(n_per_type=5))
        assert len(fps) > 0
        assert all(ex.label == 0 for ex in fps)  # All FPs

    def test_fp_templates_exist(self):
        # Should have templates for common types
        assert "ssn" in FP_TEMPLATES
        assert "email" in FP_TEMPLATES
        assert "phone" in FP_TEMPLATES
        assert "credit_card" in FP_TEMPLATES
        assert "name" in FP_TEMPLATES

    def test_fp_has_token(self):
        """FP templates should contain entity token."""
        fps = list(generate_false_positives(n_per_type=10))
        for ex in fps:
            token = f"[{ex.entity_type.upper()}]"
            assert token in ex.text, f"Missing {token} in: {ex.text}"

    def test_fp_source_is_synthetic(self):
        fps = list(generate_false_positives(n_per_type=3))
        for ex in fps:
            assert ex.source == "synthetic_fp"


class TestLabel:
    """Test Label enum."""

    def test_label_values(self):
        assert Label.FALSE_POSITIVE.value == 0
        assert Label.TRUE_POSITIVE.value == 1


# Skip these tests if setfit not installed
try:
    from scrubiq.training.model import TPFPClassifier, is_available, FilterResult

    HAS_SETFIT = is_available()
except ImportError:
    HAS_SETFIT = False


@pytest.mark.skipif(not HAS_SETFIT, reason="setfit not installed")
class TestTPFPClassifier:
    """Test TP/FP classifier (requires setfit)."""

    def test_format_context(self):
        classifier = TPFPClassifier()
        formatted = classifier.format_match_context(
            context="Employee John Smith enrolled",
            value="John Smith",
            entity_type="name",
        )
        assert "[NAME]" in formatted
        assert "John Smith" not in formatted

    def test_format_context_ssn(self):
        classifier = TPFPClassifier()
        formatted = classifier.format_match_context(
            context="SSN: 078-05-1120 on file",
            value="078-05-1120",
            entity_type="ssn",
        )
        assert "[SSN]" in formatted
        assert "078-05-1120" not in formatted


class TestFilterResult:
    """Test FilterResult dataclass."""

    def test_true_positive(self):
        result = FilterResult(is_true_positive=True, confidence=0.95)
        assert result.is_true_positive
        assert not result.is_false_positive
        assert result.confidence == 0.95

    def test_false_positive(self):
        result = FilterResult(is_true_positive=False, confidence=0.88)
        assert not result.is_true_positive
        assert result.is_false_positive
        assert result.confidence == 0.88


# Integration test with mock data
class TestDataPipeline:
    """Test data loading pipeline."""

    def test_load_user_feedback_missing_file(self):
        """Should gracefully handle missing feedback file."""
        from scrubiq.training.data import load_user_feedback

        # Load from non-existent path
        examples = list(load_user_feedback("/nonexistent/path.jsonl"))
        assert examples == []  # Empty list, no error

    def test_entity_map_coverage(self):
        """Nemotron entity map should cover common types."""
        from scrubiq.training.data import NEMOTRON_ENTITY_MAP

        # Should map common Nemotron types to our types
        assert NEMOTRON_ENTITY_MAP.get("SSN") == "ssn"
        assert NEMOTRON_ENTITY_MAP.get("NAME") == "name"
        assert NEMOTRON_ENTITY_MAP.get("EMAIL") == "email"
        assert NEMOTRON_ENTITY_MAP.get("PHONE") == "phone"
        assert NEMOTRON_ENTITY_MAP.get("CREDIT_CARD") == "credit_card"
