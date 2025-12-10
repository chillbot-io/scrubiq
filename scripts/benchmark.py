#!/usr/bin/env python3
"""Benchmark scrubIQ detection accuracy.

Runs scrubIQ against a test corpus and measures:
- Precision (how many detections are correct)
- Recall (how many planted entities were found)
- F1 score
- False positive rate
- Processing speed

Usage:
    # Generate test corpus first
    python scripts/generate_test_corpus.py ./test_corpus --count 100
    
    # Run benchmark
    python scripts/benchmark.py ./test_corpus
    
    # Compare with/without Presidio
    python scripts/benchmark.py ./test_corpus --compare-presidio
"""

import argparse
import json
import time
import sys
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@dataclass
class BenchmarkResults:
    """Results from a benchmark run."""
    name: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Corpus stats
    total_files: int = 0
    files_with_planted_data: int = 0
    files_clean: int = 0
    files_test_data: int = 0
    
    # Detection stats
    files_with_detections: int = 0
    total_matches: int = 0
    real_matches: int = 0  # Excluding test data flags
    test_data_flagged: int = 0
    
    # By entity type
    by_entity: dict = field(default_factory=dict)
    
    # Performance
    scan_time_seconds: float = 0.0
    files_per_second: float = 0.0
    
    # Accuracy metrics (if ground truth available)
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    
    # Configuration
    presidio_enabled: bool = True
    
    def calculate_metrics(self):
        """Calculate precision, recall, F1."""
        if self.true_positives + self.false_positives > 0:
            self.precision = self.true_positives / (self.true_positives + self.false_positives)
        
        if self.true_positives + self.false_negatives > 0:
            self.recall = self.true_positives / (self.true_positives + self.false_negatives)
        
        if self.precision + self.recall > 0:
            self.f1_score = 2 * self.precision * self.recall / (self.precision + self.recall)
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "corpus": {
                "total_files": self.total_files,
                "files_with_planted_data": self.files_with_planted_data,
                "files_clean": self.files_clean,
                "files_test_data": self.files_test_data,
            },
            "detections": {
                "files_with_detections": self.files_with_detections,
                "total_matches": self.total_matches,
                "real_matches": self.real_matches,
                "test_data_flagged": self.test_data_flagged,
            },
            "by_entity": self.by_entity,
            "performance": {
                "scan_time_seconds": round(self.scan_time_seconds, 2),
                "files_per_second": round(self.files_per_second, 2),
            },
            "accuracy": {
                "true_positives": self.true_positives,
                "false_positives": self.false_positives,
                "false_negatives": self.false_negatives,
                "precision": round(self.precision, 4),
                "recall": round(self.recall, 4),
                "f1_score": round(self.f1_score, 4),
            },
            "config": {
                "presidio_enabled": self.presidio_enabled,
            },
        }


def load_manifest(corpus_path: Path) -> Optional[dict]:
    """Load corpus manifest if available."""
    manifest_path = corpus_path / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text())
    return None


def categorize_file(file_path: Path, corpus_path: Path) -> str:
    """Categorize a file based on its location."""
    # Ensure both paths are absolute for comparison
    file_path = file_path.resolve()
    corpus_path = corpus_path.resolve()
    relative = file_path.relative_to(corpus_path)
    parts = relative.parts
    
    if len(parts) > 1:
        category = parts[0]
        if category in ["hr", "finance", "medical"]:
            return "sensitive"
        elif category == "test_data":
            return "test_data"
        elif category == "general":
            return "clean"
    
    return "unknown"


def run_benchmark(
    corpus_path: Path,
    enable_presidio: bool = True,
    name: str = "benchmark",
) -> BenchmarkResults:
    """Run benchmark on a corpus."""
    from scrubiq import Scanner
    
    # Resolve path early
    corpus_path = corpus_path.resolve()
    
    results = BenchmarkResults(name=name, presidio_enabled=enable_presidio)
    
    # Load manifest for ground truth
    manifest = load_manifest(corpus_path)
    
    # Initialize scanner
    scanner = Scanner(enable_presidio=enable_presidio)
    
    # Time the scan
    start_time = time.time()
    scan_result = scanner.scan(str(corpus_path))
    end_time = time.time()
    
    results.scan_time_seconds = end_time - start_time
    results.total_files = scan_result.total_files
    results.files_with_detections = scan_result.files_with_matches
    results.total_matches = scan_result.total_matches
    
    if results.total_files > 0:
        results.files_per_second = results.total_files / results.scan_time_seconds
    
    # Analyze results by category
    for file_result in scan_result.files:
        category = categorize_file(file_result.path, corpus_path)
        
        if category == "sensitive":
            results.files_with_planted_data += 1
        elif category == "clean":
            results.files_clean += 1
        elif category == "test_data":
            results.files_test_data += 1
        
        # Count matches
        for match in file_result.matches:
            entity_type = match.entity_type.value
            
            if entity_type not in results.by_entity:
                results.by_entity[entity_type] = {"total": 0, "real": 0, "test_data": 0}
            
            results.by_entity[entity_type]["total"] += 1
            
            if match.is_test_data:
                results.by_entity[entity_type]["test_data"] += 1
                results.test_data_flagged += 1
            else:
                results.by_entity[entity_type]["real"] += 1
                results.real_matches += 1
    
    # Calculate accuracy metrics
    # True positives: detections in sensitive files (excluding test data flags)
    # False positives: detections in clean files
    # False negatives: sensitive files with no detections
    
    for file_result in scan_result.files:
        category = categorize_file(file_result.path, corpus_path)
        has_real_matches = any(not m.is_test_data for m in file_result.matches)
        
        if category == "sensitive":
            if has_real_matches:
                results.true_positives += 1
            else:
                results.false_negatives += 1
        elif category == "clean":
            if has_real_matches:
                results.false_positives += 1
        elif category == "test_data":
            # Test data files should have matches flagged as test data
            test_data_matches = sum(1 for m in file_result.matches if m.is_test_data)
            if test_data_matches > 0:
                # Correctly identified test data
                pass
            elif has_real_matches:
                # Detected but didn't flag as test data - this is okay
                pass
    
    results.calculate_metrics()
    
    return results


