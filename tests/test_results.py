"""Tests for core data models."""

from datetime import datetime
from pathlib import Path

import pytest

from scrubiq.scanner.results import (
    Confidence,
    EntityType,
    FileResult,
    LabelRecommendation,
    Match,
    ScanResult,
)


class TestConfidence:
    def test_from_score_very_high(self):
        assert Confidence.from_score(0.99) == Confidence.VERY_HIGH
        assert Confidence.from_score(0.95) == Confidence.VERY_HIGH

    def test_from_score_high(self):
        assert Confidence.from_score(0.94) == Confidence.HIGH
        assert Confidence.from_score(0.85) == Confidence.HIGH

    def test_from_score_medium(self):
        assert Confidence.from_score(0.84) == Confidence.MEDIUM
        assert Confidence.from_score(0.70) == Confidence.MEDIUM

    def test_from_score_low(self):
        assert Confidence.from_score(0.69) == Confidence.LOW
        assert Confidence.from_score(0.50) == Confidence.LOW
        assert Confidence.from_score(0.0) == Confidence.LOW


class TestMatch:
    def test_confidence_level(self):
        match = Match(
            entity_type=EntityType.SSN,
            value="123-45-6789",
            start=0,
            end=11,
            confidence=0.92,
            detector="regex",
        )
        assert match.confidence_level == Confidence.HIGH

    def test_redacted_value_standard(self):
        match = Match(
            entity_type=EntityType.SSN,
            value="123-45-6789",
            start=0,
            end=11,
            confidence=0.9,
            detector="regex",
        )
        assert match.redacted_value == "12*******89"

    def test_redacted_value_short(self):
        match = Match(
            entity_type=EntityType.CVV,
            value="123",
            start=0,
            end=3,
            confidence=0.9,
            detector="regex",
        )
        assert match.redacted_value == "***"

    def test_redacted_value_four_chars(self):
        match = Match(
            entity_type=EntityType.CVV,
            value="1234",
            start=0,
            end=4,
            confidence=0.9,
            detector="regex",
        )
        assert match.redacted_value == "****"

    def test_model_version_default_none(self):
        match = Match(
            entity_type=EntityType.SSN,
            value="123-45-6789",
            start=0,
            end=11,
            confidence=0.9,
            detector="regex",
        )
        assert match.model_version is None

    def test_model_version_set(self):
        match = Match(
            entity_type=EntityType.NAME,
            value="John Smith",
            start=0,
            end=10,
            confidence=0.85,
            detector="setfit",
            model_version="v1.0.0+local.3",
        )
        assert match.model_version == "v1.0.0+local.3"


class TestFileResult:
    def test_has_sensitive_data_with_matches(self):
        result = FileResult(
            path=Path("test.txt"),
            source="filesystem",
            size_bytes=100,
            modified=datetime.now(),
            matches=[Match(EntityType.SSN, "123-45-6789", 0, 11, 0.9, "regex")],
        )
        assert result.has_sensitive_data

    def test_has_sensitive_data_no_matches(self):
        result = FileResult(
            path=Path("test.txt"),
            source="filesystem",
            size_bytes=100,
            modified=datetime.now(),
            matches=[],
        )
        assert not result.has_sensitive_data

    def test_has_sensitive_data_only_test_data(self):
        result = FileResult(
            path=Path("test.txt"),
            source="filesystem",
            size_bytes=100,
            modified=datetime.now(),
            matches=[
                Match(EntityType.SSN, "123-45-6789", 0, 11, 0.9, "regex", is_test_data=True)
            ],
        )
        assert not result.has_sensitive_data  # Test data doesn't count

    def test_real_matches_excludes_test_data(self):
        result = FileResult(
            path=Path("test.txt"),
            source="filesystem",
            size_bytes=100,
            modified=datetime.now(),
            matches=[
                Match(EntityType.SSN, "078-05-1120", 0, 11, 0.9, "regex", is_test_data=False),
                Match(EntityType.SSN, "123-45-6789", 20, 31, 0.9, "regex", is_test_data=True),
            ],
        )
        assert len(result.real_matches) == 1
        assert result.real_matches[0].value == "078-05-1120"

    def test_highest_confidence(self):
        result = FileResult(
            path=Path("test.txt"),
            source="filesystem",
            size_bytes=100,
            modified=datetime.now(),
            matches=[
                Match(EntityType.SSN, "078-05-1120", 0, 11, 0.75, "regex"),
                Match(EntityType.EMAIL, "test@example.com", 20, 36, 0.92, "regex"),
            ],
        )
        assert result.highest_confidence == 0.92

    def test_highest_confidence_no_matches(self):
        result = FileResult(
            path=Path("test.txt"),
            source="filesystem",
            size_bytes=100,
            modified=datetime.now(),
        )
        assert result.highest_confidence == 0.0

    def test_entity_types_found(self):
        result = FileResult(
            path=Path("test.txt"),
            source="filesystem",
            size_bytes=100,
            modified=datetime.now(),
            matches=[
                Match(EntityType.SSN, "078-05-1120", 0, 11, 0.9, "regex"),
                Match(EntityType.EMAIL, "test@example.com", 20, 36, 0.9, "regex"),
                Match(EntityType.SSN, "111-22-3333", 50, 61, 0.9, "regex"),
            ],
        )
        assert result.entity_types_found == {EntityType.SSN, EntityType.EMAIL}


