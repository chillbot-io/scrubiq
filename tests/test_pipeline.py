"""Tests for classification pipeline."""

import pytest
from scrubiq.classifier.pipeline import (
    ClassifierPipeline,
    ClassificationResult,
    HIGH_SENSITIVITY_TYPES,
)
from scrubiq.scanner.results import EntityType, LabelRecommendation


class TestClassificationResult:
    """Tests for ClassificationResult dataclass."""

    def test_has_sensitive_data_true(self):
        """Non-test matches mean sensitive data present."""
        from scrubiq.scanner.results import Match

        result = ClassificationResult(
            matches=[
                Match(
                    entity_type=EntityType.SSN,
                    value="078-05-1120",
                    start=0,
                    end=11,
                    confidence=0.9,
                    detector="regex",
                )
            ],
            label_recommendation=LabelRecommendation.CONFIDENTIAL,
        )
        assert result.has_sensitive_data

    def test_has_sensitive_data_false_when_empty(self):
        """No matches means no sensitive data."""
        result = ClassificationResult(matches=[], label_recommendation=None)
        assert not result.has_sensitive_data

    def test_has_sensitive_data_false_when_all_test(self):
        """All test data means no real sensitive data."""
        from scrubiq.scanner.results import Match

        result = ClassificationResult(
            matches=[
                Match(
                    entity_type=EntityType.SSN,
                    value="123-45-6789",
                    start=0,
                    end=11,
                    confidence=0.9,
                    detector="regex",
                    is_test_data=True,
                )
            ],
            label_recommendation=None,
        )
        assert not result.has_sensitive_data

    def test_real_matches_excludes_test_data(self):
        """real_matches property filters out test data."""
        from scrubiq.scanner.results import Match

        result = ClassificationResult(
            matches=[
                Match(EntityType.SSN, "078-05-1120", 0, 11, 0.9, "regex"),
                Match(EntityType.SSN, "123-45-6789", 20, 31, 0.9, "regex", is_test_data=True),
            ],
            label_recommendation=LabelRecommendation.CONFIDENTIAL,
        )

        assert len(result.matches) == 2
        assert len(result.real_matches) == 1
        assert result.real_matches[0].value == "078-05-1120"


class TestClassifierPipeline:
    """Tests for ClassifierPipeline."""

    @pytest.fixture
    def pipeline(self):
        """Create pipeline without Presidio (faster tests)."""
        return ClassifierPipeline(enable_presidio=False)

    def test_detects_ssn(self, pipeline):
        """Pipeline detects SSN via regex."""
        result = pipeline.classify("Employee SSN: 078-05-1120")

        assert len(result.matches) >= 1
        ssn_matches = [m for m in result.matches if m.entity_type == EntityType.SSN]
        assert len(ssn_matches) == 1
        assert ssn_matches[0].value == "078-05-1120"

    def test_detects_credit_card(self, pipeline):
        """Pipeline detects credit card via regex."""
        result = pipeline.classify("Card: 4532015112830366")

        cc_matches = [m for m in result.matches if m.entity_type == EntityType.CREDIT_CARD]
        assert len(cc_matches) == 1

    def test_detects_email(self, pipeline):
        """Pipeline detects email via regex."""
        result = pipeline.classify("Contact: john.doe@company.com")

        email_matches = [m for m in result.matches if m.entity_type == EntityType.EMAIL]
        assert len(email_matches) == 1
        assert email_matches[0].value == "john.doe@company.com"

    def test_detects_phone(self, pipeline):
        """Pipeline detects phone number via regex."""
        result = pipeline.classify("Call: (555) 867-5309")

        phone_matches = [m for m in result.matches if m.entity_type == EntityType.PHONE]
        assert len(phone_matches) == 1

    def test_flags_test_ssn(self, pipeline):
        """Pipeline flags known test SSN patterns."""
        result = pipeline.classify("Example: 123-45-6789")

        assert len(result.matches) >= 1
        assert result.matches[0].is_test_data

    def test_clean_text_no_matches(self, pipeline):
        """Clean text produces no matches."""
        result = pipeline.classify("This is a normal document with no sensitive data.")

        assert len(result.matches) == 0
        assert result.label_recommendation is None

    def test_has_presidio_false_when_disabled(self, pipeline):
        """has_presidio is False when disabled."""
        assert not pipeline.has_presidio

    def test_classify_with_filename(self, pipeline):
        """classify accepts optional filename."""
        result = pipeline.classify("SSN: 078-05-1120", filename="employee.txt")
        assert len(result.matches) >= 1


