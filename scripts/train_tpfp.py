#!/usr/bin/env python3
"""
scrubIQ Training Pipeline - Complete Walkthrough

This script demonstrates the complete training flow:
1. Download training data (Nemotron-PII)
2. Prepare dataset (TPs + synthetic FPs + user feedback)
3. Train SetFit model
4. Evaluate and save

Run this script:
    python scripts/train_tpfp.py

Prerequisites:
    pip install setfit datasets sentence-transformers

The trained model will be saved to ~/.local/share/scrubiq/models/tpfp-v1/
"""

import sys
from pathlib import Path

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def step_1_download_data():
    """
    Step 1: Download Nemotron-PII from HuggingFace
    
    This is NVIDIA's high-quality PII dataset:
    - 100k records
    - 55+ entity types (SSN, MRN, names, etc.)
    - Healthcare, finance, legal domains
    - Span-level annotations
    - CC-BY-4.0 license (commercial OK)
    """
    print("=" * 60)
    print("STEP 1: Download Training Data")
    print("=" * 60)
    
    from datasets import load_dataset
    
    # Check if already downloaded
    nemotron_path = Path("./nemotron_pii")
    if nemotron_path.exists():
        print(f"✓ Nemotron-PII already downloaded at {nemotron_path}")
        return True
    
    print("Downloading nvidia/Nemotron-PII from HuggingFace...")
    print("(This is ~200MB and may take a few minutes)\n")
    
    try:
        ds = load_dataset("nvidia/Nemotron-PII")
        ds.save_to_disk(str(nemotron_path))
        print(f"✓ Saved to {nemotron_path}")
        print(f"  Records: {len(ds['train']):,}")
        return True
    except Exception as e:
        print(f"✗ Download failed: {e}")
        return False


def step_2_prepare_dataset(max_examples: int = 5000):
    """
    Step 2: Prepare training dataset
    
    Combines three data sources:
    
    1. Nemotron-PII (True Positives)
       - Real PII patterns from healthcare, finance, legal
       - "[SSN] found in employee record for John Smith"
       - Label: 1 (this IS real PII)
    
    2. Synthetic False Positives
       - Test data patterns we generate
       - "Test SSN: [SSN] for validation purposes"
       - Label: 0 (this is NOT real PII)
    
    3. User Feedback (from scrubiq review)
       - Real FPs from your actual scans
       - Most valuable training signal
       - Label: whatever you marked it as
    """
    print("\n" + "=" * 60)
    print("STEP 2: Prepare Training Dataset")
    print("=" * 60)
    
    from scrubiq.training.data import prepare_training_dataset
    
    examples = prepare_training_dataset(
        nemotron_examples=max_examples,
        fp_per_type=100,  # 100 FPs per entity type
        include_user_feedback=True,
    )
    
    return examples


def step_3_train_model(examples, iterations: int = 20):
    """
    Step 3: Train SetFit model
    
    SetFit is perfect for this task:
    - Works with small datasets (we have ~5000, need ~100)
    - Trains on CPU in minutes
    - ~100MB model size
    - No GPU required
    
    How it works:
    1. Start with pre-trained sentence transformer
       (already understands English semantics)
    
    2. Contrastive learning:
       - "these two are same class" → push embeddings closer
       - "these two are different" → push embeddings apart
    
    3. Train tiny classification head on top
       - Just logistic regression
       - Input: 384-dim embedding
       - Output: 0 (FP) or 1 (TP)
    """
    print("\n" + "=" * 60)
    print("STEP 3: Train TP/FP Classifier")
    print("=" * 60)
    
    from scrubiq.training.model import TPFPClassifier
    
    classifier = TPFPClassifier()
    
    metrics = classifier.train(
        examples,
        num_iterations=iterations,
        batch_size=16,
        show_progress=True,
    )
    
    return classifier, metrics


