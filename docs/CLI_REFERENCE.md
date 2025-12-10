# scrubIQ CLI Reference

**Complete command-line interface guide.**

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `scrubiq scan` | Scan files for sensitive data |
| `scrubiq stats` | Show database statistics |
| `scrubiq export` | Export findings to JSON |
| `scrubiq report` | Generate HTML report |
| `scrubiq review` | Human review TUI |
| `scrubiq setup` | Configure M365 integration |
| `scrubiq config` | Manage configuration |
| `scrubiq labels` | List sensitivity labels |
| `scrubiq label` | Apply labels to files |
| `scrubiq purge` | Delete stored data |
| `scrubiq train` | Train TP/FP classifier |

---

## Global Options

```
scrubiq --version    Show version
scrubiq --help       Show help
```

---

## scrubiq scan

**Scan files and directories for sensitive data.**

### Basic Usage

```powershell
# Scan a directory
scrubiq scan ./documents

# Scan a file
scrubiq scan ./file.docx

# Scan network share
scrubiq scan "\\server\share\folder"
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--open` | | Open HTML report in browser when done |
| `--output FILE` | `-o` | Write results to file |
| `--format FORMAT` | `-f` | Output format: `text`, `json`, `html` (default: text) |
| `--quiet` | `-q` | Minimal output, no progress UI |
| `--no-store` | | Don't save results to database |
| `--no-presidio` | | Disable NER (faster, less accurate on names) |
| `--apply-labels` | | Apply sensitivity labels after scan |
| `--dry-run` | | Preview labels without applying |
| `--model PATH` | | Use custom TP/FP model |

### Examples

```powershell
# Scan and open report
scrubiq scan ./documents --open

# Scan quietly, output JSON
scrubiq scan ./documents -q --format json --output results.json

# Fast scan (no NER)
scrubiq scan ./documents --no-presidio

# Scan without storing (one-off check)
scrubiq scan ./documents --no-store

# Scan and apply labels (Windows with AIP client)
scrubiq scan ./documents --apply-labels

# Preview what would be labeled
scrubiq scan ./documents --apply-labels --dry-run
```

### Output

```
╭─────────────────── ⚠ Sensitive Data Found ───────────────────╮
│ Summary                                                       │
│   Total files scanned      94                                 │
│   Files with matches       64                                 │
│   Files with errors         0                                 │
│   Total matches           159                                 │
│                                                               │
│ Entities Found                                                │
│   ssn                      81                                 │
│   phone                    52                                 │
│   email                    33                                 │
│   credit_card               4                                 │
│                                                               │
│ Label Recommendations                                         │
│   highly_confidential      45 files                           │
│   confidential             12 files                           │
│   internal                  7 files                           │
╰───────────────────────────────────────────────────────────────╯

Results stored in encrypted database (scan_id: abc12345)
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No sensitive data found |
| 1 | Sensitive data found |
| 2 | Error occurred |

---

## scrubiq stats

**Show database statistics and scan history.**

### Basic Usage

```powershell
# Show overall stats
scrubiq stats

# Show specific scan
scrubiq stats --scan-id abc12345
```

### Options

| Option | Description |
|--------|-------------|
| `--scan-id ID` | Show details for specific scan |
| `--json` | Output as JSON |

### Examples

```powershell
# View all stats
scrubiq stats

# View specific scan details
scrubiq stats --scan-id 6388fe9d

# Output as JSON for scripting
scrubiq stats --json
```

### Output

```
╭─────────────────── Database Statistics ───────────────────╮
│                                                           │
│ Total scans:           12                                 │
│ Total files scanned:   1,847                              │
│ Total matches found:   3,291                              │
│ Database size:         2.4 MB                             │
│                                                           │
│ Recent Scans                                              │
│   6388fe9d  2024-12-09 15:30  94 files    658 matches     │
│   a1b2c3d4  2024-12-09 14:15  50 files    123 matches     │
│   e5f6g7h8  2024-12-08 09:00  200 files   456 matches     │
│                                                           │
╰───────────────────────────────────────────────────────────╯
```

---

## scrubiq export

**Export scan findings to JSON.**

### Basic Usage

```powershell
# Export to stdout
scrubiq export abc12345

