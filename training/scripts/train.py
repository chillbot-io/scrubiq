#!/usr/bin/env python
"""
Train the TP/FP classifier.

Usage:
    # First time: Download Nemotron-PII dataset
    python -m scrubiq.training.scripts.download_data
    
    # Train the model
    python -m scrubiq.training.scripts.train
    
    # Or with custom settings
    python -m scrubiq.training.scripts.train \
        --nemotron-examples 10000 \
        --fp-per-type 200 \
        --output ./models/tpfp-v1
"""

import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Train the TP/FP classifier for scrubIQ"
    )
    parser.add_argument(
        "--nemotron-examples",
        type=int,
        default=5000,
        help="Max examples from Nemotron-PII (default: 5000)"
    )
    parser.add_argument(
        "--fp-per-type",
        type=int,
        default=100,
        help="False positive examples per entity type (default: 100)"
    )
    parser.add_argument(
        "--include-feedback",
        action="store_true",
        default=True,
        help="Include user review feedback (default: True)"
    )
    parser.add_argument(
        "--no-feedback",
        action="store_true",
        help="Exclude user review feedback"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./models/tpfp-v1",
        help="Output directory for trained model"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=20,
        help="Training iterations (default: 20)"
    )
    parser.add_argument(
        "--data-only",
        action="store_true",
        help="Only prepare data, don't train"
    )
    
    args = parser.parse_args()
    
    # Import here to catch missing dependencies early
    try:
        from scrubiq.training.data import prepare_training_dataset
        from scrubiq.training.model import TPFPClassifier, is_available
    except ImportError as e:
        print(f"Error importing training modules: {e}")
        print("\nMake sure you have the required dependencies:")
        print("  pip install setfit datasets")
        sys.exit(1)
    
    if not is_available():
        print("Training dependencies not available.")
        print("Install with: pip install setfit datasets")
        sys.exit(1)
    
    # Prepare training data
    print("=" * 60)
    print("STEP 1: Preparing Training Data")
    print("=" * 60)
    
    data_path = Path(args.output) / "training_data.jsonl"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    
    include_feedback = args.include_feedback and not args.no_feedback
    
    examples = prepare_training_dataset(
        nemotron_examples=args.nemotron_examples,
        fp_per_type=args.fp_per_type,
        include_user_feedback=include_feedback,
        output_path=str(data_path),
    )
    
    if args.data_only:
        print(f"\nData prepared at: {data_path}")
        print("Run without --data-only to train.")
        sys.exit(0)
    
    # Train
    print("\n" + "=" * 60)
    print("STEP 2: Training TP/FP Classifier")
    print("=" * 60)
    
    classifier = TPFPClassifier()
    metrics = classifier.train(
        examples=examples,
        num_iterations=args.iterations,
        show_progress=True,
    )
    
    # Save
    print("\n" + "=" * 60)
    print("STEP 3: Saving Model")
    print("=" * 60)
    
    classifier.save(args.output)
    print(f"Model saved to: {args.output}")
    
    # Test
    print("\n" + "=" * 60)
    print("STEP 4: Quick Test")
    print("=" * 60)
    
    test_cases = [
        ("[SSN] found in employee payroll record", "Real PII"),
        ("Test SSN: [SSN] for validation only", "Test data"),
        ("Contact [EMAIL] for more information", "Could be either"),
        ("Example: [SSN] (do not use)", "Test data"),
        ("Patient [NAME] admitted with symptoms", "Real PII"),
    ]
    
    print("\nTest predictions:")
    for text, expected in test_cases:
        result = classifier.predict(text)
        label = "TP" if result.is_true_positive else "FP"
        print(f"  {label} ({result.confidence:.0%}): {text[:50]}...")
        print(f"      Expected: {expected}")
    
    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)
    print(f"\nTo use this model, add to your code:")
    print(f"  from scrubiq.training import TPFPClassifier")
    print(f"  classifier = TPFPClassifier.load('{args.output}')")
    print(f"  result = classifier.predict('[SSN] in context...')")


if __name__ == "__main__":
    main()
