"""TP/FP Classifier model for filtering false positives.

This module provides:
1. TPFPClassifier - wraps SetFit for training and inference
2. Integration with the classification pipeline
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union
import json

from .data import TrainingExample


# Check for SetFit availability
try:
    from setfit import SetFitModel, SetFitTrainer
    from sentence_transformers.losses import CosineSimilarityLoss

    HAS_SETFIT = True
except ImportError:
    HAS_SETFIT = False
    SetFitModel = None
    SetFitTrainer = None

# Check for datasets
try:
    from datasets import Dataset

    HAS_DATASETS = True
except ImportError:
    HAS_DATASETS = False
    Dataset = None


@dataclass
class FilterResult:
    """Result of TP/FP classification."""

    is_true_positive: bool
    confidence: float

    @property
    def is_false_positive(self) -> bool:
        return not self.is_true_positive


class TPFPClassifier:
    """
    Classifier for distinguishing true positives from false positives.

    Uses SetFit (few-shot learning) to learn from examples.
    Can work with as few as 50 examples per class.

    Training:
        classifier = TPFPClassifier()
        classifier.train(examples)
        classifier.save("./models/tpfp-v1")

    Inference:
        classifier = TPFPClassifier.load("./models/tpfp-v1")
        result = classifier.predict("[SSN] found in test file")
        if result.is_false_positive:
            print("Filtered out")

    Integration with scanner:
        # In ClassifierPipeline
        for match in matches:
            context = self._format_context(match)
            result = self.tpfp.predict(context)
            match.is_false_positive = result.is_false_positive
    """

    # Default base model - small but effective
    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(
        self,
        model_path: Optional[str] = None,
        base_model: str = DEFAULT_MODEL,
    ):
        """
        Initialize classifier.

        Args:
            model_path: Path to trained model (None = untrained)
            base_model: Base sentence transformer for training
        """
        self.base_model = base_model
        self.model: Optional[SetFitModel] = None
        self.model_path = model_path

        if model_path:
            self.load(model_path)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "TPFPClassifier":
        """Load a trained model."""
        if not HAS_SETFIT:
            raise ImportError("setfit required. Install with: pip install setfit")

        path = Path(path)
        instance = cls()
        instance.model = SetFitModel.from_pretrained(str(path))
        instance.model_path = str(path)

        # Load metadata if exists
        meta_path = path / "scrubiq_meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                instance._metadata = json.load(f)

        return instance

    def save(self, path: Union[str, Path]):
        """Save trained model."""
        if self.model is None:
            raise ValueError("No model to save. Train first.")

        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        self.model.save_pretrained(str(path))

        # Save metadata
        meta = {
            "base_model": self.base_model,
            "version": "1.0.0",
        }
        with open(path / "scrubiq_meta.json", "w") as f:
            json.dump(meta, f, indent=2)

        self.model_path = str(path)

    def train(
        self,
        examples: list[TrainingExample],
        num_iterations: int = 20,
        batch_size: int = 16,
        show_progress: bool = True,
    ) -> dict:
        """
        Train the TP/FP classifier.

        Args:
            examples: Training examples with text and label
            num_iterations: Number of contrastive pairs per example
            batch_size: Training batch size
            show_progress: Show progress bar

        Returns:
            Training metrics dict
        """
        if not HAS_SETFIT:
            raise ImportError("setfit required for training. Install with: pip install setfit")
        if not HAS_DATASETS:
            raise ImportError("datasets required for training. Install with: pip install datasets")

        # Convert to HuggingFace Dataset
        texts = [ex.text for ex in examples]
        labels = [ex.label for ex in examples]

        dataset = Dataset.from_dict(
            {
                "text": texts,
                "label": labels,
            }
        )

        # Split train/eval (90/10)
        split = dataset.train_test_split(test_size=0.1, seed=42)
        train_ds = split["train"]
        eval_ds = split["test"]

        print(f"Training on {len(train_ds)} examples, eval on {len(eval_ds)}")
        print(f"  True positives: {sum(labels)}")
        print(f"  False positives: {len(labels) - sum(labels)}")

        # Initialize model
        self.model = SetFitModel.from_pretrained(self.base_model)

        # Create trainer
        trainer = SetFitTrainer(
            model=self.model,
            train_dataset=train_ds,
            eval_dataset=eval_ds,
            loss_class=CosineSimilarityLoss,
            num_iterations=num_iterations,
            batch_size=batch_size,
            show_progress_bar=show_progress,
        )

        # Train
        print("\nTraining...")
        trainer.train()

        # Evaluate
        print("\nEvaluating...")
        metrics = trainer.evaluate()

        print("\nResults:")
        print(f"  Accuracy: {metrics.get('accuracy', 0):.1%}")

        return metrics

    def predict(self, text: str) -> FilterResult:
        """
        Predict if text represents a true positive or false positive.

        Args:
            text: Context with entity replaced by [TOKEN]

        Returns:
            FilterResult with is_true_positive and confidence
        """
        if self.model is None:
            raise ValueError("No model loaded. Train or load a model first.")

        # Get prediction
        prediction = self.model.predict([text])[0]

        # Get probabilities if available
        try:
            probs = self.model.predict_proba([text])[0]
            confidence = max(probs)
        except (AttributeError, NotImplementedError):
            confidence = 1.0 if prediction in [0, 1] else 0.5

        return FilterResult(
            is_true_positive=bool(prediction == 1),
            confidence=float(confidence),
        )

    def predict_batch(self, texts: list[str]) -> list[FilterResult]:
        """Predict multiple texts at once (faster)."""
        if self.model is None:
            raise ValueError("No model loaded. Train or load a model first.")

        predictions = self.model.predict(texts)

        try:
            probs = self.model.predict_proba(texts)
            confidences = [max(p) for p in probs]
        except (AttributeError, NotImplementedError):
            confidences = [1.0] * len(predictions)

        return [
            FilterResult(
                is_true_positive=bool(pred == 1),
                confidence=float(conf),
            )
            for pred, conf in zip(predictions, confidences)
        ]

    def format_match_context(
        self,
        context: str,
        value: str,
        entity_type: str,
    ) -> str:
        """
        Format a match's context for prediction.

        Replaces the entity value with [TOKEN] to match training format.

        Args:
            context: Text surrounding the match
            value: The matched entity value
            entity_type: Type of entity (ssn, email, etc.)

        Returns:
            Formatted string ready for predict()
        """
        token = f"[{entity_type.upper()}]"
        return context.replace(value, token)


def is_available() -> bool:
    """Check if training dependencies are available."""
    return HAS_SETFIT and HAS_DATASETS