def print_results(results: BenchmarkResults):
    """Print benchmark results in a nice format."""
    print("\n" + "=" * 70)
    print(f"BENCHMARK RESULTS: {results.name}")
    print("=" * 70)
    
    print(f"\n{'CORPUS':^70}")
    print("-" * 70)
    print(f"  Total files:              {results.total_files:>6}")
    print(f"  Files with planted data:  {results.files_with_planted_data:>6}")
    print(f"  Clean files:              {results.files_clean:>6}")
    print(f"  Test data files:          {results.files_test_data:>6}")
    
    print(f"\n{'DETECTIONS':^70}")
    print("-" * 70)
    print(f"  Files with detections:    {results.files_with_detections:>6}")
    print(f"  Total matches:            {results.total_matches:>6}")
    print(f"  Real matches:             {results.real_matches:>6}")
    print(f"  Test data flagged:        {results.test_data_flagged:>6}")
    
    print(f"\n{'BY ENTITY TYPE':^70}")
    print("-" * 70)
    for entity, counts in sorted(results.by_entity.items()):
        print(f"  {entity:<20} total: {counts['total']:>4}  real: {counts['real']:>4}  test: {counts['test_data']:>4}")
    
    print(f"\n{'PERFORMANCE':^70}")
    print("-" * 70)
    print(f"  Scan time:                {results.scan_time_seconds:>6.2f} seconds")
    print(f"  Files per second:         {results.files_per_second:>6.1f}")
    print(f"  Presidio NER:             {'enabled' if results.presidio_enabled else 'disabled'}")
    
    print(f"\n{'ACCURACY':^70}")
    print("-" * 70)
    print(f"  True positives:           {results.true_positives:>6}")
    print(f"  False positives:          {results.false_positives:>6}")
    print(f"  False negatives:          {results.false_negatives:>6}")
    print(f"  Precision:                {results.precision:>6.1%}")
    print(f"  Recall:                   {results.recall:>6.1%}")
    print(f"  F1 Score:                 {results.f1_score:>6.1%}")
    
    print("=" * 70)


def compare_results(results1: BenchmarkResults, results2: BenchmarkResults):
    """Compare two benchmark runs."""
    print("\n" + "=" * 70)
    print("COMPARISON")
    print("=" * 70)
    
    print(f"\n{'Metric':<30} {results1.name:>18} {results2.name:>18}")
    print("-" * 70)
    
    print(f"{'Files with detections':<30} {results1.files_with_detections:>18} {results2.files_with_detections:>18}")
    print(f"{'Total matches':<30} {results1.total_matches:>18} {results2.total_matches:>18}")
    print(f"{'Real matches':<30} {results1.real_matches:>18} {results2.real_matches:>18}")
    print(f"{'Scan time (s)':<30} {results1.scan_time_seconds:>18.2f} {results2.scan_time_seconds:>18.2f}")
    print(f"{'Precision':<30} {results1.precision:>17.1%} {results2.precision:>17.1%}")
    print(f"{'Recall':<30} {results1.recall:>17.1%} {results2.recall:>17.1%}")
    print(f"{'F1 Score':<30} {results1.f1_score:>17.1%} {results2.f1_score:>17.1%}")
    
    # Improvement
    if results1.f1_score > 0 and results2.f1_score > 0:
        improvement = (results1.f1_score - results2.f1_score) / results2.f1_score * 100
        print(f"\n{'F1 improvement':<30} {improvement:>+17.1f}%")
    
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Benchmark scrubIQ detection accuracy")
    parser.add_argument("corpus_path", help="Path to test corpus")
    parser.add_argument("--compare-presidio", action="store_true", help="Compare with and without Presidio")
    parser.add_argument("--output", "-o", type=Path, help="Save results to JSON file")
    parser.add_argument("--no-presidio", action="store_true", help="Disable Presidio NER")
    
    args = parser.parse_args()
    
    corpus_path = Path(args.corpus_path)
    
    if not corpus_path.exists():
        print(f"Error: Corpus path not found: {corpus_path}")
        print("\nGenerate a test corpus first:")
        print(f"  python scripts/generate_test_corpus.py {corpus_path} --count 100")
        sys.exit(1)
    
    if args.compare_presidio:
        # Run with Presidio
        print("\nRunning benchmark WITH Presidio NER...")
        results_with = run_benchmark(corpus_path, enable_presidio=True, name="With Presidio")
        print_results(results_with)
        
        # Run without Presidio
        print("\nRunning benchmark WITHOUT Presidio NER...")
        results_without = run_benchmark(corpus_path, enable_presidio=False, name="Without Presidio")
        print_results(results_without)
        
        # Compare
        compare_results(results_with, results_without)
        
        # Save results
        if args.output:
            combined = {
                "with_presidio": results_with.to_dict(),
                "without_presidio": results_without.to_dict(),
            }
            args.output.write_text(json.dumps(combined, indent=2))
            print(f"\nResults saved to: {args.output}")
    else:
        # Single run
        enable_presidio = not args.no_presidio
        name = "With Presidio" if enable_presidio else "Without Presidio"
        
        print(f"\nRunning benchmark ({name})...")
        results = run_benchmark(corpus_path, enable_presidio=enable_presidio, name=name)
        print_results(results)
        
        if args.output:
            args.output.write_text(json.dumps(results.to_dict(), indent=2))
            print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
