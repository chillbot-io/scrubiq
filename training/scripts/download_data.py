#!/usr/bin/env python
"""
Download Nemotron-PII dataset for training.

This downloads the dataset from HuggingFace and saves it locally
for faster repeated access.

Usage:
    python -m scrubiq.training.scripts.download_data
    
    # Or specify output directory
    python -m scrubiq.training.scripts.download_data --output ./data/nemotron
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Download Nemotron-PII dataset"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./nemotron_pii",
        help="Output directory (default: ./nemotron_pii)"
    )
    
    args = parser.parse_args()
    
    # Check dependencies
    try:
        from datasets import load_dataset
    except ImportError:
        print("Error: datasets library required")
        print("Install with: pip install datasets")
        sys.exit(1)
    
    print("Downloading Nemotron-PII dataset from HuggingFace...")
    print("This may take a few minutes on first download.\n")
    
    try:
        ds = load_dataset("nvidia/Nemotron-PII")
    except Exception as e:
        print(f"Error downloading dataset: {e}")
        print("\nMake sure you have internet access and try again.")
        sys.exit(1)
    
    # Show info
    print("Dataset info:")
    print(f"  Splits: {list(ds.keys())}")
    for split_name, split_data in ds.items():
        print(f"  {split_name}: {len(split_data)} records")
    
    # Show sample
    print("\nSample record:")
    sample = ds['train'][0]
    print(f"  Text: {sample.get('text', '')[:100]}...")
    print(f"  Entities: {len(sample.get('entities', []))} found")
    if sample.get('entities'):
        ent = sample['entities'][0]
        print(f"    First: {ent.get('type')} = {ent.get('value', '')[:30]}...")
    
    # Save locally
    print(f"\nSaving to {args.output}...")
    ds.save_to_disk(args.output)
    print("Done!")
    
    print(f"\nDataset saved to: {args.output}")
    print("You can now run training with:")
    print("  python -m scrubiq.training.scripts.train")


if __name__ == "__main__":
    main()
