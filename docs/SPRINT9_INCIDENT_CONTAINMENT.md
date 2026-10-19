# Sprint 9: database incident containment

**Date:** 2026-10-17. **Incident:** a local development server wrote to the main `answerwise` database at about
17:02–17:04 IST. The full investigation is [SPRINT8_IMPORT_INVESTIGATION.md](SPRINT8_IMPORT_INVESTIGATION.md), kept
unchanged as the original record.

> **The incident is NOT resolved.**
> - It stays open until an authorised database administrator completes the review in §4 and the data owner decides
>   the response.
> - Nothing here shows that the main database is clean or fully understood.
> - In this sprint the main database was not connected to, queried, inspected or changed.

**Status:**
- **NO-GO** for pilot use;
- B1–B5 OPEN; D1–D10 undecided;
- real-world grading accuracy remains unknown;
- high-stakes and unreviewed grading remain NO-GO.

## 1. Incident summary and confirmed timeline

All times are IST (UTC+05:30). Sources: the main `mongod` log, VS Code's saved terminal output, file metadata and the
Claude session transcript. Details are in the sprint 8 report.

| Time | Confirmed event |
|---|---|
| 17:02:07.30–17:02:10.56 | `app.main` is imported by a `uvicorn app.main:app --reload --port 8000` server (reloader process 31380, server process 4932) in an already-open VS Code PowerShell terminal (`backend\`, `.venv` active); 20 `.pyc` files are written |
| 17:02:10.712 | Main `mongod` (127.0.0.1:27017) accepts PyMongo 4.17.0 / CPython 3.12.4 connections (connection ids 1809–1811), all logged as "Connection not authenticating" |
| 17:02:10.746–.776 | `createCollection answerwise.enrollments`; index builds `_id_` and `uniq_enrollment_email`, from the application's start-up `ensure_indexes` |
| 17:02:36–17:02:39 | Embedding model loaded by the server |
| 17:03:19.92 | Server log: "Registered student account 6ad35cffacd1975c76878e49"; `POST /api/auth/register` → 201 |
| 17:03:19.97 | Two more connections (ids 1812–1813) |
| 17:03:55 | VS Code shuts down; every one of these connections ends |

## 2. Facts, inferences and unknowns

**Confirmed (from existing logs or files)**
- A dev server connected to the main server and created `answerwise.enrollments` with two indexes.
- The server reported one successful student registration.
- The configuration that led there: `backend/.env` selected `MONGODB_DB=answerwise`. The code default and
  `.env.example` were also `answerwise`.
- No pilot safeguard applied: `PILOT_MODE` was off, and only pilot mode refused that database.
- Between 10:08:27 and 17:02:10 the main server accepted no connections, and none after 17:03:19 (log read up to
  about 17:14).

**Inferred, needing a database administrator to confirm**
- A user document `6ad35cff…` was **persisted** in `answerwise.users`, based on the application log, the 201 response
  and the ObjectId time.
- `enrollments` is empty: development-mode registration does not write enrollments.
- Requests read data (login, assessments, results, analytics, submissions).
- **The main `mongod` does not enforce access control.** The unauthenticated connection 1810 was able to create a
  collection and indexes.
- The operator was a person using the developer's terminal.

**Unknown**
- Who started the server.
- Whether the registered account belongs to a tester or a real person.
- Its exact contents.
- Whether any other writes happened: MongoDB logs no inserts or updates at default verbosity.
- Why VS Code shut down.

## 3. Preventive changes

### What was established from the code (static reading)

| Question | Answer |
|---|---|
| How is the database chosen? | Only by `Settings.mongodb_db`: environment variable `MONGODB_DB`, then `backend/.env`, then the code default. `app/db.py` uses `client[s.mongodb_db]`, so a database name inside `MONGODB_URI` is ignored |
| Could development reach `answerwise` by accident? | **Yes, before this sprint**, in three ways: the code default was `answerwise`; `.env.example` said `answerwise`; and only pilot mode refused it |
| Does start-up write to the database? | **Yes.** The lifespan always runs `ensure_indexes(get_db())`, which creates missing collections and indexes. That is the 17:02:10 write |
| Can development select a dedicated database safely? | Yes: `MONGODB_DB=answerwise_dev` in the local, uncommitted `backend/.env` |
| Does the pilot launcher stop unsupported starts? | Partly. A PILOT_MODE server refuses to start without `ANSWERWISE_LAUNCHER=1`, but that variable can be set by hand (a known limitation, sprints 3–5). Pilot mode also refuses the development database and needs a valid pilot marker. **Development mode had no protection at all.** That is the gap closed here |

### Changes made (no database access was needed)

| File | Change |
|---|---|
| `backend/app/config.py` | `PROTECTED_DATABASES = ("answerwise",)` and `protected_database_problem(name)`. `get_settings()` now raises "Refusing to start: …" in **every** mode when the **resolved** `mongodb_db` (after the environment and `.env`; case and spaces ignored; empty refused) is protected. The default database is now `answerwise_dev`. The pilot check also refuses `answerwise_dev`, which strengthens it and weakens nothing |
| `backend/scripts/pilot_preflight.py` | `check_database` builds `Settings()` itself, so it repeats the guard and reports FAIL without connecting or reading |
| `backend/scripts/pilot_init_db.py` | Also refuses `answerwise_dev` and the protected names |
| `backend/.env.example` | `MONGODB_DB=answerwise_dev`, with an explanation |
| `README.md` | Environment table: default `answerwise_dev`; `answerwise` refused |
| `backend/tests/test_protected_database_sprint9.py` (new) | 23 isolated unit tests (§6) |
| `docs/PILOT_RUNBOOK.md`, `docs/PILOT_READINESS.md` | Local-development rule and incident status (§7) |

**Where the guard sits, and why there.** `get_settings()` runs at module level when `app.main` is imported, before
the FastAPI app, its lifespan (`ensure_indexes`) or any router exists. It also runs inside `get_db()`, the seed, the
pilot launcher and the pilot scripts. So `uvicorn app.main:app` with `MONGODB_DB=answerwise` now stops at import,
**before any connection**. The pilot fail-safes are unchanged and still run first.

**Action for the developer.** The local `backend/.env` was **not edited**: it holds secrets and is the developer's
own configuration. It still selects `answerwise` (sprint 8), so the dev server will now **refuse to start** until
`MONGODB_DB=answerwise_dev` (or another name) is set there. The new database starts empty; seed it with
`python -m scripts.seed`.

**What the guard does not cover:**
- tools outside this application, such as `mongosh`, Compass or other projects;
- someone who edits the code or renames the database;
- the missing access control on the MongoDB server itself (§7).

## 4. Database administrator handoff (to be performed separately, by an authorised person)

**Non-destructive.**
- Do **not** delete, drop, update or re-index anything until step 7 has an authorised decision.
- Work from a terminal that is not running the application.
- Never print passwords, password hashes, tokens or full personal data into tickets or reports.

1. **Preserve the evidence first**, before any log rotation or restart:
   - **Main server log.** Copy `C:\Program Files\MongoDB\Server\8.2\log\mongod.log` (and any rotated files) to a
     write-protected evidence location, and record the SHA-256 of each copy. The relevant entries are
     **2026-10-17 17:02:10.712 to 17:03:55.728**, connection ids **1809–1813**.
   - **VS Code state.** Copy
     `%APPDATA%\Code\User\workspaceStorage\35694c9961f7cc7c29a7fb0e37e3c116\state.vscdb.backup` and `state.vscdb`.
     They hold the terminal output with the server log lines.
   - **VS Code logs.** Copy `%APPDATA%\Code\logs\20261016T213626\`.
   - **Bytecode metadata.** Record the timestamps of the 20 `backend/app/**/__pycache__/*.pyc` files. Do not delete
     or regenerate them.
2. **Take a read-only backup** of the database as it is now, for example
   `mongodump --host 127.0.0.1 --port 27017 --db answerwise --out <secure location>`.
   - Store it under the institution's rules for personal data.
   - Record its checksum, who made it and when.
3. **Inspect the new collection** (read-only, in `mongosh`, `use answerwise`):
   - `db.getCollectionInfos({name: "enrollments"})`;
   - `db.enrollments.getIndexes()`, expected to be `_id_` and the unique `uniq_enrollment_email`;
   - `db.enrollments.countDocuments({})`, expected to be 0. Record any other result without printing the addresses.
4. **Confirm whether the reported registration persisted**, without exposing personal data:
   - `db.users.find({_id: ObjectId("6ad35cffacd1975c76878e49")}, {_id: 1, role: 1, created_at: 1, pilot_enrolled: 1})`
     — this projection excludes the name, e-mail and password hash;
   - expected, if it persisted: `role: "student"` and `created_at` about `2026-10-17T11:33:19Z`;
   - record "present" or "absent" and those fields only.
5. **Test account or real person?** Decide without revealing the address.
   - Ask the developer who ran the terminal whether they registered a test account at 17:03 IST, and with which
     address.
   - The administrator then checks for an exact match, for example
     `db.users.countDocuments({_id: ObjectId("6ad35cff…"), email: "<address the developer names>"})`, and records
     only the 0 or 1.
   - If nobody can account for it, **treat it as possibly a real person's data**. Do not open it further; escalate
     to the data owner and, if applicable, ethics (B2).
6. **Look for other changes in the incident window** (read-only):
   - For each collection, count documents whose ObjectId falls in the window:
     `db.getCollectionNames().forEach(c => print(c, db[c].countDocuments({_id: {$gte: ObjectId.createFromTime(Math.floor(Date.parse("2026-10-17T11:32:00Z")/1000)), $lte: ObjectId.createFromTime(Math.floor(Date.parse("2026-10-17T11:34:30Z")/1000))}})))`.
   - Also count documents with `updated_at` or `created_at` in the same UTC window, in collections that have those
     fields.
   - Note that a standalone server keeps **no oplog**. Updates to older documents may not be detectable unless a
     backup from before 17:02 exists. If one does, compare against it; if not, record that as a limitation.
   - Check whether access control is enabled (`security.authorization` in `mongod.cfg`; `db.adminCommand({getCmdLineOpts: 1})`).
     The log suggests it is off.
7. **Decide the response** before changing anything. This is the **data owner's** decision, with ethics involved if
   a real person's data is affected. Options include:
   - keep everything and document it;
   - remove a confirmed test account;
   - drop the empty `enrollments` collection;
   - restore from a backup;
   - change nothing.

   **Record:** who authorised the decision, who carried it out, when, the exact commands, and the checksums of the
   evidence before and after.
8. **Report back** using counts and present/absent results only, so the incident record can be closed.

## 5. Evidence preservation and integrity

**Evidence preserved (read-only).**
- No file named in §4.1 was changed or deleted in this sprint.
- The 20 sprint 8 `.pyc` files are byte-identical to the sprint 8 snapshot (all 304 project files were compared before
  any edit).
- **No bytecode was written** in sprint 9.

**Protected files**, checked with `sha256sum`, `jq` and `sed` only (no Python):

| Group | Result |
|---|---|
| 10 scoring sources `app/nlp/*.py` | identical to the sprint 1 hash list |
| `app/services/evaluation_service.py` and `scripts/pilot_frozen_engine.json` | identical to the end-of-sprint-3 record (the manifest's hash value is not written down) |
| Manifest coverage | 11/11 listed files match the manifest |
| 48 historical evaluation files (they include both locked sets and their locks) | identical to the recorded list |
| Locked sets | both match their locks under the project's CRLF→LF rule |

One check needed a second attempt. The first manifest-coverage run reported 0/11, because `jq` on Windows adds a
carriage return to each line. With it stripped the result is 11/11, consistent with the per-file checks above.

**Limits.**
- The hash lists were written by the development agent itself in earlier sprints; they are **not independent
  baselines**.
- The lock files are stored in the repository.
- There is no version control.
- Independent verification needs the supervisor's own hashes (B5).
- Baselines and locks were **not** regenerated.

**Changed in this sprint:** the 6 files in §3 plus this report.

## 6. Tests

**Run.** `tests/test_protected_database_sprint9.py`, 23 tests, from `backend/`:

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<scratchpad>/guard python -B -m pytest -p s9guard -p no:cacheprovider \
  --noconftest tests/test_protected_database_sprint9.py -v
```

**Result: exit 0, 23 passed.**

How the run was isolated:
- `--noconftest` meant no shared fixtures were loaded, so no database client was created.
- The scratchpad plugin `s9guard` installs a Python audit hook that refuses and logs **any socket connection**,
  **any import of `app.main`**, and **any read of the real `backend/.env`**.
- A probe first confirmed the hook blocks all three.
- During the 23 tests it logged **nothing**: no socket, no application import, no `.env` read.
- Every `MongoClient` the code under test could create was replaced by a stub that fails the test if it is called.

What the tests cover:
- the protected name in any spelling, and an empty name;
- other names, such as `answerwise_dev`, test and pilot names, being allowed;
- the new default;
- refusal in development and in production;
- the selected name coming from the environment or from a `.env` file;
- the environment label not bypassing the guard;
- pilot refusal of the development and protected names;
- `get_db()` refusing before creating a client;
- the preflight not opening the database;
- `pilot_init_db` refusing;
- a static AST check that `app.main` resolves settings before the app exists, without importing it;
- the template value.

**Detection check.** The same file, run against a scratchpad copy with the **old** behaviour (default `answerwise`,
no guard), gives **7 failed, 16 passed**: every guard-dependent test fails. The copy was deleted afterwards.

**Other commands.**
- A documentation edit accidentally ran `python -B -` with an **empty** script. It did nothing: no import and no
  network. The edit was then redone with the editor.
- The main server's log shows **no connection accepted after 17:03:20** up to the end of the portion read during this
  sprint.

**Not run, and why.**
- **All existing backend suites, including sprints 3–7 and their regression sets.** They use MongoDB through shared
  fixtures (some of which used the main *server* in the past), and this sprint forbids commands that might connect
  to MongoDB.
  - *Static review instead:* the only existing test touching this path (`test_pilot_readiness.py`, pilot mode with
    `MONGODB_DB=answerwise`) still raises the pilot error first, and that error still contains "dedicated pilot
    database".
  - **This is reasoning, not a test result.**
- Scoring, evaluation and study suites; browser end-to-end tests: forbidden.
- Frontend tests: no frontend change.
- Starting a server to watch the guard refuse: forbidden. The refusal at import is shown statically and with the
  unit tests.

## 7. Remaining risks

| Risk | Note |
|---|---|
| **Incident open** | Database review §4 not yet performed; the account's persistence and identity are unverified; other writes cannot be ruled out |
| **Main MongoDB has no access control (inferred)** | Any local process can read or write any database. The application guard does not change that. Recommendation for IT and the administrator: enable authentication, with separate users for development and administration |
| The guard is application-level | It does not stop `mongosh`, Compass, other projects or code edits. A real `answerwise_dev` server is also a shared local server |
| Local `.env` still says `answerwise` | Fail-closed: the dev server will refuse until the developer changes it |
| Existing suites not re-run | The regression status after this change is not freshly verified (§6) |
| Start-up always writes indexes | `ensure_indexes` writes to whatever database is selected, by design; now never `answerwise` |
| Earlier tests used the main *server* | Sprint 3's tests (09:00–10:08) used separate databases on the same server. Not re-examined. The administrator's database list can show any leftover test databases |
| Pilot-launcher marker can be set by hand | Unchanged known limitation (sprints 3–5) |

## 8. Status

- **The incident is not fully resolved** until the database review in §4 is complete and the data owner has decided
  the response.
- **B1–B5 remain OPEN** and **D1–D10 undecided**; nothing here is an approval.
- **Real-world grading accuracy remains unknown.**
- **High-stakes and unreviewed grading remain NO-GO.**
- **The project remains NO-GO for pilot use.**
