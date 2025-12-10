"""Training data format and loaders for TP/FP classifier.

The TP/FP classifier learns to distinguish:
- True Positives (TP): Real PII that should be flagged
- False Positives (FP): Test data, examples, or incorrect matches

Training data format:
    {
        "text": "[SSN] found in employee record for payroll",  # Context with entity replaced by token
        "label": 1,  # 1 = TP (real PII), 0 = FP (false positive)
        "entity_type": "ssn",
        "source": "nemotron"  # Where the example came from
    }
"""

from dataclasses import dataclass, asdict
from typing import Iterator, Optional
from enum import Enum
import json
import random


class Label(Enum):
    """Training labels."""

    FALSE_POSITIVE = 0  # Not real PII
    TRUE_POSITIVE = 1  # Real PII


@dataclass
class TrainingExample:
    """Single training example for TP/FP classifier."""

    # Context with entity replaced by [TOKEN] (e.g., [SSN], [NAME])
    text: str

    # 1 = true positive, 0 = false positive
    label: int

    # Entity type being classified
    entity_type: str

    # Where this example came from
    source: str = "unknown"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TrainingExample":
        return cls(**d)

    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_jsonl(cls, line: str) -> "TrainingExample":
        return cls.from_dict(json.loads(line))


# Map Nemotron entity types to our types
NEMOTRON_ENTITY_MAP = {
    "SSN": "ssn",
    "SOCIAL_SECURITY_NUMBER": "ssn",
    "NAME": "name",
    "PERSON_NAME": "name",
    "FIRST_NAME": "name",
    "LAST_NAME": "name",
    "EMAIL": "email",
    "EMAIL_ADDRESS": "email",
    "PHONE": "phone",
    "PHONE_NUMBER": "phone",
    "ADDRESS": "address",
    "STREET_ADDRESS": "address",
    "CREDIT_CARD": "credit_card",
    "CREDIT_CARD_NUMBER": "credit_card",
    "MRN": "mrn",
    "MEDICAL_RECORD_NUMBER": "mrn",
    "DOB": "dob",
    "DATE_OF_BIRTH": "dob",
    "IP_ADDRESS": "api_key",
    "ACCOUNT_NUMBER": "credit_card",
    "HEALTH_PLAN_ID": "health_plan_id",
}


def load_nemotron_pii(
    max_examples: Optional[int] = None,
    entity_types: Optional[list[str]] = None,
) -> Iterator[TrainingExample]:
    """
    Load Nemotron-PII dataset and convert to training format.

    Args:
        max_examples: Maximum examples to load (None = all)
        entity_types: Filter to specific entity types (None = all)

    Yields:
        TrainingExample for each entity in the dataset

    Usage:
        # First, download on your machine:
        # pip install datasets
        #
        # from datasets import load_dataset
        # ds = load_dataset("nvidia/Nemotron-PII")
        # ds.save_to_disk("./nemotron_pii")

        for example in load_nemotron_pii(max_examples=1000):
            print(example.text, example.label)
    """
    try:
        from datasets import load_dataset
    except ImportError:
        raise ImportError("datasets library required. Install with: pip install datasets")

    # Try loading from disk first (faster), fall back to HuggingFace
    try:
        from datasets import load_from_disk

        ds = load_from_disk("./nemotron_pii")["train"]
    except (FileNotFoundError, KeyError, Exception):
        ds = load_dataset("nvidia/Nemotron-PII", split="train")

    count = 0
    for record in ds:
        text = record.get("text", "")
        entities = record.get("entities", [])

        for entity in entities:
            ent_type = entity.get("type", "")
            our_type = NEMOTRON_ENTITY_MAP.get(ent_type, ent_type.lower())

            # Filter by entity type if specified
            if entity_types and our_type not in entity_types:
                continue

            # Get entity position and value
            start = entity.get("start", 0)
            end = entity.get("end", 0)
            entity.get("value", text[start:end])

            # Extract context (100 chars around entity)
            ctx_start = max(0, start - 50)
            ctx_end = min(len(text), end + 50)
            context = text[ctx_start:ctx_end]

            # Replace entity with token
            token = f"[{our_type.upper()}]"
            entity_in_context_start = start - ctx_start
            entity_in_context_end = end - ctx_start

            anonymized = context[:entity_in_context_start] + token + context[entity_in_context_end:]

            yield TrainingExample(
                text=anonymized,
                label=Label.TRUE_POSITIVE.value,  # Nemotron entities are real PII
                entity_type=our_type,
                source="nemotron",
            )

            count += 1
            if max_examples and count >= max_examples:
                return


