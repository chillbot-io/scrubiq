# scrubIQ Model Training Guide

**Complete guide to training the TP/FP classifier for industry-leading accuracy.**

---

## Overview

scrubIQ's accuracy comes from three layers:

```
Layer 1: Regex Patterns     → High precision, catches obvious patterns
Layer 2: Presidio NER       → Catches names, addresses (lower precision)
Layer 3: TP/FP Classifier   → Filters false positives from Layer 1+2
```

This guide covers training Layer 3 - the machine learning model that learns to distinguish real sensitive data from false positives.

---

## Part 1: Human-in-the-Loop Training

**This is the fastest way to improve accuracy. You can start right now.**

### 1.1 The Review Workflow

```powershell
# 1. Scan documents
scrubiq scan ./your_documents

# 2. Review low-confidence matches
scrubiq review <scan_id>

# 3. Check accumulated feedback
scrubiq review --stats
```

### 1.2 Review Interface

```
┌─────────────────────── Review Sample ───────────────────────┐
│ [1/122]  √15 ✗3 ⊘2                                          │
│                                                             │
│ /path/to/employee_record.txt                                │
│                                                             │
│   Employee: Lisa Davis                                      │
│   SSN: 529-03-4308                                          │
│   DOB: [07/19/1970]  ← highlighted match                    │
│                                                             │
│   DATE_OF_BIRTH  60% confidence  (presidio)                 │
│   Value: 07******70                                         │
│                                                             │
│ Verdict [c/w/s/q]:                                          │
└─────────────────────────────────────────────────────────────┘
```

