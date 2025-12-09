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
