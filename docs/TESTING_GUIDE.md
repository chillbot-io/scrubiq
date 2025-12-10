# scrubIQ Testing Guide

**Complete guide to testing all functionality and measuring performance.**

---

## Quick Reference

| Test | Command | Expected |
|------|---------|----------|
| Installation | `scrubiq --version` | `scrubiq, version 0.1.0` |
| Basic scan | `scrubiq scan ./test_corpus` | Finds matches, stores in DB |
| HTML report | `scrubiq scan ./test_corpus --open` | Browser opens with report |
| Stats | `scrubiq stats` | Shows scan history |
| Export | `scrubiq export <scan_id>` | JSON output |
| Review | `scrubiq review <scan_id>` | TUI launches |
| Unit tests | `pytest tests/ -v` | 317+ passed |

---

## Part 1: Installation Testing

### 1.1 Basic Installation

```powershell
cd D:\scrubiq
pip install -e ".[dev]"

# Verify
scrubiq --version
# Expected: scrubiq, version 0.1.0
```

### 1.2 Check All Dependencies

```powershell
python -c "
from scrubiq import Scanner, Config
from scrubiq.storage import FindingsDatabase
from scrubiq.reporter.html import generate_html_report
print('Core imports: OK')

from scrubiq.classifier.detectors.presidio import HAS_PRESIDIO
print(f'Presidio NER: {\"OK\" if HAS_PRESIDIO else \"Not installed\"}')

from scrubiq.labeler.aip import AIPClient
aip = AIPClient()
print(f'AIP Client: {\"OK\" if aip.is_available() else \"Not available\"}')
"
```

### 1.3 Run Unit Tests

```powershell
# Quick run
pytest tests/ -q

# Verbose with coverage
pytest tests/ -v --cov=scrubiq --cov-report=term-missing

# Expected: 317+ passed, some skipped (Presidio tests skip if spacy model missing)
```

---

## Part 2: Core Functionality Testing

### 2.1 Scanning

**Test: Basic directory scan**
```powershell
scrubiq scan ./test_corpus
```
Expected:
- Progress UI shows
- Summary panel appears
- `scan_id` is output
- "Results stored in encrypted database"

**Test: Scan with HTML report**
```powershell
scrubiq scan ./test_corpus --open
```
Expected:
- Browser opens with HTML report
- Report shows files, matches, entity breakdown
- Filtering works (try the dropdowns)

**Test: Scan without database storage**
```powershell
scrubiq scan ./test_corpus --no-store --format json --output results.json
```
Expected:
- `results.json` created
- No database entry (verify with `scrubiq stats`)

**Test: Scan with Presidio disabled**
```powershell
scrubiq scan ./test_corpus --no-presidio
```
Expected:
- Faster scan
- Fewer matches (no names/addresses from NER)

**Test: Quiet mode**
```powershell
scrubiq scan ./test_corpus -q
```
Expected:
- Minimal output, no progress UI

### 2.2 Database Operations

**Test: View statistics**
```powershell
scrubiq stats
```
Expected:
- Total scans count
- Total files scanned
- Total matches found
- Recent scans list

**Test: View specific scan**
```powershell
scrubiq stats --scan-id <scan_id>
```
Expected:
- Detailed breakdown for that scan
- Files with matches listed

**Test: Export findings**
```powershell
scrubiq export <scan_id>
scrubiq export <scan_id> --output findings.json
```
Expected:
- JSON output to stdout or file
- Contains file paths, matches, recommendations

**Test: Generate report from stored scan**
```powershell
scrubiq report <scan_id> --open
```
Expected:
- HTML report generates
- Browser opens

**Test: Purge scan data**
```powershell
# First, do a test scan
scrubiq scan ./test_corpus --no-presidio
# Note the scan_id

# Delete it
scrubiq purge --scan-id <scan_id>
# Confirm with 'y'

# Verify gone
scrubiq stats
```

**Test: Purge all data**
```powershell
scrubiq purge --all
# Requires typing 'DELETE ALL' to confirm
```

### 2.3 Human Review

**Test: Launch review TUI**
```powershell
scrubiq scan ./test_corpus
scrubiq review <scan_id>
```
Expected:
- TUI shows sample with context
- Keyboard controls work (c/w/s/q)
- Progress counter updates

**Test: Review with custom threshold**
```powershell
scrubiq review <scan_id> --threshold 0.70
```
Expected:
- More matches to review (lower threshold = more uncertainty)