def step_4_evaluate(classifier, examples):
    """
    Step 4: Test the trained model
    
    Let's see it in action on some examples.
    """
    print("\n" + "=" * 60)
    print("STEP 4: Evaluate Model")
    print("=" * 60)
    
    # Test examples
    test_cases = [
        # True Positives (should predict 1)
        ("Employee [SSN] enrolled in health benefits", "TP"),
        ("Patient [NAME] admitted to room 302", "TP"),
        ("Please update billing for [CREDIT_CARD]", "TP"),
        
        # False Positives (should predict 0)
        ("Test SSN: [SSN] for QA validation", "FP"),
        ("Example: [EMAIL] (replace with your email)", "FP"),
        ("Use [CREDIT_CARD] in sandbox environment", "FP"),
    ]
    
    print("\nTesting on sample cases:\n")
    print(f"{'Context':<50} {'Expected':>10} {'Predicted':>10} {'Conf':>8}")
    print("-" * 80)
    
    correct = 0
    for context, expected in test_cases:
        result = classifier.predict(context)
        predicted = "TP" if result.is_true_positive else "FP"
        is_correct = predicted == expected
        correct += is_correct
        
        # Truncate context for display
        display_ctx = context[:47] + "..." if len(context) > 50 else context
        mark = "✓" if is_correct else "✗"
        
        print(f"{display_ctx:<50} {expected:>10} {predicted:>10} {result.confidence:>7.1%} {mark}")
    
    print("-" * 80)
    print(f"Accuracy on test cases: {correct}/{len(test_cases)} ({correct/len(test_cases):.0%})")


def step_5_save_model(classifier):
    """
    Step 5: Save the trained model
    
    The model is saved to:
    - Linux: ~/.local/share/scrubiq/models/tpfp-v1/
    - Windows: %LOCALAPPDATA%/scrubiq/models/tpfp-v1/
    
    It will be automatically loaded when you run scrubiq scan.
    """
    print("\n" + "=" * 60)
    print("STEP 5: Save Model")
    print("=" * 60)
    
    from scrubiq.storage.database import get_data_dir
    
    output_path = get_data_dir() / "models" / "tpfp-v1"
    
    classifier.save(output_path)
    print(f"✓ Model saved to: {output_path}")
    
    # Show what was saved
    print("\nSaved files:")
    for f in output_path.iterdir():
        size = f.stat().st_size
        if size > 1024 * 1024:
            size_str = f"{size / 1024 / 1024:.1f}MB"
        elif size > 1024:
            size_str = f"{size / 1024:.1f}KB"
        else:
            size_str = f"{size}B"
        print(f"  {f.name}: {size_str}")
    
    return output_path


def main():
    """Run the complete training pipeline."""
    print("\n" + "=" * 60)
    print("scrubIQ TP/FP Classifier Training")
    print("=" * 60)
    print("""
This script trains a model to distinguish:
- True Positives: Real PII that should be flagged
- False Positives: Test data, examples, wrong matches

The trained model will filter out false positives during scans.
""")
    
    # Check dependencies
    try:
        import setfit
        import datasets
        import sentence_transformers
    except ImportError as e:
        print("ERROR: Missing dependencies")
        print("\nInstall with:")
        print("  pip install setfit datasets sentence-transformers")
        sys.exit(1)
    
    # Run pipeline
    if not step_1_download_data():
        print("\nFailed to download data. Exiting.")
        sys.exit(1)
    
    examples = step_2_prepare_dataset(max_examples=5000)
    
    classifier, metrics = step_3_train_model(examples)
    
    step_4_evaluate(classifier, examples[:100])
    
    output_path = step_5_save_model(classifier)
    
    # Summary
    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)
    print(f"""
Summary:
  Training examples: {len(examples):,}
  Model accuracy:    {metrics.get('accuracy', 0):.1%}
  Model saved to:    {output_path}

Next steps:
  1. Run a scan:     scrubiq scan ./documents
  2. Review matches: scrubiq review <scan_id>
  3. Retrain:        python scripts/train_tpfp.py

The model improves with more user feedback!
""")


if __name__ == "__main__":
    main()
