# Supervisor integrity record (template)

> The **faculty supervisor** keeps this record **outside** the study directory and outside the repository, for example
> by e-mail to themselves or on paper. The study team must not be able to edit the supervisor's copy.

**What the hashes prove:** that the locked study set and the score report verified later are byte-for-byte the files
that existed when the hashes were handed over.
**What they do NOT prove:** that informed consent was obtained, that marking was blind or independent, that the
adjudication was fair, or that nobody scored a copy of the data elsewhere. Those rest on the ethics approval, the consent
records, and the markers' and supervisor's own confirmation.

| Item | Value | Received on | Received from |
|---|---|---|---|
| Study id | `<study_id>` | | |
| Frozen engine (printed by `freeze`) | `<engine_version / config_fingerprint>` | | |
| `study_set.json` SHA-256 (printed by `freeze`) | `<64 hex characters>` | `<date>` | `<role>` |
| `score_report.json` SHA-256 (printed by `score`) | `<64 hex characters>` | `<date>` | `<role>` |

**Verification** (run by or in front of the supervisor, from `backend/`):

```bash
python -m evaluation.real_study verify --study STUDY --set-hash <set hash> --report-hash <report hash>
```

Expected output: `VERIFIED`. Any `MISMATCH` or `MISSING` means the study result must not be used.

| Verified on | Result | By |
|---|---|---|
| `<date>` | `<VERIFIED / MISMATCH>` | `<supervisor>` |