# Export to file
scrubiq export abc12345 --output findings.json
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--output FILE` | `-o` | Write to file instead of stdout |
| `--include-context` | | Include match context (larger output) |
| `--redact` | | Redact sensitive values (default: true) |

### Examples

```powershell
# Export with full context
scrubiq export 6388fe9d --output findings.json --include-context

# Pipe to another tool
scrubiq export 6388fe9d | jq '.files[] | select(.has_sensitive_data)'
```

### Output Format

```json
{
  "scan_id": "6388fe9d",
  "started_at": "2024-12-09T15:30:00",
  "source_path": "/mnt/d/scrubiq/test_corpus",
  "summary": {
    "total_files": 94,
    "files_with_matches": 64,
    "total_matches": 159
  },
  "files": [
    {
      "path": "/path/to/file.txt",
      "has_sensitive_data": true,
      "label_recommendation": "highly_confidential",
      "matches": [
        {
          "entity_type": "ssn",
          "value": "07*-**-*120",
          "confidence": 0.95,
          "detector": "regex"
        }
      ]
    }
  ]
}
```

---

## scrubiq report

**Generate HTML report from stored scan.**

### Basic Usage

```powershell
# Generate and open
scrubiq report abc12345 --open

# Generate to file
scrubiq report abc12345 --output report.html
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--open` | | Open in browser after generating |
| `--output FILE` | `-o` | Output file path |

### Examples

```powershell
# Generate and view
scrubiq report 6388fe9d --open

# Save to specific location
scrubiq report 6388fe9d --output "C:\Reports\scan_report.html"
```

---

## scrubiq review

**Human-in-the-loop review of low-confidence matches.**

### Basic Usage

```powershell
# Review matches from a scan
scrubiq review abc12345

# View review statistics
scrubiq review --stats
```

### Options

| Option | Description |
|--------|-------------|
| `--threshold FLOAT` | Confidence threshold (default: 0.85) |
| `--stats` | Show review statistics |
| `--entity-type TYPE` | Filter by entity type |

### Examples

```powershell
# Review matches below 85% confidence
scrubiq review 6388fe9d

# Review more matches (lower threshold)
scrubiq review 6388fe9d --threshold 0.70

# Review only SSN matches
scrubiq review 6388fe9d --entity-type ssn

# Check how many reviews you've done
scrubiq review --stats
```

### TUI Controls

| Key | Action |
|-----|--------|
| `c` | Correct - this IS sensitive data |
| `w` | Wrong - this is NOT sensitive data |
| `s` | Skip - can't tell from context |
| `q` | Quit and save |

### TUI Display

```
┌─────────────────────── Review Sample ───────────────────────┐
│ [1/122]  √15 ✗3 ⊘2                                          │
│                                                             │
│ /mnt/d/scrubiq/test_corpus/hr/employee_record_003.txt       │
│                                                             │
│   FORM                                                      │
│                                                             │
│   Employee: Lisa Davis                                      │
│   SSN: 529-03-4308                                          │
│   DOB: [07/19/1970]  ← highlighted match                    │
│                                                             │
│   Health Plan Selection:                                    │
│   [X] Premium PPO - Employee                                │
│                                                             │
│   DATE_OF_BIRTH  60% confidence  (presidio)                 │
│   Value: 07******70                                         │
│                                                             │
│ Verdict [c/w/s/q]:                                          │
└─────────────────────────────────────────────────────────────┘
```

Counter explanation: `[1/122] √15 ✗3 ⊘2`
- `[1/122]` - Reviewing item 1 of 122
- `√15` - 15 marked correct
- `✗3` - 3 marked wrong
- `⊘2` - 2 skipped

---

## scrubiq setup

**Configure Microsoft 365 integration.**

### Basic Usage

```powershell
# Interactive setup wizard
scrubiq setup

# Show manual setup instructions
scrubiq setup --manual

# Reset configuration
scrubiq setup --reset
```

### Options

| Option | Description |
|--------|-------------|
| `--manual` | Show step-by-step manual instructions |
| `--reset` | Clear existing configuration |

### Examples

```powershell
# Run setup wizard (opens browser for auth)
scrubiq setup

# Get manual instructions (no browser)
scrubiq setup --manual

