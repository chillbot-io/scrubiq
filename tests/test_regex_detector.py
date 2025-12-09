"""Tests for regex detector."""

import pytest

from scrubiq.classifier.detectors.regex import (
    RegexDetector,
    luhn_check,
    validate_ssn,
)
from scrubiq.scanner.results import EntityType


class TestValidateSSN:
    def test_valid_ssn_with_dashes(self):
        assert validate_ssn("078-05-1120")

    def test_valid_ssn_without_dashes(self):
        assert validate_ssn("078051120")

    def test_valid_ssn_with_spaces(self):
        assert validate_ssn("078 05 1120")

    def test_invalid_area_000(self):
        assert not validate_ssn("000-12-3456")

    def test_invalid_area_666(self):
        assert not validate_ssn("666-12-3456")

    def test_invalid_area_900s(self):
        assert not validate_ssn("900-12-3456")
        assert not validate_ssn("999-12-3456")

    def test_invalid_group_00(self):
        assert not validate_ssn("123-00-4567")

    def test_invalid_serial_0000(self):
        assert not validate_ssn("123-45-0000")

    def test_wrong_length(self):
        assert not validate_ssn("12-34-5678")
        assert not validate_ssn("1234-56-7890")


class TestLuhnCheck:
    def test_valid_visa_test_card(self):
        assert luhn_check("4111111111111111")

    def test_valid_mastercard_test(self):
        assert luhn_check("5500000000000004")

    def test_valid_amex_test(self):
        assert luhn_check("378282246310005")

    def test_valid_with_spaces(self):
        assert luhn_check("4111 1111 1111 1111")

    def test_valid_with_dashes(self):
        assert luhn_check("4111-1111-1111-1111")

    def test_invalid_random_number(self):
        assert not luhn_check("1234567890123456")

    def test_invalid_too_short(self):
        assert not luhn_check("411111111111")

    def test_invalid_too_long(self):
        assert not luhn_check("41111111111111111111")


class TestRegexDetectorSSN:
    @pytest.fixture
    def detector(self):
        return RegexDetector()

    def test_detect_ssn_with_dashes(self, detector):
        text = "Employee SSN: 078-05-1120"
        matches = detector.detect(text)

        ssn_matches = [m for m in matches if m.entity_type == EntityType.SSN]
        assert len(ssn_matches) == 1
        assert ssn_matches[0].value == "078-05-1120"
        assert ssn_matches[0].confidence == 0.75
        assert ssn_matches[0].detector == "regex"

    def test_detect_ssn_without_dashes(self, detector):
        text = "SSN: 078051120"
        matches = detector.detect(text)

        ssn_matches = [m for m in matches if m.entity_type == EntityType.SSN]
        assert len(ssn_matches) == 1
        assert ssn_matches[0].value == "078051120"

    def test_detect_test_ssn_flagged(self, detector):
        text = "Example: 123-45-6789"
        matches = detector.detect(text)

        ssn_matches = [m for m in matches if m.entity_type == EntityType.SSN]
        assert len(ssn_matches) == 1
        assert ssn_matches[0].is_test_data is True

    def test_detect_real_ssn_not_flagged(self, detector):
        text = "Real SSN: 078-05-1120"
        matches = detector.detect(text)

        ssn_matches = [m for m in matches if m.entity_type == EntityType.SSN]
        assert len(ssn_matches) == 1
        assert ssn_matches[0].is_test_data is False

    def test_invalid_ssn_not_detected(self, detector):
        text = "Invalid: 000-00-0000"
        matches = detector.detect(text)

        ssn_matches = [m for m in matches if m.entity_type == EntityType.SSN]
        assert len(ssn_matches) == 0

    def test_multiple_ssns(self, detector):
        text = "SSN1: 078-05-1120, SSN2: 219-09-9999"
        matches = detector.detect(text)

        ssn_matches = [m for m in matches if m.entity_type == EntityType.SSN]
        assert len(ssn_matches) == 2


