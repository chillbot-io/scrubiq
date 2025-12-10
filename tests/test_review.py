"""Tests for human review system."""

import pytest
from datetime import datetime
from pathlib import Path

from scrubiq.review.models import ReviewSample, Verdict
from scrubiq.review.storage import ReviewStorage


class TestVerdict:
    """Test Verdict enum."""

    def test_correct_value(self):
        assert Verdict.CORRECT.value == "TP"

    def test_wrong_value(self):
        assert Verdict.WRONG.value == "FP"

    def test_skip_value(self):
        assert Verdict.SKIP.value == "skip"


class TestReviewSample:
    """Test ReviewSample model."""

    @pytest.fixture
    def sample(self):
        return ReviewSample(
            id=1,
            scan_id="test123",
            entity_type="ssn",
            value="123-45-6789",
            value_redacted="12*-**-*789",
            confidence=0.72,
            detector="regex",
            context="Employee SSN: 123-45-6789 on file",
            file_path="/test/hr/employees.txt",
            file_type=".txt",
        )

    def test_confidence_pct(self, sample):
        assert sample.confidence_pct == 72

    def test_anonymize_context(self, sample):
        anonymized = sample.anonymize_context()
        assert "123-45-6789" not in anonymized
        assert "[SSN]" in anonymized
        assert "Employee SSN:" in anonymized

    def test_anonymize_context_preserves_surrounding_text(self, sample):
        anonymized = sample.anonymize_context()
        assert "Employee" in anonymized
        assert "on file" in anonymized

    def test_to_training_dict_anonymizes(self, sample):
        sample.verdict = Verdict.CORRECT
        sample.reviewed_at = datetime.now()

        training = sample.to_training_dict()

        assert "123-45-6789" not in training["context"]
        assert "[SSN]" in training["context"]

    def test_to_training_dict_includes_verdict(self, sample):
        sample.verdict = Verdict.WRONG
        sample.reviewed_at = datetime.now()

        training = sample.to_training_dict()

        assert training["verdict"] == "FP"

    def test_to_training_dict_includes_metadata(self, sample):
        sample.verdict = Verdict.CORRECT
        sample.reviewed_at = datetime.now()

        training = sample.to_training_dict()

        assert training["entity_type"] == "ssn"
        assert training["confidence"] == 0.72
        assert training["detector"] == "regex"
        assert training["file_type"] == ".txt"

    def test_initial_verdict_is_none(self, sample):
        assert sample.verdict is None

    def test_initial_reviewed_at_is_none(self, sample):
        assert sample.reviewed_at is None