# Start fresh
scrubiq setup --reset
```

---

## scrubiq config

**Manage scrubIQ configuration.**

### Subcommands

| Subcommand | Description |
|------------|-------------|
| `config show` | Display current configuration |
| `config set` | Set a configuration value |
| `config labels` | Configure label mappings |
| `config test` | Test M365 connection |

### config show

```powershell
scrubiq config show
```

Output:
```
╭─────────────────── Configuration ───────────────────╮
│                                                     │
│ Tenant ID:      abc123-def456-...                   │
│ Client ID:      xyz789-...                          │
│ Client Secret:  ••••••••••••••• (set)               │
│                                                     │
│ Labeling Method: aip_client                         │
│                                                     │
│ Label Mappings:                                     │
│   highly_confidential → Highly Confidential         │
│   confidential        → Confidential                │
│   internal            → Internal                    │
│   public              → (skip)                      │
│                                                     │
│ Config file: C:\Users\...\scrubiq\config.json       │
╰─────────────────────────────────────────────────────╯
```

### config set

```powershell
# Set tenant ID
scrubiq config set tenant_id "your-tenant-id"

# Set client ID
scrubiq config set client_id "your-client-id"

# Set client secret (stored securely in keyring)
scrubiq config set client_secret "your-secret"

# Set labeling method
scrubiq config set method aip_client    # or graph_api
```

### config labels

Interactive label mapping wizard:

```powershell
scrubiq config labels
```

Output:
```
Available labels in your tenant:
  1. Public
  2. Internal
  3. Confidential
  4. Highly Confidential\All Employees
  5. Highly Confidential\Project X

Map 'highly_confidential' recommendation to:
  Enter number, label ID, or 'skip': 4

Map 'confidential' recommendation to:
  Enter number, label ID, or 'skip': 3

...

✓ Label mappings saved
```

### config test

```powershell
scrubiq config test
```

Output:
```
Testing Microsoft 365 connection...

✓ Authentication successful
✓ Can read sensitivity labels (found 5)
✓ Can list SharePoint sites (found 12)
✗ AIP client not available (Windows only)

Connection test passed (3/4 checks)
```

---

## scrubiq labels

**List available sensitivity labels from Microsoft 365.**

### Basic Usage

```powershell
scrubiq labels
```

### Options

| Option | Description |
|--------|-------------|
| `--json` | Output as JSON |

### Output

```
Available Sensitivity Labels:

  ID                                    Name
  ────────────────────────────────────  ────────────────────────────
  a1b2c3d4-e5f6-7890-abcd-ef1234567890  Public
  b2c3d4e5-f6a7-8901-bcde-f12345678901  Internal
  c3d4e5f6-a7b8-9012-cdef-123456789012  Confidential
  d4e5f6a7-b8c9-0123-defa-234567890123  Highly Confidential\All Employees
```

---

## scrubiq label

**Apply sensitivity labels based on scan results.**

### Basic Usage

```powershell
# Dry run (preview)
scrubiq label abc12345

# Actually apply
scrubiq label abc12345 --apply
```

### Options

| Option | Description |
|--------|-------------|
| `--apply` | Actually apply labels (default: dry-run) |
| `--mapping FILE` | Use custom label mapping file |

### Examples

```powershell
# Preview what would be labeled
scrubiq label 6388fe9d

# Apply labels via Graph API
scrubiq label 6388fe9d --apply
```

**Note:** For local files, use `scrubiq scan --apply-labels` instead. The `label` command uses Graph API which only works for SharePoint/OneDrive files.

---

## scrubiq scan-sharepoint

**Scan SharePoint site for sensitive data.**

### Basic Usage

```powershell
scrubiq scan-sharepoint "https://contoso.sharepoint.com/sites/HR"
```

### Options

| Option | Description |
|--------|-------------|
| `--apply-labels` | Apply labels after scan |
| `--dry-run` | Preview labels without applying |
| `--library NAME` | Specific document library |

### Examples

```powershell
# Scan entire site
scrubiq scan-sharepoint "https://contoso.sharepoint.com/sites/Finance"

# Scan specific library
scrubiq scan-sharepoint "https://contoso.sharepoint.com/sites/HR" --library "Employee Records"

# Scan and label
scrubiq scan-sharepoint "https://contoso.sharepoint.com/sites/HR" --apply-labels
```

---

## scrubiq purge

**Delete stored scan data.**

### Basic Usage

```powershell
# Delete specific scan
scrubiq purge --scan-id abc12345