**Test: Check feedback storage**
```powershell
# After reviewing some matches
type $env:LOCALAPPDATA\scrubiq\feedback\reviews.jsonl
```
Expected:
- JSONL file with your verdicts
- Each line has: entity_type, verdict, context, etc.

**Test: View review stats**
```powershell
scrubiq review --stats
```
Expected:
- Total reviews count
- TP/FP breakdown
- Accuracy percentage

### 2.4 HTML Reports

**Test: Report filtering**
1. Open an HTML report
2. Use the entity type dropdown - filters should work
3. Use the search box - should filter by filename
4. Click on a file row - should expand/collapse

**Test: Report content accuracy**
1. Open report
2. Pick a file with matches
3. Open the actual file and verify the matches are real
4. Check that values are redacted (e.g., `12*******89` not full SSN)

---

## Part 3: Microsoft 365 Integration Testing

### 3.1 Configuration

**Test: Setup wizard (manual mode)**
```powershell
scrubiq setup --manual
```
Expected:
- Prints step-by-step instructions
- Shows required permissions
- Shows how to configure

**Test: View configuration**
```powershell
scrubiq config show
```
Expected:
- Shows tenant_id (or "not set")
- Shows client_id (or "not set")
- Shows client_secret status
- Shows label mappings

**Test: Set configuration values**
```powershell
scrubiq config set tenant_id "your-tenant-id"
scrubiq config set client_id "your-client-id"
scrubiq config set client_secret "your-secret"

# Verify
scrubiq config show
```

### 3.2 Label Operations (Requires M365 Tenant)

**Test: List available labels**
```powershell
scrubiq labels
```
Expected (if configured):
- List of sensitivity labels from your tenant
- Label IDs and names

**Test: Configure label mappings**
```powershell
scrubiq config labels
```
Expected:
- Interactive prompts for each recommendation level
- Can select by number or skip

**Test: Test connection**
```powershell
scrubiq config test
```
Expected:
- Tests authentication
- Tests permissions
- Reports success or specific errors

### 3.3 Labeling (Requires AIP Client on Windows)

**Test: Check AIP availability**
```powershell
python -c "
from scrubiq.labeler.aip import AIPClient
aip = AIPClient()
print(f'Available: {aip.is_available()}')
if aip.is_available():
    print(f'PowerShell: {aip._powershell_path}')
"
```

**Test: Dry-run labeling**
```powershell
scrubiq scan ./test_corpus --apply-labels --dry-run
```
Expected:
- Shows what WOULD be labeled
- No actual changes made

**Test: Apply labels (careful!)**
```powershell
# Only if you have AIP client and labels configured
scrubiq scan ./test_corpus --apply-labels
```
Expected:
- Files get labeled
- Summary shows labeled count

---

## Part 4: File Type Testing

### 4.1 Supported File Types

Create test files with planted SSN `078-05-1120`:

| Type | Create | Test |
|------|--------|------|
| .txt | `echo "SSN: 078-05-1120" > test.txt` | Should detect |
| .csv | `echo "name,ssn\nJohn,078-05-1120" > test.csv` | Should detect |
| .json | `echo '{"ssn": "078-05-1120"}' > test.json` | Should detect |
| .md | `echo "# Test\nSSN: 078-05-1120" > test.md` | Should detect |
| .docx | Create in Word with SSN | Should detect |
| .xlsx | Create in Excel with SSN | Should detect |
| .pdf | Create/export with SSN | Should detect |
| .pptx | Create in PowerPoint with SSN | Should detect |

**Test each type:**
```powershell
scrubiq scan ./path/to/test/files --no-store
```

### 4.2 Edge Cases

**Test: Empty file**
```powershell
echo "" > empty.txt
scrubiq scan . --no-store
```
Expected: No matches, no errors

**Test: Binary file (should skip)**
```powershell
# Put an image or exe in the folder
scrubiq scan . --no-store
```
Expected: Unsupported file types skipped gracefully

**Test: Large file**
```powershell
# Create a file > 100MB
scrubiq scan . --no-store
```
Expected: "File too large" message, skipped

**Test: Locked file**
```powershell
# Open a file in another program (e.g., Word)
scrubiq scan . --no-store
```
Expected: Error message but continues scanning other files

---

## Part 5: Detection Accuracy Testing

### 5.1 True Positive Tests

These should ALL be detected:

```
SSN: 078-05-1120
Social Security: 123-45-6789
SSN 555-12-3456

Credit Card: 4532015112830366
Card: 5425233430109903

Email: john.doe@company.com
Phone: (555) 867-5309
Phone: 555-867-5309
```

