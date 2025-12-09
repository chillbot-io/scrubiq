# scrubIQ

Find and protect sensitive data in Microsoft 365 and file shares.

## Quick Start

```bash
pip install scrubiq

# Scan a directory
scrubiq scan ./documents

# Scan and open HTML report
scrubiq scan ./documents --open

# Output JSON
scrubiq scan ./documents --format json --output results.json
```

## What It Finds

- **PII**: SSN, names, addresses, phone numbers, email, dates of birth
- **PHI**: Medical record numbers, health plan IDs, diagnoses, medications
- **PCI**: Credit card numbers
- **Secrets**: API keys, passwords in config files

## Installation

```bash
pip install scrubiq
```

For development:

```bash
git clone https://github.com/chillbot-io/scrubiq.git
cd scrubiq
pip install -e ".[dev]"
```

## Configuration

For Microsoft 365 labeling:

```bash
scrubiq setup
```

## License

MIT