# False positive templates for different entity types
FP_TEMPLATES = {
    "ssn": [
        "Test SSN: [SSN] for validation purposes only",
        "Example: [SSN] (do not use in production)",
        "Use [SSN] as a sample in your unit tests",
        "Demo data: SSN=[SSN], not a real number",
        "Placeholder SSN [SSN] for the form mockup",
        "SSN format example: [SSN]",
        "For testing, try SSN [SSN]",
        "Invalid test SSN: [SSN]",
    ],
    "email": [
        "Contact us at [EMAIL] for support",
        "Example: [EMAIL] (replace with your email)",
        "Send test emails to [EMAIL]",
        "Placeholder: [EMAIL]",
        "For demo purposes: [EMAIL]",
        "Template variable: [EMAIL]",
        "QA testing email: [EMAIL]",
    ],
    "phone": [
        "Call our support line at [PHONE]",
        "Fax number: [PHONE]",
        "For assistance, dial [PHONE]",
        "Test phone: [PHONE]",
        "Example phone number: [PHONE]",
        "Office: [PHONE]",
        "Toll-free: [PHONE]",
    ],
    "credit_card": [
        "Test card: [CREDIT_CARD] for sandbox",
        "Example: [CREDIT_CARD] (Visa test number)",
        "Use [CREDIT_CARD] in development",
        "Demo card number: [CREDIT_CARD]",
        "For testing payments: [CREDIT_CARD]",
    ],
    "name": [
        "Example: [NAME] as a placeholder",
        "Template: Dear [NAME],",
        "Replace [NAME] with actual recipient",
        "Test user: [NAME]",
        "Sample: [NAME] (not a real person)",
    ],
    "address": [
        "Example address: [ADDRESS]",
        "Ship to: [ADDRESS] (placeholder)",
        "Test address: [ADDRESS]",
        "For demo: [ADDRESS]",
    ],
}


def generate_false_positives(
    n_per_type: int = 50,
    entity_types: Optional[list[str]] = None,
) -> Iterator[TrainingExample]:
    """
    Generate synthetic false positive examples.

    These teach the model to recognize test/example data patterns.

    Args:
        n_per_type: Number of FP examples per entity type
        entity_types: Which types to generate (None = all)

    Yields:
        TrainingExample with label=0 (false positive)
    """
    types_to_use = entity_types or list(FP_TEMPLATES.keys())

    for ent_type in types_to_use:
        templates = FP_TEMPLATES.get(ent_type, [])
        if not templates:
            continue

        for i in range(n_per_type):
            template = random.choice(templates)

            yield TrainingExample(
                text=template,
                label=Label.FALSE_POSITIVE.value,
                entity_type=ent_type,
                source="synthetic_fp",
            )


def load_user_feedback(feedback_path: str = None) -> Iterator[TrainingExample]:
    """
    Load training examples from user review feedback.

    These are the most valuable - real FPs from real scans.

    Args:
        feedback_path: Path to reviews.jsonl (default: ~/.scrubiq/reviews.jsonl)

    Yields:
        TrainingExample from user verdicts
    """
    from pathlib import Path

    if feedback_path is None:
        # Default path from ReviewStorage
        import os

        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA", "~"))
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share"))
        feedback_path = base.expanduser() / "scrubiq" / "reviews.jsonl"
    else:
        feedback_path = Path(feedback_path)

    if not feedback_path.exists():
        return

    with open(feedback_path) as f:
        for line in f:
            record = json.loads(line)

            # Convert verdict to label
            verdict = record.get("verdict", "")
            if verdict == "TP":
                label = Label.TRUE_POSITIVE.value
            elif verdict == "FP":
                label = Label.FALSE_POSITIVE.value
            else:
                continue  # Skip unknown verdicts

            yield TrainingExample(
                text=record.get("context", ""),
                label=label,
                entity_type=record.get("entity_type", "unknown"),
                source="user_feedback",
            )


def prepare_training_dataset(
    nemotron_examples: int = 5000,
    fp_per_type: int = 100,
    include_user_feedback: bool = True,
    output_path: Optional[str] = None,
) -> list[TrainingExample]:
    """
    Prepare complete training dataset.

    Combines:
    1. Nemotron-PII (true positives)
    2. Synthetic false positives
    3. User feedback (if available)

    Args:
        nemotron_examples: Max TP examples from Nemotron
        fp_per_type: FP examples per entity type
        include_user_feedback: Include user review verdicts
        output_path: Optional path to save as JSONL

    Returns:
        List of TrainingExample
    """
    examples = []

    # Load true positives from Nemotron
    print(f"Loading up to {nemotron_examples} examples from Nemotron-PII...")
    for ex in load_nemotron_pii(max_examples=nemotron_examples):
        examples.append(ex)
    print(f"  Loaded {len(examples)} true positives")

    # Generate false positives
    print("Generating synthetic false positives...")
    fp_count = 0
    for ex in generate_false_positives(n_per_type=fp_per_type):
        examples.append(ex)
        fp_count += 1
    print(f"  Generated {fp_count} false positives")

    # Load user feedback
    if include_user_feedback:
        print("Loading user feedback...")
        user_count = 0
        for ex in load_user_feedback():
            examples.append(ex)
            user_count += 1
        print(f"  Loaded {user_count} from user reviews")

    # Shuffle
    random.shuffle(examples)

    # Save if path provided
    if output_path:
        with open(output_path, "w") as f:
            for ex in examples:
                f.write(ex.to_jsonl() + "\n")
        print(f"Saved {len(examples)} examples to {output_path}")

    # Summary
    tp_count = sum(1 for e in examples if e.label == 1)
    fp_count = sum(1 for e in examples if e.label == 0)
    print(f"\nTotal: {len(examples)} examples ({tp_count} TP, {fp_count} FP)")

    return examples
