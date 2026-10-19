# Sprint 10: final technical review after database isolation

**Date:** 2026-10-17. **Scope:** a review of the sprint 9 protected-database guard and its documentation.

**Status:**
- **INC-1 is OPEN** until an authorised database administrator completes the review in
  [SPRINT9_INCIDENT_CONTAINMENT.md](SPRINT9_INCIDENT_CONTAINMENT.md) §4 and the data owner records a decision;
- **B1–B5 OPEN**, **D1–D10 undecided**; nothing here is an approval;
- real-world grading accuracy remains **unknown**;
- high-stakes and unreviewed grading remain **NO-GO**;
- **the project remains NO-GO for pilot use.**

## 1. Pre-conditions found

| Item | Finding |
|---|---|
| `backend/.env`, `MONGODB_DB` line (only the database lines were read; no secrets) | Changed at **17:30:13** and now `MONGODB_DB=answerwise_dev`. This was **observed in the file**; it is not an explicit confirmation from the developer |
| `MONGODB_URI` | `mongodb://localhost:27017`: still the **main MongoDB server** involved in INC-1, which appears to run without access control. The database name is now safe; the **connection is not verified safe** |
| Main server activity since the incident | Its log file (read as a file) shows **no connection accepted** and no collection or index created after 17:03:20, up to its last write at 17:30:34. So no server was started after the `.env` change |
| Other changes since sprint 9 | Only `backend/.env` (above) and the final sprint 9 report edit, which was mine (verified: removing that edit reproduces the sprint 9 snapshot hash) |

**Consequence.** Under this sprint's rules, existing database-dependent backend suites were **not run** (§5): the
connection is not verified safe, and the developer has not explicitly confirmed it.

## 2. Static review of the guard

| Check | Result |
|---|---|
| **Database selection order** | `Settings.mongodb_db`: OS environment `MONGODB_DB` (matched case-insensitively), then `backend/.env` (absolute path, so it does not depend on the working directory), then the default `answerwise_dev`. `app/db.py` uses `client[s.mongodb_db]`, so a database in the `MONGODB_URI` path is ignored and cannot bypass the guard |
| **Guard logic** (`app/config.py` `protected_database_problem`, called in `get_settings`) | Compares the **resolved** name after `strip().lower()`; refuses `answerwise` in any case or with surrounding whitespace, and an empty name. It runs in every mode, after the pilot and production checks, which raise first if they apply. A refusal raises, so nothing is cached and every later call raises again |
| **Every place a MongoDB client is created** (non-test) | Exactly two: `app/db.py` `get_db` (calls `get_settings()` first) and `scripts/pilot_preflight.py` `check_database` (repeats the guard first). There are no others in `app/`, `scripts/`, `evaluation/` or `docs/*.py` |
| **Import order** | Nothing in `app/` or `scripts/` connects at module level. The only module-level settings call is `app/main.py:27 settings = get_settings()`. Everything imported before it only defines code, so `uvicorn app.main:app` refuses at import, before the app, its start-up `ensure_indexes`, or any client exists |
| **Entry points** | dev server and `run_server` (launcher, `main()` → `get_settings()`); `seed` (`get_settings()` before `get_db()`, so `--reset` cannot reach `drop_database`); `pilot_init_db` (`get_settings()`, plus its own name check); `pilot_fallback_report` (`get_db()`); `pilot_preflight` (own check). **All stop before connecting** |
| **Case and whitespace** | Handled by lower-casing and stripping. MongoDB also refuses a second database whose name differs only in case. Look-alike names (for example with Unicode or zero-width characters) are **different databases**, not the protected one, so they are not a bypass of `answerwise` itself |
| **Remaining bypass routes (not application code)** | `app.db.set_db()` (used only by tests); tools outside the app (`mongosh`, Compass, other projects); editing the code. None can be closed by an application guard |

**No bypass was found** by which this application's own code could open `answerwise` without the guard running
first.

## 3. Findings

| ID | Severity | Finding | Action |
|---|---|---|---|
| S10-1 | **MEDIUM (operational)** | The guard isolates the **database name**, not the **server**. With `MONGODB_URI=mongodb://localhost:27017`, the development database `answerwise_dev` **and** the throw-away test databases (`answerwise_test_<pid>`, `answerwise_sec*`, `answerwise_preflight_test_*`) are created on the **same main server** that was involved in INC-1 and appears to run without access control | **Documented** (README, runbook §0). Recommended and **not implemented**, because it changes how developers run tests: (a) point development and tests at a separate, disposable `mongod`; (b) IT enables MongoDB authentication with separate users; (c) optionally, a test-side check that refuses the main server unless explicitly allowed. These need a developer or IT decision |
| S10-2 | LOW | The three command-line entry points (`seed`, `run_server`, `pilot_fallback_report`) were covered only indirectly by the sprint 9 tests | **Fixed:** 3 tests added (§4) |
| S10-3 | LOW (docs) | The README did not tell developers with an older `.env` why the backend now refuses, nor that a new database name is not a new server | **Fixed:** one note under "Installation and running" |
| S10-4 | INFO | Application start-up always runs `ensure_indexes`, so selecting a database is never read-only. By design; documented in the runbook since sprint 9 | none |
| S10-5 | INFO | `seed --reset` drops whatever database is selected (now never `answerwise`) | none |

