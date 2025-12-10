"""Detection modules for different entity types."""

from .regex import RegexDetector
from .presidio import HAS_PRESIDIO, is_available as presidio_available

# Only export PresidioDetector if available
if HAS_PRESIDIO:
    from .presidio import PresidioDetector

    __all__ = ["RegexDetector", "PresidioDetector", "HAS_PRESIDIO", "presidio_available"]
else:
    __all__ = ["RegexDetector", "HAS_PRESIDIO", "presidio_available"]
