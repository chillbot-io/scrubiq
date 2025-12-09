"""Regex-based pattern detection for sensitive data."""

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from scrubiq.scanner.results import EntityType, Match


@dataclass
class Pattern:
    """A detection pattern with metadata."""

    name: str
    entity_type: EntityType
    regex: re.Pattern
    confidence_base: float
    validator: Optional[Callable[[str], bool]] = None
    test_patterns: list[str] = field(default_factory=list)


# =============================================================================
# Validators
# =============================================================================


def validate_ssn(value: str) -> bool:
    """
    Validate SSN format and basic rules.

    Rules:
    - Area number (first 3): cannot be 000, 666, or 900-999
    - Group number (middle 2): cannot be 00
    - Serial number (last 4): cannot be 0000
    """
    digits = re.sub(r"[^\d]", "", value)
    if len(digits) != 9:
        return False

    area = int(digits[:3])
    group = int(digits[3:5])
    serial = int(digits[5:])

    # Invalid area numbers
    if area == 0 or area == 666 or area >= 900:
        return False

    # Invalid group number
    if group == 0:
        return False

    # Invalid serial number
    if serial == 0:
        return False

    return True


def luhn_check(value: str) -> bool:
    """
    Luhn algorithm for credit card validation.

    Returns True if the number passes the Luhn checksum.
    """
    digits = [int(d) for d in re.sub(r"[^\d]", "", value)]

    if len(digits) < 13 or len(digits) > 19:
        return False

    # Luhn algorithm
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]

    checksum = sum(odd_digits)
    for d in even_digits:
        checksum += sum(divmod(d * 2, 10))

    return checksum % 10 == 0


# =============================================================================
# Pattern Definitions
# =============================================================================

SSN_PATTERN = Pattern(
    name="us_ssn",
    entity_type=EntityType.SSN,
    regex=re.compile(
        r"\b"
        r"(?!000|666|9\d{2})"  # Area cannot be 000, 666, 900-999
        r"([0-8]\d{2}|7([0-6]\d|7[012]))"  # Valid area numbers
        r"[-\s]?"
        r"(?!00)\d{2}"  # Group cannot be 00
        r"[-\s]?"
        r"(?!0000)\d{4}"  # Serial cannot be 0000
        r"\b"
    ),
    confidence_base=0.75,
    validator=validate_ssn,
    test_patterns=[
        "123-45-6789",
        "000-00-0000",
        "111-11-1111",
        "222-22-2222",
        "333-33-3333",
        "444-44-4444",
        "555-55-5555",
        "999-99-9999",
        "123-12-1234",
        "987-65-4321",
    ],
)

CREDIT_CARD_PATTERN = Pattern(
    name="credit_card",
    entity_type=EntityType.CREDIT_CARD,
    regex=re.compile(
        r"\b(?:"
        r"4[0-9]{12}(?:[0-9]{3})?"  # Visa (13 or 16 digits)
        r"|5[1-5][0-9]{14}"  # Mastercard
        r"|3[47][0-9]{13}"  # Amex
        r"|6(?:011|5[0-9]{2})[0-9]{12}"  # Discover
        r"|3(?:0[0-5]|[68][0-9])[0-9]{11}"  # Diners Club
        r")\b"
    ),
    confidence_base=0.70,
    validator=luhn_check,
    test_patterns=[
        "4111111111111111",  # Visa test
        "4111-1111-1111-1111",
        "5500000000000004",  # MC test
        "340000000000009",  # Amex test
        "4242424242424242",  # Stripe test
        "5555555555554444",  # MC test
        "378282246310005",  # Amex test
    ],
)

EMAIL_PATTERN = Pattern(
    name="email",
    entity_type=EntityType.EMAIL,
    regex=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    confidence_base=0.90,
    test_patterns=[
        "test@example.com",
        "test@example.org",
        "user@test.com",
        "noreply@example.com",
        "no-reply@example.com",
        "admin@localhost",
        "foo@bar.test",
        "example@example.com",
    ],
)

PHONE_PATTERN = Pattern(
    name="us_phone",
    entity_type=EntityType.PHONE,
    regex=re.compile(
        r"\b"
        r"(?:\+1[-.\s]?)?"  # Optional +1 country code
        r"(?:\(?\d{3}\)?[-.\s]?)"  # Area code
        r"\d{3}[-.\s]?"  # Exchange
        r"\d{4}"  # Subscriber
        r"\b"
    ),
    confidence_base=0.65,
    test_patterns=[
        "555-555-5555",
        "555-123-4567",
        "(555) 555-5555",
        "555.555.5555",
        "123-456-7890",
        "000-000-0000",
    ],
)

# All patterns to check
ALL_PATTERNS = [
    SSN_PATTERN,
    CREDIT_CARD_PATTERN,
    EMAIL_PATTERN,
    PHONE_PATTERN,
]


# =============================================================================
# Detector Class
# =============================================================================


class RegexDetector:
    """
    Detect sensitive data using regex patterns.

    Usage:
        detector = RegexDetector()
        matches = detector.detect("My SSN is 078-05-1120")
        # Returns list of Match objects
    """

    def __init__(self, patterns: Optional[list[Pattern]] = None):
        """
        Initialize detector with patterns.

        Args:
            patterns: List of Pattern objects to use. Defaults to ALL_PATTERNS.
        """
        self.patterns = patterns if patterns is not None else ALL_PATTERNS

    def detect(self, text: str) -> list[Match]:
        """
        Find all pattern matches in text.

        Args:
            text: The text to scan for sensitive data.

        Returns:
            List of Match objects for each detection.
        """
        matches = []

        for pattern in self.patterns:
            for m in pattern.regex.finditer(text):
                value = m.group()

                # Run validator if present
                if pattern.validator and not pattern.validator(value):
                    continue

                # Check if this looks like test/example data
                is_test = self._is_test_data(value, pattern.test_patterns)

                # Get surrounding context (50 chars each side)
                ctx_start = max(0, m.start() - 50)
                ctx_end = min(len(text), m.end() + 50)
                context = text[ctx_start:ctx_end]

                matches.append(
                    Match(
                        entity_type=pattern.entity_type,
                        value=value,
                        start=m.start(),
                        end=m.end(),
                        confidence=pattern.confidence_base,
                        detector="regex",
                        context=context,
                        is_test_data=is_test,
                    )
                )

        return matches

    def _is_test_data(self, value: str, test_patterns: list[str]) -> bool:
        """Check if value matches known test/example patterns."""
        # Normalize for comparison (remove separators)
        normalized = re.sub(r"[-.\s()]", "", value.lower())

        for test in test_patterns:
            test_normalized = re.sub(r"[-.\s()]", "", test.lower())
            if normalized == test_normalized:
                return True

        return False