## 4. Test evidence (fresh, this sprint)

**Run:** `backend/tests/test_protected_database_sprint9.py`, now **26 tests** (23 from sprint 9 plus 3 added here for
S10-2). It is **not** database-dependent and does not import the app. From `backend/`:

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<scratchpad>/sprint9/guard python -B -m pytest -p s9guard -p no:cacheprovider \
  --noconftest tests/test_protected_database_sprint9.py -v
```

**Result: exit 0, 26 passed.**

How the run was isolated:
- `--noconftest` meant no shared fixtures were loaded, so no database client was created.
- The scratchpad plugin `s9guard` (probe-verified in sprint 9) refuses and logs **any socket connection**, **any
  import of `app.main`** and **any read of the real `backend/.env`**. It logged **nothing**.
- The tests disable the `.env` file (or use a temporary one) before building settings.
- Every client, server or seeding step the code under test could reach is replaced by a stub that fails the test if
  it is called.

The dangerous cases covered:

| Case | Covered |
|---|---|
| Protected name in the environment, in `.env`, in mixed case, with whitespace; empty name | yes |
| Development and production modes; pilot mode refusing development and protected names | yes |
| `get_db()`, preflight, `pilot_init_db` | yes (sprint 9) |
| **`seed --reset`, `run_server.main`, `pilot_fallback_report.main`** | **yes (new)** |
| `app.main` resolves settings before the app exists | static AST check, without importing it |
| `.env.example` value | yes |

**Detection check for the new tests.** Run against a scratchpad copy with the guard removed: **3 failed** (each
stopped at a stub, still with no network). The copy was deleted.

**Not run, and why**

| Not run | Why |
|---|---|
| All existing database-dependent backend suites (sprints 3–7, regression sets) | **The pre-condition is not met.** `.env` now names `answerwise_dev`, but `MONGODB_URI` is the main incident server and the developer has not confirmed the connection is safe. The shared fixtures would create databases on that server (S10-1). Their regression status after sprints 9–10 is **not freshly verified** |
| Starting the dev server or the launcher to watch the refusal | Forbidden (no application start); shown by the stub-based tests and static review |
| Seed scripts | Forbidden |
| Scoring, evaluation and study suites; browser end-to-end; frontend | Forbidden, or no frontend change |

## 5. Protected-file integrity (existing rules, no regeneration)

Checked with `sha256sum`, `jq` (carriage returns stripped) and `sed` only:

| Group | Result |
|---|---|
| 10 scoring sources | identical to the sprint 1 list |
| `evaluation_service.py` and `pilot_frozen_engine.json` | identical to the end-of-sprint-3 record (the manifest hash value is not written down) |
| Manifest coverage | 11/11 |
| 48 historical evaluation files (they include both locked sets and their locks) | identical to the recorded list |
| Locked sets | both match their locks under the CRLF→LF rule |
| Bytecode | none written this sprint; the incident's 20 `.pyc` files are untouched |

**Limits:** the hash lists were written by the development agent; they are not independent baselines. The locks are
stored in the repository, there is no version control, and independent verification needs the supervisor (B5).

## 6. Files changed in sprint 10

| File | Reason |
|---|---|
| `backend/tests/test_protected_database_sprint9.py` | 3 entry-point tests (S10-2) |
| `README.md` | Existing-`.env` and same-server note (S10-3) |
| `docs/PILOT_RUNBOOK.md` §0 | Run tests against a disposable `mongod` while INC-1 is open (S10-1) |
| `docs/PILOT_READINESS.md` | Status line references this review |
| `docs/SPRINT10_FINAL_TECHNICAL_REVIEW.md` | This report |

No application, scoring, evaluation, model, dataset, lock or manifest file was changed. `backend/.env` was **not**
edited by me.

## 7. Remaining actions

| Who | Action |
|---|---|
| **Developer** | Explicitly confirm the `.env` change. Decide on S10-1: a separate disposable `mongod` for development and tests (recommended), or keep the shared server once IT has added authentication. Only then run the existing backend suites, against a verified disposable database |
| **Database administrator** | The sprint 9 §4 checklist: preserve the evidence, take a read-only backup, inspect `enrollments`, confirm the account's persistence and identity without exposing it, look for other changes, check access control |
| **Data owner** (and ethics, if a real person's data is involved) | Decide the INC-1 response; record who authorised it and who carried it out |
| **IT** | Enable MongoDB access control; D7 topology |
| **Faculty, ethics, supervisor** | B1–B5 and D1–D10, as in [SPRINT6_FINAL_SIGNOFF.md](SPRINT6_FINAL_SIGNOFF.md) |

**Technical sign-off (conservative).**
- **Covered by tests and static review:** the application can no longer select the protected database through its
  own configuration or entry points.
- **Not signed off:**
  - the regression status of the existing suites (not run);
  - the safety of the shared MongoDB server (S10-1);
  - the state of the `answerwise` database (INC-1);
  - any pilot readiness.