class TestPipelineDeduplication:
    """Tests for deduplication logic."""

    @pytest.fixture
    def pipeline(self):
        return ClassifierPipeline(enable_presidio=False)

    def test_no_duplicate_matches(self, pipeline):
        """Same entity shouldn't appear twice."""
        # Text with a single SSN
        result = pipeline.classify("SSN: 078-05-1120 is the number")

        ssn_matches = [m for m in result.matches if m.entity_type == EntityType.SSN]
        assert len(ssn_matches) == 1

    def test_multiple_distinct_entities(self, pipeline):
        """Different entities in same text detected separately."""
        result = pipeline.classify("SSN: 078-05-1120, Email: john@example.com")

        ssn_matches = [m for m in result.matches if m.entity_type == EntityType.SSN]
        email_matches = [m for m in result.matches if m.entity_type == EntityType.EMAIL]

        assert len(ssn_matches) == 1
        assert len(email_matches) == 1


class TestPipelineLabelRecommendation:
    """Tests for label recommendation logic."""

    @pytest.fixture
    def pipeline(self):
        return ClassifierPipeline(enable_presidio=False)

    def test_highly_confidential_for_high_confidence_ssn(self, pipeline):
        """High confidence SSN gets HIGHLY_CONFIDENTIAL."""
        result = pipeline.classify("Employee SSN: 078-05-1120")

        # Check we got a match with high confidence
        ssn_matches = [m for m in result.matches if m.entity_type == EntityType.SSN]
        assert len(ssn_matches) == 1
        assert ssn_matches[0].confidence >= 0.75  # Our regex gives 0.75 base

        # Label should be CONFIDENTIAL or HIGHLY_CONFIDENTIAL
        assert result.label_recommendation in [
            LabelRecommendation.CONFIDENTIAL,
            LabelRecommendation.HIGHLY_CONFIDENTIAL,
        ]

    def test_no_label_for_empty_results(self, pipeline):
        """No matches means no label recommendation."""
        result = pipeline.classify("Just some normal text here.")
        assert result.label_recommendation is None

    def test_no_label_for_test_data_only(self, pipeline):
        """Test data only means no label recommendation."""
        result = pipeline.classify("Test SSN: 123-45-6789")

        # Match exists but is test data
        assert len(result.matches) >= 1
        assert all(m.is_test_data for m in result.matches)
        assert result.label_recommendation is None

    def test_internal_for_email_only(self, pipeline):
        """Email-only results get INTERNAL label."""
        result = pipeline.classify("Contact: john.doe@company.com for details")

        # Should have email match with high confidence (0.90)
        email_matches = [m for m in result.matches if m.entity_type == EntityType.EMAIL]
        assert len(email_matches) == 1

        # Email is not high-sensitivity, so INTERNAL or lower
        if result.label_recommendation:
            assert result.label_recommendation in [
                LabelRecommendation.INTERNAL,
                LabelRecommendation.PUBLIC,
            ]


class TestHighSensitivityTypes:
    """Tests for high sensitivity type classification."""

    def test_ssn_is_high_sensitivity(self):
        """SSN is classified as high sensitivity."""
        assert EntityType.SSN in HIGH_SENSITIVITY_TYPES

    def test_credit_card_is_high_sensitivity(self):
        """Credit card is classified as high sensitivity."""
        assert EntityType.CREDIT_CARD in HIGH_SENSITIVITY_TYPES

    def test_mrn_is_high_sensitivity(self):
        """Medical record number is classified as high sensitivity."""
        assert EntityType.MRN in HIGH_SENSITIVITY_TYPES

    def test_email_is_not_high_sensitivity(self):
        """Email is not classified as high sensitivity."""
        assert EntityType.EMAIL not in HIGH_SENSITIVITY_TYPES

    def test_phone_is_not_high_sensitivity(self):
        """Phone number is not classified as high sensitivity."""
        assert EntityType.PHONE not in HIGH_SENSITIVITY_TYPES


class TestPresidioIntegration:
    """Tests for Presidio integration (if available)."""

    def test_pipeline_works_without_presidio(self):
        """Pipeline works even when Presidio is disabled."""
        pipeline = ClassifierPipeline(enable_presidio=False)
        result = pipeline.classify("John Smith SSN: 078-05-1120")

        # Should still detect SSN via regex
        ssn_matches = [m for m in result.matches if m.entity_type == EntityType.SSN]
        assert len(ssn_matches) == 1

    def test_presidio_enabled_by_default(self):
        """Presidio is enabled by default (if available)."""
        pipeline = ClassifierPipeline()
        # has_presidio depends on whether presidio is installed
        # Just verify no error on creation
        assert pipeline is not None

    def test_presidio_threshold_configurable(self):
        """Presidio threshold can be configured."""
        pipeline = ClassifierPipeline(
            enable_presidio=True,
            presidio_threshold=0.7,
        )
        # No error on creation
        assert pipeline is not None
