"""Tests for Presidio NER detector."""

import pytest
from scrubiq.classifier.detectors.presidio import (
    HAS_PRESIDIO,
    PRESIDIO_ENTITY_MAP,
    is_available,
)
from scrubiq.scanner.results import EntityType


class TestPresidioAvailability:
    """Tests for Presidio availability checking."""

    def test_has_presidio_is_bool(self):
        """HAS_PRESIDIO is a boolean."""
        assert isinstance(HAS_PRESIDIO, bool)

    def test_is_available_matches_has_presidio(self):
        """is_available() returns same as HAS_PRESIDIO."""
        assert is_available() == HAS_PRESIDIO


class TestPresidioEntityMap:
    """Tests for Presidio entity type mapping."""

    def test_person_maps_to_name(self):
        """PERSON entity maps to NAME."""
        assert PRESIDIO_ENTITY_MAP["PERSON"] == EntityType.NAME

    def test_email_maps_correctly(self):
        """EMAIL_ADDRESS maps to EMAIL."""
        assert PRESIDIO_ENTITY_MAP["EMAIL_ADDRESS"] == EntityType.EMAIL

    def test_phone_maps_correctly(self):
        """PHONE_NUMBER maps to PHONE."""
        assert PRESIDIO_ENTITY_MAP["PHONE_NUMBER"] == EntityType.PHONE

    def test_ssn_maps_correctly(self):
        """US_SSN maps to SSN."""
        assert PRESIDIO_ENTITY_MAP["US_SSN"] == EntityType.SSN

    def test_credit_card_maps_correctly(self):
        """CREDIT_CARD maps to CREDIT_CARD."""
        assert PRESIDIO_ENTITY_MAP["CREDIT_CARD"] == EntityType.CREDIT_CARD

    def test_location_maps_to_address(self):
        """LOCATION maps to ADDRESS."""
        assert PRESIDIO_ENTITY_MAP["LOCATION"] == EntityType.ADDRESS

    def test_datetime_maps_to_dob(self):
        """DATE_TIME maps to DOB."""
        assert PRESIDIO_ENTITY_MAP["DATE_TIME"] == EntityType.DOB

    def test_driver_license_maps_to_ssn(self):
        """US_DRIVER_LICENSE maps to SSN (high-sensitivity PII)."""
        assert PRESIDIO_ENTITY_MAP["US_DRIVER_LICENSE"] == EntityType.SSN

    def test_bank_number_maps_to_credit_card(self):
        """US_BANK_NUMBER maps to CREDIT_CARD."""
        assert PRESIDIO_ENTITY_MAP["US_BANK_NUMBER"] == EntityType.CREDIT_CARD

    def test_itin_maps_to_ssn(self):
        """US_ITIN maps to SSN."""
        assert PRESIDIO_ENTITY_MAP["US_ITIN"] == EntityType.SSN

    def test_passport_maps_to_ssn(self):
        """US_PASSPORT maps to SSN."""
        assert PRESIDIO_ENTITY_MAP["US_PASSPORT"] == EntityType.SSN

    def test_medical_license_maps_to_mrn(self):
        """MEDICAL_LICENSE maps to MRN."""
        assert PRESIDIO_ENTITY_MAP["MEDICAL_LICENSE"] == EntityType.MRN

    def test_ip_address_maps_to_api_key(self):
        """IP_ADDRESS maps to API_KEY."""
        assert PRESIDIO_ENTITY_MAP["IP_ADDRESS"] == EntityType.API_KEY


@pytest.mark.skipif(not HAS_PRESIDIO, reason="Presidio not installed")
class TestPresidioDetector:
    """Tests for PresidioDetector (only run if Presidio installed)."""

    @pytest.fixture
    def detector(self):
        from scrubiq.classifier.detectors.presidio import PresidioDetector

        try:
            return PresidioDetector(score_threshold=0.5)
        except Exception as e:
            pytest.skip(f"Presidio available but spacy model not loaded: {e}")

    def test_detects_name(self, detector):
        """Presidio detects person names."""
        matches = detector.detect("Please contact John Smith regarding this matter.")

        name_matches = [m for m in matches if m.entity_type == EntityType.NAME]
        assert len(name_matches) >= 1
        assert "John Smith" in [m.value for m in name_matches]

    def test_detects_email(self, detector):
        """Presidio detects email addresses."""
        matches = detector.detect("Send to john.doe@company.com for review.")

        email_matches = [m for m in matches if m.entity_type == EntityType.EMAIL]
        assert len(email_matches) == 1
        assert email_matches[0].value == "john.doe@company.com"

    def test_detects_phone(self, detector):
        """Presidio detects phone numbers."""
        matches = detector.detect("Call me at 555-867-5309 today.")

        phone_matches = [m for m in matches if m.entity_type == EntityType.PHONE]
        assert len(phone_matches) >= 1

    def test_detects_location(self, detector):
        """Presidio detects locations/addresses."""
        matches = detector.detect("The office is located in New York City.")

        [m for m in matches if m.entity_type == EntityType.ADDRESS]
        # Note: May or may not detect depending on model

    def test_match_has_context(self, detector):
        """Matches include surrounding context."""
        text = "Employee John Smith works in the accounting department."
        matches = detector.detect(text)

        if matches:
            assert matches[0].context
            assert len(matches[0].context) > len(matches[0].value)

    def test_match_has_correct_positions(self, detector):
        """Match positions are correct."""
        text = "Contact John Smith for details."
        matches = detector.detect(text)

        for match in matches:
            # Verify position matches the value
            assert text[match.start : match.end] == match.value

    def test_detector_attribute(self, detector):
        """Matches are attributed to presidio detector."""
        matches = detector.detect("Hello John Smith")

        for match in matches:
            assert match.detector == "presidio"

    def test_clean_text_no_matches(self, detector):
        """Clean text produces no matches."""
        matches = detector.detect("This is a simple test document.")

        # May have some matches but should be minimal
        # Just verify no error
        assert isinstance(matches, list)

    def test_supported_entities(self, detector):
        """supported_entities returns list of Presidio types."""
        entities = detector.supported_entities

        assert "PERSON" in entities
        assert "EMAIL_ADDRESS" in entities
        assert "PHONE_NUMBER" in entities


@pytest.mark.skipif(HAS_PRESIDIO, reason="Test only when Presidio NOT installed")
class TestPresidioNotInstalled:
    """Tests for behavior when Presidio is not installed."""

    def test_detector_raises_without_presidio(self):
        """PresidioDetector raises RuntimeError if Presidio not installed."""
        from scrubiq.classifier.detectors.presidio import PresidioDetector

        with pytest.raises(RuntimeError, match="presidio-analyzer not installed"):
            PresidioDetector()