### 5.2 True Negative Tests

These should NOT be detected (or flagged as test data):

```
Order ID: 123-45-6789 (context matters)
Test SSN: 123-45-6789 (test data pattern)
Example: 000-00-0000 (invalid SSN)
Card: 1234567890123456 (fails Luhn check)
```

### 5.3 Test Data Detection

```powershell
# Create file with test patterns
echo "Test SSN: 123-45-6789
Example card: 4111111111111111
Demo: 555-555-5555" > test_patterns.txt

scrubiq scan . --no-store
```
Expected: Matches found but flagged as `is_test_data: true`

### 5.4 Benchmark Script

```powershell
python scripts/benchmark.py ./test_corpus --no-presidio
```

Expected output:
```
ACCURACY
----------------------------------------------------------------------
  True positives:               XX
  False positives:               X
  False negatives:              XX
  Precision:                  XX.X%
  Recall:                     XX.X%
  F1 Score:                   XX.X%
```

---

## Part 6: Performance Testing

### 6.1 Speed Benchmarks

**Test: Small corpus (100 files)**
```powershell
Measure-Command { scrubiq scan ./test_corpus --no-store -q }
```
Target: < 10 seconds with Presidio, < 1 second without

**Test: Files per second**
```powershell
python scripts/benchmark.py ./test_corpus --no-presidio
# Check "files per second" in output
```
Target: > 1000 files/second without Presidio

### 6.2 Memory Usage

```powershell
# Monitor memory while scanning large directory
scrubiq scan "C:\Users\YourName\Documents" --no-store
```
Expected: Memory stays reasonable (< 500MB for most scans)

### 6.3 Large File Handling

```powershell
# Create 50MB text file
python -c "print('SSN: 078-05-1120\n' * 1000000)" > large.txt
scrubiq scan . --no-store
```
Expected: Handles without crashing

---

## Part 7: Error Handling Testing

### 7.1 Invalid Paths

```powershell
scrubiq scan ./nonexistent
```
Expected: Clear error message, non-zero exit code

### 7.2 Permission Denied

```powershell
# Try scanning a protected directory
scrubiq scan "C:\Windows\System32"
```
Expected: Errors logged but scan continues for accessible files

### 7.3 Corrupted Files

```powershell
# Create corrupted docx
echo "not a real docx" > fake.docx
scrubiq scan . --no-store
```
Expected: Error for that file, scan continues

### 7.4 Network Paths

```powershell
# If you have a network share
scrubiq scan "\\server\share\folder"
```
Expected: Works same as local paths

---

## Part 8: Regression Testing

After any code changes, run:

```powershell
# Full test suite
pytest tests/ -v

# Quick smoke test
scrubiq scan ./test_corpus --no-store -q
echo $LASTEXITCODE  # Should be 1 (found sensitive data) or 0 (none found)

# Benchmark comparison
python scripts/benchmark.py ./test_corpus --output baseline.json
# Make changes
python scripts/benchmark.py ./test_corpus --output new.json
# Compare F1 scores
```

---

## Part 9: Test Checklist

### Pre-Release Checklist

- [ ] `pip install -e ".[dev]"` succeeds
- [ ] `scrubiq --version` works
- [ ] `pytest tests/` - all pass (some skips OK)
- [ ] `scrubiq scan ./test_corpus` - finds matches
- [ ] `scrubiq scan ./test_corpus --open` - report opens
- [ ] `scrubiq stats` - shows scan
- [ ] `scrubiq export <id>` - JSON output
- [ ] `scrubiq review <id>` - TUI works
- [ ] `scrubiq purge --scan-id <id>` - deletes scan
- [ ] Benchmark F1 > 90%

### M365 Integration Checklist (if configured)

- [ ] `scrubiq setup --manual` - shows instructions
- [ ] `scrubiq config show` - shows settings
- [ ] `scrubiq labels` - lists tenant labels
- [ ] `scrubiq config labels` - mapping wizard works
- [ ] `scrubiq config test` - connection succeeds
- [ ] `scrubiq scan ... --apply-labels --dry-run` - preview works

---

## Appendix: Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Run `pip install -e ".[dev]"` again |
| Presidio not detecting names | Install spacy model: `python -m spacy download en_core_web_lg` |
| AIP client not available | Install from Microsoft, requires Windows |
| Database locked | Close other scrubiq processes |
| HTML report won't open | Check browser default, try `--output report.html` then open manually |
| Review shows 0 matches | Lower threshold: `--threshold 0.5` |

---

*Testing Guide for scrubIQ v0.1.0*