class TestScanResult:
    def test_stats_empty(self):
        scan = ScanResult(source_path="./test", source_type="filesystem")
        assert scan.total_files == 0
        assert scan.files_with_matches == 0
        assert scan.files_errored == 0
        assert scan.total_matches == 0

    def test_stats_with_files(self):
        scan = ScanResult(source_path="./test", source_type="filesystem")
        scan.add_file(
            FileResult(
                path=Path("a.txt"),
                source="filesystem",
                size_bytes=100,
                modified=datetime.now(),
                matches=[Match(EntityType.SSN, "111-22-3333", 0, 11, 0.9, "regex")],
            )
        )
        scan.add_file(
            FileResult(
                path=Path("b.txt"),
                source="filesystem",
                size_bytes=100,
                modified=datetime.now(),
                matches=[],
            )
        )
        scan.add_file(
            FileResult(
                path=Path("c.txt"),
                source="filesystem",
                size_bytes=100,
                modified=datetime.now(),
                error="Permission denied",
            )
        )

        assert scan.total_files == 3
        assert scan.files_with_matches == 1
        assert scan.files_errored == 1
        assert scan.total_matches == 1

    def test_complete_sets_timestamp(self):
        scan = ScanResult()
        assert scan.completed_at is None
        scan.complete()
        assert scan.completed_at is not None

    def test_to_dict_structure(self):
        scan = ScanResult(source_path="./test", source_type="filesystem")
        scan.add_file(
            FileResult(
                path=Path("a.txt"),
                source="filesystem",
                size_bytes=100,
                modified=datetime.now(),
                matches=[Match(EntityType.SSN, "078-05-1120", 0, 11, 0.9, "regex")],
                label_recommendation=LabelRecommendation.HIGHLY_CONFIDENTIAL,
            )
        )
        scan.complete()

        d = scan.to_dict()

        assert "scan_id" in d
        assert "started_at" in d
        assert "completed_at" in d
        assert d["source_path"] == "./test"
        assert d["source_type"] == "filesystem"
        assert d["summary"]["total_files"] == 1
        assert d["summary"]["files_with_matches"] == 1
        assert len(d["files"]) == 1

        file_dict = d["files"][0]
        assert file_dict["path"] == "a.txt"
        assert file_dict["has_sensitive_data"] is True
        assert file_dict["label_recommendation"] == "highly_confidential"
        assert len(file_dict["matches"]) == 1

        match_dict = file_dict["matches"][0]
        assert match_dict["entity_type"] == "ssn"
        assert match_dict["value"] == "07*******20"  # Redacted (11 chars - 4 = 7 asterisks)
        assert match_dict["confidence"] == 0.9
        assert match_dict["detector"] == "regex"

    def test_to_dict_includes_model_version(self):
        scan = ScanResult()
        scan.add_file(
            FileResult(
                path=Path("a.txt"),
                source="filesystem",
                size_bytes=100,
                modified=datetime.now(),
                matches=[
                    Match(
                        EntityType.NAME,
                        "John Smith",
                        0,
                        10,
                        0.88,
                        "setfit",
                        model_version="v1.0.0",
                    )
                ],
            )
        )

        d = scan.to_dict()
        assert d["files"][0]["matches"][0]["model_version"] == "v1.0.0"