class TestReviewStorage:
    """Test ReviewStorage class."""

    @pytest.fixture
    def storage(self, tmp_path):
        return ReviewStorage(path=tmp_path / "reviews.jsonl")

    @pytest.fixture
    def sample(self):
        return ReviewSample(
            id=1,
            scan_id="test123",
            entity_type="ssn",
            value="123-45-6789",
            value_redacted="12*-**-*789",
            confidence=0.72,
            detector="regex",
            context="Employee SSN: 123-45-6789 on file",
            file_path="/test/hr/employees.txt",
            file_type=".txt",
        )

    def test_save_creates_file(self, storage, sample):
        sample.verdict = Verdict.CORRECT
        sample.reviewed_at = datetime.now()

        storage.save_verdict(sample)

        assert storage.path.exists()

    def test_save_anonymizes_value(self, storage, sample):
        sample.verdict = Verdict.WRONG
        sample.reviewed_at = datetime.now()

        storage.save_verdict(sample)

        content = storage.path.read_text()
        assert "123-45-6789" not in content
        assert "[SSN]" in content

    def test_skip_not_saved(self, storage, sample):
        sample.verdict = Verdict.SKIP
        sample.reviewed_at = datetime.now()

        storage.save_verdict(sample)

        assert not storage.path.exists()

    def test_none_verdict_not_saved(self, storage, sample):
        storage.save_verdict(sample)

        assert not storage.path.exists()

    def test_load_all_returns_saved(self, storage, sample):
        sample.verdict = Verdict.CORRECT
        sample.reviewed_at = datetime.now()

        storage.save_verdict(sample)

        loaded = list(storage.load_all())
        assert len(loaded) == 1
        assert loaded[0]["verdict"] == "TP"

    def test_multiple_saves_append(self, storage, sample):
        sample.verdict = Verdict.CORRECT
        sample.reviewed_at = datetime.now()
        storage.save_verdict(sample)

        sample2 = ReviewSample(
            id=2,
            scan_id="test123",
            entity_type="email",
            value="test@example.com",
            value_redacted="te**@ex*****.com",
            confidence=0.65,
            detector="regex",
            context="Contact: test@example.com for info",
            file_path="/test/contact.txt",
            file_type=".txt",
            verdict=Verdict.WRONG,
            reviewed_at=datetime.now(),
        )
        storage.save_verdict(sample2)

        loaded = list(storage.load_all())
        assert len(loaded) == 2

    def test_get_stats_empty(self, storage):
        stats = storage.get_stats()

        assert stats["total"] == 0
        assert stats["true_positives"] == 0
        assert stats["false_positives"] == 0

    def test_get_stats_with_data(self, storage, sample):
        # Add some verdicts
        sample.verdict = Verdict.CORRECT
        sample.reviewed_at = datetime.now()
        storage.save_verdict(sample)

        sample2 = ReviewSample(
            id=2,
            scan_id="test123",
            entity_type="email",
            value="test@example.com",
            value_redacted="te**@ex*****.com",
            confidence=0.65,
            detector="regex",
            context="Contact: test@example.com for info",
            file_path="/test/contact.txt",
            file_type=".txt",
            verdict=Verdict.WRONG,
            reviewed_at=datetime.now(),
        )
        storage.save_verdict(sample2)

        stats = storage.get_stats()

        assert stats["total"] == 2
        assert stats["true_positives"] == 1
        assert stats["false_positives"] == 1
        assert stats["accuracy"] == 0.5

    def test_get_stats_by_entity_type(self, storage, sample):
        sample.verdict = Verdict.CORRECT
        sample.reviewed_at = datetime.now()
        storage.save_verdict(sample)

        stats = storage.get_stats()

        assert "ssn" in stats["by_entity_type"]
        assert stats["by_entity_type"]["ssn"] == 1

    def test_clear_removes_all(self, storage, sample):
        sample.verdict = Verdict.CORRECT
        sample.reviewed_at = datetime.now()
        storage.save_verdict(sample)

        count = storage.clear()

        assert count == 1
        assert not storage.path.exists()

    def test_clear_empty_returns_zero(self, storage):
        count = storage.clear()
        assert count == 0


class TestReviewSampleAnonymization:
    """Test various anonymization scenarios."""

    def test_email_anonymization(self):
        sample = ReviewSample(
            id=1,
            scan_id="test",
            entity_type="email",
            value="john.doe@company.com",
            value_redacted="jo**@co*****.com",
            confidence=0.9,
            detector="regex",
            context="Please contact john.doe@company.com for details",
            file_path="/test.txt",
            file_type=".txt",
        )

        anonymized = sample.anonymize_context()
        assert "john.doe@company.com" not in anonymized
        assert "[EMAIL]" in anonymized

    def test_credit_card_anonymization(self):
        sample = ReviewSample(
            id=1,
            scan_id="test",
            entity_type="credit_card",
            value="4111111111111111",
            value_redacted="41**********1111",
            confidence=0.85,
            detector="regex",
            context="Card number: 4111111111111111",
            file_path="/test.txt",
            file_type=".txt",
        )

        anonymized = sample.anonymize_context()
        assert "4111111111111111" not in anonymized
        assert "[CREDIT_CARD]" in anonymized

    def test_phone_anonymization(self):
        sample = ReviewSample(
            id=1,
            scan_id="test",
            entity_type="phone",
            value="555-123-4567",
            value_redacted="55*-***-*567",
            confidence=0.7,
            detector="regex",
            context="Call 555-123-4567 for support",
            file_path="/test.txt",
            file_type=".txt",
        )

        anonymized = sample.anonymize_context()
        assert "555-123-4567" not in anonymized
        assert "[PHONE]" in anonymized

    def test_value_not_in_context_unchanged(self):
        sample = ReviewSample(
            id=1,
            scan_id="test",
            entity_type="ssn",
            value="123-45-6789",
            value_redacted="12*-**-*789",
            confidence=0.7,
            detector="regex",
            context="Some context without the actual value",
            file_path="/test.txt",
            file_type=".txt",
        )

        anonymized = sample.anonymize_context()
        # Should just return original since value not found
        assert "[SSN]" in anonymized or "Some context" in anonymized