**Keyboard shortcuts:**
- **c** = Correct (this IS sensitive data)
- **w** = Wrong (this is NOT sensitive data / false positive)
- **s** = Skip (can't tell from context)
- **q** = Quit and save

### 1.3 What Makes a Good Review

**Mark as CORRECT (c) when:**
- It's clearly PII in a real document (SSN on employee form)
- The context confirms it's sensitive (DOB next to patient name)
- Even if the format is slightly off, it's still real data

**Mark as WRONG (w) when:**
- It's test/example data ("Test SSN: 123-45-6789")
- It's a false pattern match (order ID that looks like SSN)
- It's business data, not personal (company phone number)
- The context shows it's not sensitive (random date in a log file)

**Skip (s) when:**
- You genuinely can't tell from the context shown
- You'd need to see more of the document

### 1.4 How Many Reviews?

| Reviews | Effect |
|---------|--------|
| 20-50 | Minimal - good for testing pipeline |
| 50-100 | Noticeable improvement on your document types |
| 100-500 | Significant accuracy gains |
| 500+ | Approaching maximum benefit from your data |

**Pro tip:** Quality > quantity. 50 careful reviews beat 200 rushed ones.

### 1.5 Review Different Entity Types

Don't just review SSNs. Cover the spread:

```powershell
# Check what you've reviewed
type $env:LOCALAPPDATA\scrubiq\feedback\reviews.jsonl | 
  python -c "import sys,json,collections; c=collections.Counter(json.loads(l)['entity_type'] for l in sys.stdin); print(dict(c))"
```

Target distribution:
- SSN: 20%
- Names: 20%
- Dates/DOB: 20%
- Phone/Email: 20%
- Credit cards/MRN/Other: 20%

### 1.6 Where Feedback Is Stored

```
Windows: %LOCALAPPDATA%\scrubiq\feedback\reviews.jsonl
Linux:   ~/.config/scrubiq/feedback/reviews.jsonl
```

Each line is a JSON object:
```json
{
  "id": "abc123",
  "entity_type": "ssn",
  "verdict": "TP",
  "confidence": 0.72,
  "detector": "regex",
  "context": "Employee SSN: [SSN] was verified...",
  "reason": null,
  "timestamp": "2024-12-09T15:30:00"
}
```

---

## Part 2: Training Datasets

### 2.1 Dataset Overview

| Dataset | Size | Content | Access |
|---------|------|---------|--------|
| Your Reviews | 50-500+ | Your actual documents | Local |
| Synthetic | 1,000+ | Generated fake docs | Generate yourself |
| Nemotron-CC | 500K+ | Web text with PII | Free (HuggingFace) |
| i2b2 2014 | 1,304 | Clinical notes | Free (apply for access) |

### 2.2 Generate Synthetic Data

Already built-in:

```powershell
# Generate 1000 documents with planted PII
python scripts/generate_test_corpus.py ./training/synthetic --count 1000

# Check what was generated
type ./training/synthetic/manifest.json
```

This creates:
- HR documents (SSN, DOB, addresses)
- Finance documents (credit cards)
- Medical documents (MRN, health plan IDs)
- Clean documents (no PII)
- Test data documents (obvious fakes like 123-45-6789)

### 2.3 Download Nemotron-CC Dataset

NVIDIA's Nemotron-CC contains synthetic PII annotations:

```powershell
pip install datasets

python -c "
from datasets import load_dataset
from pathlib import Path

# Download PII subset
ds = load_dataset('nvidia/Nemotron-CC', split='train', streaming=True)

# Save first 10K examples with PII
output = Path('./training/nemotron')
output.mkdir(parents=True, exist_ok=True)

count = 0
with open(output / 'examples.jsonl', 'w') as f:
    for item in ds:
        if 'pii' in str(item).lower():
            f.write(str(item) + '\n')
            count += 1
            if count >= 10000:
                break
            if count % 1000 == 0:
                print(f'Downloaded {count} examples...')

print(f'Done! Saved {count} examples')
"
```

### 2.4 Apply for i2b2 2014 Dataset

**This is the gold standard for PHI detection benchmarks.**

1. Go to: https://portal.dbmi.hms.harvard.edu/projects/n2c2-nlp/
2. Create account
3. Submit data use agreement
4. Wait 5-7 business days for approval
5. Download "2014 De-identification and Heart Disease" track

Once approved:
```powershell
# After downloading and extracting
python training/scripts/load_i2b2.py ./path/to/i2b2/data --output ./training/i2b2
```

### 2.5 Combine All Training Data

```powershell
# Merge all sources into one training file
python -c "
from pathlib import Path
import json

output = Path('./training/combined.jsonl')
sources = [
    Path('./training/synthetic/manifest.json'),
    Path('./training/nemotron/examples.jsonl'),
    Path('./training/i2b2/examples.jsonl'),
    Path(r'%LOCALAPPDATA%/scrubiq/feedback/reviews.jsonl'),  # Your reviews
]

with open(output, 'w') as out:
    for source in sources:
        if source.exists():
            print(f'Loading {source}...')
            with open(source) as f:
                for line in f:
                    out.write(line)

print(f'Combined training data written to {output}')
"
```

---

## Part 3: Training the TP/FP Classifier

### 3.1 Install Training Dependencies

```powershell
pip install setfit datasets sentence-transformers
```

### 3.2 Training Script

```powershell
# Basic training
python scripts/train_tpfp.py --data ./training/combined.jsonl --output ./models/tpfp-v1

# Or use the CLI
scrubiq train --min-samples 50
```

### 3.3 What the Trainer Does

```python
# Simplified version of what happens:

from setfit import SetFitModel, SetFitTrainer

# 1. Load your feedback data
examples = load_training_data("./training/combined.jsonl")

# 2. Format for the model
# Input: "[SSN] in context: Employee SSN: [SSN] was verified..."
# Label: 1 (true positive) or 0 (false positive)
texts = [f"[{e['entity_type'].upper()}] in context: {e['context']}" for e in examples]
labels = [1 if e['verdict'] == 'TP' else 0 for e in examples]

# 3. Train SetFit model (works with small datasets!)
model = SetFitModel.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
trainer = SetFitTrainer(model=model, train_dataset=dataset)
trainer.train()

# 4. Save
model.save_pretrained("./models/tpfp-v1")
```

### 3.4 Training Parameters

```python
# In scripts/train_tpfp.py, you can adjust:

SetFitTrainer(
    model=model,
    train_dataset=train_data,
    eval_dataset=test_data,
    num_iterations=20,      # More = better but slower
    num_epochs=1,           # Usually 1 is enough for SetFit
    batch_size=16,          # Increase if you have GPU
    learning_rate=2e-5,     # Default is usually fine
)
```

### 3.5 Evaluate the Model

```powershell
python scripts/train_tpfp.py --data ./training/combined.jsonl --output ./models/tpfp-v1 --eval

# Output:
# Training examples: 847
# Test examples: 212
# 
# Results:
#   Accuracy:  94.3%
#   Precision: 96.1%
#   Recall:    92.8%
#   F1:        94.4%
```

### 3.6 Integrate Trained Model

After training, the model integrates automatically:

```powershell
# Copy to package location
mkdir src\scrubiq\classifier\models\tpfp-v1
copy models\tpfp-v1\* src\scrubiq\classifier\models\tpfp-v1\

# Now scans will use it
scrubiq scan ./documents
```

Or specify explicitly:
```powershell
scrubiq scan ./documents --model ./models/tpfp-v1
```

---

## Part 4: Iterative Improvement

### 4.1 The Feedback Loop

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Scan      │ ──▶ │   Review    │ ──▶ │   Train     │
│  Documents  │     │  Matches    │     │   Model     │
└─────────────┘     └─────────────┘     └─────────────┘
       ▲                                       │
       │                                       │
       └───────────── Better Model ────────────┘
```

### 4.2 Track Progress Over Time

```powershell
# Benchmark before training
python scripts/benchmark.py ./test_corpus --output benchmark_v0.json

# Train model
scrubiq train

# Benchmark after
python scripts/benchmark.py ./test_corpus --output benchmark_v1.json

# Compare
python -c "
import json
v0 = json.load(open('benchmark_v0.json'))
v1 = json.load(open('benchmark_v1.json'))
print(f'F1 improvement: {v1[\"accuracy\"][\"f1_score\"] - v0[\"accuracy\"][\"f1_score\"]:.1%}')
"
```

### 4.3 Version Your Models

```
models/
├── tpfp-v1/           # First trained model
├── tpfp-v2/           # After more reviews
├── tpfp-v3/           # After i2b2 training
└── tpfp-v3-medical/   # Specialized for healthcare
```

### 4.4 Specialize for Your Domain

If you primarily scan healthcare documents:

```powershell
# Generate medical-heavy synthetic data
python scripts/generate_test_corpus.py ./training/medical --count 500 --medical-only

# Review medical documents specifically
scrubiq scan ./real_medical_docs
scrubiq review <scan_id>

# Train specialized model
scrubiq train --output ./models/tpfp-medical
```

---

## Part 5: Benchmarking

### 5.1 Internal Benchmark (Synthetic Data)

```powershell
python scripts/benchmark.py ./test_corpus

# Compare with/without Presidio
python scripts/benchmark.py ./test_corpus --compare-presidio
```

### 5.2 i2b2 Benchmark (Gold Standard)

Once you have i2b2 access:

```powershell
python scripts/benchmark_i2b2.py ./data/i2b2-2014 --output i2b2_results.json
```

This produces numbers you can publish:
```
Dataset: i2b2 2014 De-identification Challenge

| System      | Precision | Recall | F1    |
|-------------|-----------|--------|-------|
| Presidio    | 82.3%     | 76.4%  | 79.2% |
| scrubIQ     | 91.5%     | 87.2%  | 89.3% |
```

### 5.3 Track Key Metrics

| Metric | What It Means | Target |
|--------|--------------|--------|
| Precision | Of detections, how many real | > 90% |
| Recall | Of real PII, how many found | > 85% |
| F1 | Balance of precision/recall | > 88% |
| FP Rate | False alarms | < 5% |

### 5.4 Entity-Level Metrics

```powershell
python -c "
import json
with open('benchmark_results.json') as f:
    data = json.load(f)

print('By Entity Type:')
for entity, metrics in data['by_entity'].items():
    print(f'  {entity}: P={metrics[\"precision\"]:.1%} R={metrics[\"recall\"]:.1%} F1={metrics[\"f1\"]:.1%}')
"
```

---

## Part 6: Advanced Training

### 6.1 Active Learning

Focus reviews on the most uncertain matches:

```powershell
# Already built-in! Review sorts by confidence (lowest first)
scrubiq review <scan_id>

# The first matches shown are the ones the model is least sure about
# These provide the most training signal
```

### 6.2 Hard Negative Mining

Find cases where the model is confidently wrong:

```python
# After training, scan and check high-confidence FPs
scanner = Scanner()
result = scanner.scan("./documents")

hard_negatives = []
for file in result.files:
    for match in file.matches:
        # High confidence but actually wrong
        if match.confidence > 0.9 and is_false_positive(match):
            hard_negatives.append(match)

# Add these to training data with verdict="FP"
```

### 6.3 Domain Adaptation

For specific industries:

**Healthcare:**
- Focus on MRN, health plan IDs, diagnoses
- Train on i2b2 data
- Review actual clinical notes

**Finance:**
- Focus on credit cards, account numbers, routing numbers
- Generate financial document synthetic data
- Review actual financial documents

**HR:**
- Focus on SSN, DOB, addresses
- Generate employment document synthetic data
- Review actual HR files

### 6.4 Ensemble Models

Train multiple models and combine:

```python
# Train on different data sources
model_synthetic = train_on("./training/synthetic")
model_i2b2 = train_on("./training/i2b2")
model_reviews = train_on("./training/reviews")

# Ensemble prediction
def predict(text):
    scores = [
        model_synthetic.predict(text),
        model_i2b2.predict(text),
        model_reviews.predict(text),
    ]
    return sum(scores) / len(scores) > 0.5
```

---

## Part 7: Training Schedule

### Week 1: Foundation
- [ ] Review 50+ matches from your documents
- [ ] Generate 1000 synthetic documents
- [ ] Run baseline benchmark
- [ ] Apply for i2b2 access

### Week 2: First Model
- [ ] Review 100+ more matches
- [ ] Download Nemotron-CC subset
- [ ] Train first model
- [ ] Benchmark improvement

### Week 3: Refinement
- [ ] Review focusing on weak entity types
- [ ] Train v2 model
- [ ] Compare v1 vs v2

### Week 4: Gold Standard (if i2b2 approved)
- [ ] Load i2b2 data
- [ ] Train on clinical notes
- [ ] Run i2b2 benchmark
- [ ] Document publishable numbers

### Ongoing
- [ ] Review 10-20 matches per week
- [ ] Retrain monthly
- [ ] Track metrics over time

---

## Part 8: Troubleshooting

### Not Enough Training Data

```
Error: Need at least 50 examples to train
```

Solution: Review more matches!
```powershell
scrubiq review <scan_id> --threshold 0.5  # Lower threshold = more to review
```

### Model Not Improving

Possible causes:
1. **Not enough variety** - Review different entity types
2. **Inconsistent labeling** - Be consistent in what you mark correct/wrong
3. **Too few FP examples** - Make sure you're marking false positives

Check your data balance:
```powershell
type $env:LOCALAPPDATA\scrubiq\feedback\reviews.jsonl | 
  python -c "import sys,json,collections; c=collections.Counter(json.loads(l)['verdict'] for l in sys.stdin); print(dict(c))"
```

Target: ~70% TP, ~30% FP

### Model Too Aggressive (Missing Real PII)

- Add more TP examples
- Lower the classification threshold
- Review high-confidence matches to find mistakes

### Model Too Permissive (Too Many FPs)

- Add more FP examples
- Focus reviews on false positives
- Increase classification threshold

---

## Part 9: Target Metrics

### Good (Usable)
- F1 > 85%
- Precision > 85%
- Recall > 80%

### Great (Competitive)
- F1 > 90%
- Precision > 90%
- Recall > 88%

### Excellent (Industry Leading)
- F1 > 93%
- Precision > 95%
- Recall > 90%
- Published i2b2 benchmark

### Current Baseline
With regex only:
- F1: 92.1%
- Precision: 100%
- Recall: 85.3%

The gap is recall - the model is missing some real PII. Adding Presidio NER and the TP/FP classifier should push recall up while maintaining precision.

---

## Appendix: Quick Commands

```powershell
# Review matches
scrubiq review <scan_id>

# Check review stats
scrubiq review --stats

# Train model
scrubiq train

# Benchmark
python scripts/benchmark.py ./test_corpus

# Generate synthetic data
python scripts/generate_test_corpus.py ./training/synthetic --count 1000

# View feedback file
type $env:LOCALAPPDATA\scrubiq\feedback\reviews.jsonl

# Clear feedback (start over)
Remove-Item $env:LOCALAPPDATA\scrubiq\feedback\reviews.jsonl
```

---

*Training Guide for scrubIQ v0.1.0*
