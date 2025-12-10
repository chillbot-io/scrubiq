# scrubIQ

**Find and protect sensitive data in Microsoft 365 and file shares.**

scrubIQ scans your documents for PII, PHI, and PCI data, then applies Microsoft sensitivity labels automatically. Built for M365 E3 customers who need Purview-style auto-labeling without the E5 price tag.

## Quick Start

```bash
pip install scrubiq

# Scan a directory
scrubiq scan ./documents

# Scan and open HTML report
scrubiq scan ./documents --open

# Scan and apply sensitivity labels (requires AIP client)
scrubiq scan ./documents --apply-labels
```

## What It Finds

| Category | Entity Types |
|----------|--------------|
| **PII** | SSN, Names, Addresses, Phone, Email, Date of Birth |
| **PHI** | Medical Record Numbers, Health Plan IDs, Diagnoses, Medications |
| **PCI** | Credit Card Numbers (with Luhn validation) |
| **Secrets** | API Keys, Passwords in config files |

## Features

- **Fast scanning** - Extracts text from DOCX, XLSX, PPTX, PDF, MSG, RTF, EML, and plain text
- **Smart detection** - Regex patterns + optional Presidio NER for names/addresses
- **Test data filtering** - Automatically flags `123-45-6789` and other obvious test patterns
- **Beautiful reports** - Interactive HTML reports with filtering and search
- **Encrypted storage** - Findings stored with AES-256 encryption
- **Audit logging** - Every action logged for compliance
- **Human review** - Review low-confidence matches to improve accuracy
- **Auto-labeling** - Apply Microsoft sensitivity labels via AIP client or Graph API

## Installation

```bash
# Basic installation
pip install scrubiq

# With NLP for better name/address detection
pip install scrubiq[nlp]
python -m spacy download en_core_web_lg

# With training support (for improving detection)
pip install scrubiq[training]

# Everything
pip install scrubiq[all]
```

## Usage

### Scanning

```bash
# Scan a directory
scrubiq scan ./documents

# Scan a file share
scrubiq scan "\\\\fileserver\\HR"

# Output JSON instead of storing in database
scrubiq scan ./documents --format json --output results.json --no-store

# Skip Presidio NER (faster, but misses some names)
scrubiq scan ./documents --no-presidio

# Quiet mode (minimal output)
scrubiq scan ./documents -q
```

### Reports

```bash
# Generate and open HTML report
scrubiq scan ./documents --open

# Generate report from stored scan
scrubiq report <scan_id> --open

# Export findings to JSON
scrubiq export <scan_id> --output findings.json
```

### Microsoft 365 Integration

```bash
# Setup wizard (creates Azure AD app registration)
scrubiq setup

# Or manual setup
scrubiq setup --manual

# Configure label mappings
scrubiq config labels

# Test connection
scrubiq config test

# List available sensitivity labels
scrubiq labels
```

### Labeling

```bash
# Scan and apply labels to local files (requires AIP client on Windows)
scrubiq scan ./documents --apply-labels

# Preview what would be labeled
scrubiq scan ./documents --apply-labels --dry-run

# Apply labels to SharePoint files from stored scan
scrubiq label <scan_id> --apply
```

### Database & Stats

```bash
# Show statistics
scrubiq stats

# Show specific scan details
scrubiq stats --scan-id <scan_id>

# Delete a scan
scrubiq purge --scan-id <scan_id>

# Delete all data
scrubiq purge --all
```

### Human Review

Review low-confidence matches to improve detection accuracy:

```bash
# Review matches below 85% confidence
scrubiq review <scan_id>

# Review with lower threshold
scrubiq review <scan_id> --threshold 0.70

# Show review statistics
scrubiq review --stats
```

## Configuration

Configuration is stored in `~/.config/scrubiq/config.json` (Linux/Mac) or `%LOCALAPPDATA%\scrubiq\config.json` (Windows).

```bash
# Show current configuration
scrubiq config show

# Set values
scrubiq config set tenant_id <your-tenant-id>
scrubiq config set client_id <your-client-id>
scrubiq config set client_secret <your-secret>
scrubiq config set method aip_client  # or graph_api
```

Environment variables override config file:
- `SCRUBIQ_TENANT_ID`
- `SCRUBIQ_CLIENT_ID`
- `SCRUBIQ_CLIENT_SECRET`

## Label Mappings

scrubIQ maps its classification recommendations to your tenant's sensitivity labels:

| Recommendation | Triggered By | Default Mapping |
|----------------|--------------|-----------------|
| `highly_confidential` | SSN, Credit Card, MRN, Health Plan ID | Highly Confidential |
| `confidential` | Names, Addresses, Diagnoses | Confidential |
| `internal` | Email, Phone | Internal |
| `public` | Low-confidence matches | (skip) |

Configure mappings interactively:
```bash
scrubiq config labels
```

## Requirements

- Python 3.10+
- Windows with AIP client for local file labeling (optional)
- Microsoft 365 tenant for Graph API features (optional)

### AIP Client Installation

For labeling local files on Windows:

1. Download from [Microsoft](https://docs.microsoft.com/en-us/azure/information-protection/rms-client/install-unifiedlabelingclient-app)
2. Install the Unified Labeling client
3. Sign in to Azure AD when prompted

### Azure AD App Permissions

If setting up manually, your app needs these Microsoft Graph permissions:

- `Sites.Read.All` - List SharePoint sites, read files
- `Files.Read.All` - Read file content
- `InformationProtectionPolicy.Read.All` - Get sensitivity labels
- `Sites.ReadWrite.All` - Apply labels via Graph API (optional)

## Python API

```python
from scrubiq import Scanner, Config, AIPClient

# Scan files
scanner = Scanner()
result = scanner.scan("./documents")

print(f"Scanned {result.total_files} files")
print(f"Found {result.total_matches} matches in {result.files_with_matches} files")

for file in result.files:
    if file.has_sensitive_data:
        print(f"{file.path}: {file.label_recommendation}")
        for match in file.matches:
            print(f"  - {match.entity_type}: {match.redacted_value}")

# Apply labels (Windows with AIP client)
aip = AIPClient()
if aip.is_available():
    config = Config.load()
    for file in result.files:
        if file.has_sensitive_data and file.label_recommendation:
            label_id = config.get_label_id(file.label_recommendation.value)
            if label_id:
                success, msg = aip.apply_label(file.path, label_id)
```

## Architecture

```
scrubiq/
├── scanner/          # File scanning and text extraction
├── classifier/       # Detection (regex + Presidio NER)
├── storage/          # Encrypted SQLite database
├── labeler/          # AIP client + Graph API labeling
├── auth/             # Config, setup wizard, Graph client
├── reporter/         # HTML report generation
├── review/           # Human review TUI
└── training/         # TP/FP classifier training
```

## What scrubIQ Does NOT Do

scrubIQ is focused on classification and labeling. It does not:

- Real-time monitoring / DLP
- User behavior analytics
- Threat detection
- Access governance
- IAM / AD / Entra management
- eDiscovery / legal hold
- Multi-cloud (AWS, GCP)

## License

MIT

## Links

- Documentation: https://docs.scrubiq.io (coming soon)
- Issues: https://github.com/chillbot-io/scrubiq/issues