class TestRegexDetectorCreditCard:
    @pytest.fixture
    def detector(self):
        return RegexDetector()

    def test_detect_visa(self, detector):
        # Using a valid Luhn number
        text = "Card: 4532015112830366"
        matches = detector.detect(text)

        cc_matches = [m for m in matches if m.entity_type == EntityType.CREDIT_CARD]
        assert len(cc_matches) == 1
        assert cc_matches[0].confidence == 0.70

    def test_detect_test_card_flagged(self, detector):
        text = "Test card: 4111111111111111"
        matches = detector.detect(text)

        cc_matches = [m for m in matches if m.entity_type == EntityType.CREDIT_CARD]
        assert len(cc_matches) == 1
        assert cc_matches[0].is_test_data is True

    def test_invalid_luhn_not_detected(self, detector):
        text = "Invalid card: 4111111111111112"  # Fails Luhn
        matches = detector.detect(text)

        cc_matches = [m for m in matches if m.entity_type == EntityType.CREDIT_CARD]
        assert len(cc_matches) == 0


class TestRegexDetectorEmail:
    @pytest.fixture
    def detector(self):
        return RegexDetector()

    def test_detect_email(self, detector):
        text = "Contact: john.doe@company.com"
        matches = detector.detect(text)

        email_matches = [m for m in matches if m.entity_type == EntityType.EMAIL]
        assert len(email_matches) == 1
        assert email_matches[0].value == "john.doe@company.com"
        assert email_matches[0].confidence == 0.90

    def test_detect_test_email_flagged(self, detector):
        text = "Email: test@example.com"
        matches = detector.detect(text)

        email_matches = [m for m in matches if m.entity_type == EntityType.EMAIL]
        assert len(email_matches) == 1
        assert email_matches[0].is_test_data is True

    def test_detect_real_email_not_flagged(self, detector):
        text = "Email: jane.smith@acmecorp.com"
        matches = detector.detect(text)

        email_matches = [m for m in matches if m.entity_type == EntityType.EMAIL]
        assert len(email_matches) == 1
        assert email_matches[0].is_test_data is False


class TestRegexDetectorPhone:
    @pytest.fixture
    def detector(self):
        return RegexDetector()

    def test_detect_phone_with_dashes(self, detector):
        text = "Call: 212-555-1234"
        matches = detector.detect(text)

        phone_matches = [m for m in matches if m.entity_type == EntityType.PHONE]
        assert len(phone_matches) == 1
        assert phone_matches[0].confidence == 0.65

    def test_detect_phone_with_parens(self, detector):
        text = "Phone: (212) 555-1234"
        matches = detector.detect(text)

        phone_matches = [m for m in matches if m.entity_type == EntityType.PHONE]
        assert len(phone_matches) == 1

    def test_detect_test_phone_flagged(self, detector):
        text = "Test: 555-555-5555"
        matches = detector.detect(text)

        phone_matches = [m for m in matches if m.entity_type == EntityType.PHONE]
        assert len(phone_matches) == 1
        assert phone_matches[0].is_test_data is True


class TestRegexDetectorGeneral:
    @pytest.fixture
    def detector(self):
        return RegexDetector()

    def test_no_matches_on_clean_text(self, detector):
        text = "This is a normal document with no sensitive data."
        matches = detector.detect(text)

        assert len(matches) == 0

    def test_context_captured(self, detector):
        text = "The employee named John Smith has SSN 078-05-1120 on file."
        matches = detector.detect(text)

        ssn_matches = [m for m in matches if m.entity_type == EntityType.SSN]
        assert len(ssn_matches) == 1
        assert "John Smith" in ssn_matches[0].context
        assert "on file" in ssn_matches[0].context

    def test_multiple_entity_types(self, detector):
        text = """
        Employee: John Smith
        SSN: 078-05-1120
        Email: john.smith@company.com
        Phone: 212-555-1234
        """
        matches = detector.detect(text)

        types_found = {m.entity_type for m in matches}
        assert EntityType.SSN in types_found
        assert EntityType.EMAIL in types_found
        assert EntityType.PHONE in types_found

    def test_position_tracking(self, detector):
        text = "SSN: 078-05-1120"
        matches = detector.detect(text)

        ssn_matches = [m for m in matches if m.entity_type == EntityType.SSN]
        assert len(ssn_matches) == 1

        # Verify position is correct
        match = ssn_matches[0]
        assert text[match.start : match.end] == "078-05-1120"
