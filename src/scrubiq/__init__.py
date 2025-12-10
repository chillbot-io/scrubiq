"""scrubIQ - Find and protect sensitive data."""

__version__ = "0.1.0"

from scrubiq.scanner.results import (
    Confidence,
    EntityType,
    FileResult,
    LabelRecommendation,
    Match,
    ScanResult,
)
from scrubiq.scanner.scanner import Scanner
from scrubiq.storage import FindingsDatabase, AuditLog, AuditAction
from scrubiq.reporter import generate_html_report
from scrubiq.review import Verdict, ReviewSample, ReviewStorage
from scrubiq.classifier.pipeline import ClassifierPipeline, ClassificationResult
from scrubiq.auth import GraphClient, Config, AzureSetupWizard, ManualSetupGuide
from scrubiq.labeler import Labeler, LabelResult, LabelMapping, AIPClient

__all__ = [
    # Scanner
    "Scanner",
    # Classifier
    "ClassifierPipeline",
    "ClassificationResult",
    # Results
    "Confidence",
    "EntityType",
    "FileResult",
    "LabelRecommendation",
    "Match",
    "ScanResult",
    # Storage
    "FindingsDatabase",
    "AuditLog",
    "AuditAction",
    # Reporter
    "generate_html_report",
    # Review
    "Verdict",
    "ReviewSample",
    "ReviewStorage",
    # Auth & Config
    "GraphClient",
    "Config",
    "AzureSetupWizard",
    "ManualSetupGuide",
    # Labeling
    "Labeler",
    "LabelResult",
    "LabelMapping",
    "AIPClient",
]