class TestReviewSamplerIntegration:
    """Integration tests for ReviewSampler with database."""

    @pytest.fixture
    def db_with_findings(self, tmp_path):
        """Create a database with some low-confidence findings."""
        from scrubiq.storage.database import FindingsDatabase
        from scrubiq.scanner.results import (
            ScanResult,
            FileResult,
            Match,
            EntityType,
            LabelRecommendation,
        )

        db = FindingsDatabase(db_path=str(tmp_path / "test.db"))

        # Create scan with mixed confidence findings
        scan = ScanResult(scan_id="test-scan", source_path="/test", source_type="filesystem")

        file = FileResult(
            path=Path("/test/data.txt"),
            source="filesystem",
            size_bytes=1000,
            modified=datetime.now(),
            matches=[
                Match(
                    EntityType.SSN,
                    "123-45-6789",
                    0,
                    11,
                    0.95,
                    "regex",
                    context="High conf SSN: 123-45-6789",
                ),
                Match(
                    EntityType.EMAIL,
                    "test@example.com",
                    20,
                    36,
                    0.72,
                    "regex",
                    context="Low conf email: test@example.com",
                ),
                Match(
                    EntityType.PHONE,
                    "555-1234",
                    50,
                    58,
                    0.65,
                    "regex",
                    context="Low conf phone: 555-1234",
                ),
            ],
            label_recommendation=LabelRecommendation.CONFIDENTIAL,
        )
        scan.add_file(file)
        scan.complete()

        db.store_scan(scan)

        yield db
        db.close()

    def test_sampler_filters_by_confidence(self, db_with_findings):
        from scrubiq.review.sampler import ReviewSampler

        sampler = ReviewSampler(db_with_findings)
        samples = list(sampler.get_samples("test-scan", max_confidence=0.85))

        # Should only get the low-confidence ones (0.72 and 0.65)
        assert len(samples) == 2
        assert all(s.confidence < 0.85 for s in samples)

    def test_sampler_sorts_by_confidence_ascending(self, db_with_findings):
        from scrubiq.review.sampler import ReviewSampler

        sampler = ReviewSampler(db_with_findings)
        samples = list(sampler.get_samples("test-scan", max_confidence=0.85))

        # Lowest confidence should be first
        assert samples[0].confidence <= samples[1].confidence

    def test_sampler_count_reviewable(self, db_with_findings):
        from scrubiq.review.sampler import ReviewSampler

        sampler = ReviewSampler(db_with_findings)
        count = sampler.count_reviewable("test-scan", max_confidence=0.85)

        assert count == 2

    def test_sampler_respects_limit(self, db_with_findings):
        from scrubiq.review.sampler import ReviewSampler

        sampler = ReviewSampler(db_with_findings)
        samples = list(sampler.get_samples("test-scan", max_confidence=0.85, limit=1))

        assert len(samples) == 1