# Delete all data
scrubiq purge --all
```

### Options

| Option | Description |
|--------|-------------|
| `--scan-id ID` | Delete specific scan |
| `--all` | Delete all scans (requires confirmation) |
| `--force` | Skip confirmation prompts |

### Examples

```powershell
# Delete one scan
scrubiq purge --scan-id 6388fe9d
# Confirm with 'y'

# Delete everything
scrubiq purge --all
# Must type 'DELETE ALL' to confirm

# Script-friendly (no prompts)
scrubiq purge --scan-id 6388fe9d --force
```

---

## scrubiq train

**Train the TP/FP classifier using review feedback.**

### Basic Usage

```powershell
scrubiq train
```

### Options

| Option | Description |
|--------|-------------|
| `--min-samples N` | Minimum reviews required (default: 50) |
| `--output PATH` | Output model path |
| `--data PATH` | Additional training data |

### Examples

```powershell
# Train with defaults
scrubiq train

# Train with more data
scrubiq train --min-samples 100

# Save model to specific location
scrubiq train --output ./models/my-model
```

### Output

```
Training TP/FP classifier...

Found 127 review examples:
  True positives:  94
  False positives: 33

Training SetFit model...
  Epoch 1/1: 100%|████████████| 20/20
  
Evaluation:
  Accuracy:  93.2%
  Precision: 95.1%
  Recall:    91.8%
  F1:        93.4%

✓ Model saved to: ~/.config/scrubiq/models/tpfp-v1.0.0+local.1
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SCRUBIQ_TENANT_ID` | Override tenant ID from config |
| `SCRUBIQ_CLIENT_ID` | Override client ID from config |
| `SCRUBIQ_CLIENT_SECRET` | Override client secret from config |
| `SCRUBIQ_CONFIG_DIR` | Custom config directory |
| `SCRUBIQ_DATA_DIR` | Custom data directory |

### Examples

```powershell
# Use environment variables
$env:SCRUBIQ_TENANT_ID = "your-tenant-id"
$env:SCRUBIQ_CLIENT_ID = "your-client-id"
$env:SCRUBIQ_CLIENT_SECRET = "your-secret"

scrubiq labels
```

---

## File Locations

| File | Location (Windows) | Location (Linux/Mac) |
|------|-------------------|---------------------|
| Config | `%LOCALAPPDATA%\scrubiq\config.json` | `~/.config/scrubiq/config.json` |
| Database | `%LOCALAPPDATA%\scrubiq\findings.db` | `~/.config/scrubiq/findings.db` |
| Feedback | `%LOCALAPPDATA%\scrubiq\feedback\reviews.jsonl` | `~/.config/scrubiq/feedback/reviews.jsonl` |
| Models | `%LOCALAPPDATA%\scrubiq\models\` | `~/.config/scrubiq/models/` |
| Logs | `%LOCALAPPDATA%\scrubiq\logs\` | `~/.config/scrubiq/logs/` |

---

## Common Workflows

### First Time Setup

```powershell
# 1. Install
pip install -e ".[dev]"

# 2. Verify
scrubiq --version

# 3. First scan
scrubiq scan ./documents --open
```

### Daily Scanning

```powershell
# Quick scan
scrubiq scan "\\fileserver\HR" -q

# Check for issues
scrubiq stats
```

### Improving Accuracy

```powershell
# 1. Scan
scrubiq scan ./documents

# 2. Review low-confidence matches
scrubiq review <scan_id>

# 3. Train model (after 50+ reviews)
scrubiq train

# 4. Benchmark improvement
python scripts/benchmark.py ./test_corpus
```

### M365 Labeling

```powershell
# 1. Setup
scrubiq setup

# 2. Map labels
scrubiq config labels

# 3. Test
scrubiq config test

# 4. Scan and label
scrubiq scan ./documents --apply-labels
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `command not found` | Run `pip install -e .` in scrubiq directory |
| `No files found` | Check path exists, try absolute path |
| `Database locked` | Close other scrubiq processes |
| `Presidio not working` | Run `python -m spacy download en_core_web_lg` |
| `AIP client not available` | Windows only, install AIP Unified Labeling client |
| `Authentication failed` | Check credentials with `scrubiq config show` |
| `Label not found` | Run `scrubiq config labels` to set mappings |

---

*CLI Reference for scrubIQ v0.1.0*
