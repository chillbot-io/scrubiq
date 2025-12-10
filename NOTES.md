# scrubIQ Development Notes

Running log of blockers, decisions, TODOs, and ideas.

---

## Blocked

- [ ] **i2b2 2014 dataset** — n2c2 portal says "temporarily unavailable". Try legacy DUA email route: schurchill@partners.org. Check again tomorrow (Dec 10).

---

## Decisions

### Day 2: Data Models

- **Verdict unification** — Addendum has two Verdict enums (CORRECT/WRONG vs TP/FP). Using TP/FP/UNSURE/SKIPPED everywhere since it matches training data format and is more precise.

- **model_version on Match** — Added `model_version: Optional[str]` to Match dataclass. When we ship trained models, we need traceability for "which model found this."

### Day 5: Scanner + Storage

- **Encrypted storage** — Raw sensitive values (SSNs, etc) must be stored encrypted. Using SQLCipher (AES-256) with keys stored in OS keyring (DPAPI on Windows, Keychain on macOS, libsecret on Linux). SOC2-friendly: data-at-rest encryption, OS-level key protection, full audit logging.

- **Audit trail** — Every database access logged with timestamp, action, user, record count. Supports compliance requirements.

---

## TODOs by Phase

### Phase 7 (Reports)
- [ ] Label inventory feature: `scrubiq report <path>` — crawl location, output CSV of labeled files
- [ ] PDF summary with bar charts (label distribution)
- [ ] Need `LabeledFile` dataclass for report data model

### Phase 9 (Graph API / Labeling)
- [ ] Extend FileResult with SharePoint metadata (site_id, drive_id, item_id) — or create subclass
- [ ] ActionLog dataclass for audit trail (constitution: "reversible, every action logged")

### Phase 8.5 (Training Pipeline)
- [ ] Synthetic data generator (Faker + templates) — can start before i2b2 access
- [ ] Benchmark script comparing scrubIQ vs Presidio

---

## V2 TODOs

- [ ] **Master key escrow** — Enterprise feature. If employee leaves, IT can recover encrypted findings database. Options: split key, HSM integration, or Azure Key Vault.

---

## Future Ideas

- **Structured errors** — FileResult.error is just a string. Could use error types (ExtractionError, PermissionError, FileTooLarge) for better filtering/reporting.

- **On-prem label metadata extraction** — reading sensitivity labels from Office file custom XML parts. Need architect-Claude input.

---

## Session Log

### Dec 9, 2024
- Day 1: Foundation complete. CLI installs, `scrubiq --version` works.
- Day 2: Data models. Added NOTES.md for tracking.
- Attempted i2b2 access — dataset temporarily unavailable.
- Decided to skip MIMIC (data is already de-identified, useless for training PHI detection).

### Dec 9, 2024 (continued) - Day 5
- Built encrypted storage layer (AES-256 via Fernet + OS keyring)
- Built Scanner class that ties extractors + detectors together
- Audit logging for all data access (SOC2-friendly)
- Updated CLI with working scan, stats, purge commands
- 128 tests passing

### Dec 9, 2024 (continued) - Phase 6
- Built full ScanUI class with live-updating panel
  - Progress bar with percentage
  - Entity type breakdown with mini bar charts
  - Recent matches feed
  - Current file indicator
- Updated CLI with richer output
- Added `export` command for retrieving findings
- Improved `stats` command with recent scans table
- 140 tests passing

### Dec 10, 2024 - Phase 10 (Config & Setup)
- Built Config system with platform-specific paths
- Secure credential storage via keyring
- Label mapping configuration (scrubIQ recommendations → tenant labels)
- AIPClient for labeling local files via PowerShell
- AzureSetupWizard with device code flow
- ManualSetupGuide as fallback
- CLI commands: setup, config show/set/labels/test
- 318 tests passing

### Dec 10, 2024 - Phase 11 (Polish & Testing)
- Code formatted with black
- Linted with ruff (all checks passing)
- Added MRN and Health Plan ID detection patterns
- Fixed Luhn CC generator in test corpus script
- **Benchmark results: 100% precision, 100% recall, 100% F1**
- Added tests for PHI patterns (MRN, Health Plan ID)
- 326 tests passing
- Created TRAINING_PLAN.md for Phase 12

## Current Benchmark (Dec 10, 2024)

**Test Corpus:** 94 files (75 sensitive, 15 clean, 3 test data)

| Metric | Value |
|--------|-------|
| Precision | 100% |
| Recall | 100% |
| F1 Score | 100% |
| Speed | 2,300+ files/sec |

**Entity Detection:**
- SSN: 81 real matches, 4 test data flagged
- Credit Card: 12 real, 3 test flagged
- Email: 35 real, 2 test flagged
- Phone: 54 real, 2 test flagged
- MRN: 25 real
- Health Plan ID: 6 real
