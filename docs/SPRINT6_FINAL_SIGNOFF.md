# Sprint 6: final technical sign-off and human handoff

**Date:** 2026-10-17. **For:** faculty, ethics reviewers, IT, the supervisor and the developers.
**Scope:** a final, narrow check of the sprint 5 fixes, plus the handoff packet. This was not a new security sprint.

## 1. Executive decision: **NO-GO**

The technical work is at a hand-off point, but **the pilot is not authorised and the system is not pilot-ready**:
- all five external blockers (B1–B5) are **OPEN**, and no approval evidence exists;
- none of D1–D10 is decided;
- the residual risks (`PILOT_READINESS.md` §3) are not accepted in writing.

Passing tests and completed forms are not approvals.

- **Real-world grading accuracy remains unknown.** Every existing result comes from synthetic answers written by the
  developer, marked by one person. No real student answers have been evaluated.
- **High-stakes, summative and unreviewed grading remain NO-GO** under every outcome, including a future
  CONDITIONAL GO for a low-stakes, teacher-reviewed pilot.

One new technical finding came out of this check: **S6-1**, a withdrawal partial-failure window (§6). A fix is
proposed but **not implemented**; it needs approval first.

## 2. Status of A1–A10, checked against the code

Each control is labelled by **when** it works:
- **always** — the running application enforces it on every request or start-up;
- **at launch** — `scripts/run_server.py` checks it once, when the server starts;
- **at preflight** — checked only when `scripts/pilot_preflight.py` runs;
- **limitation**;
- **developer default** — awaiting approval;
- **deployment property** — cannot be verified locally.

| ID | Status | Evidence (file, function) | How it applies |
|---|---|---|---|
| A1 | **Partly fixed; D5 open** | `backend/app/routers/questions.py` `_refuse_pilot_overrides`, called from `create_question` and `update_question`: PILOT_MODE refuses a non-empty override with 403 `pilot_overrides_disabled` | **Always** (API). Developer default pending D5. An override written directly to the database is caught only **at preflight** (limitation). Frontend handling verified (§7). |
| A2 | **Fixed in code** | `scripts/pilot_preflight.py` `target_url_problems`, `tls_context` (`ssl.create_default_context`, optional `cafile`), `check_server` (redirect check `final != target`, certificate-failure message) | **At preflight.** Whether IT's real certificate and topology pass is a **deployment property**, not verified (no certificate exists). The check covers the URL the preflight is given. |
| A3 | **Fixed** | `pilot_preflight.py` `settings_override_problems`, used by `check_database`: every `EvaluationConfig` field, unknown keys and non-object values; names only, read-only | **At preflight** only. |
| A4 | **Fixed (self-reported binding)** | `backend/app/model_cache.py` `hub_cache_dir`, `cache_problems`, `snapshot`, `cache_id`, `identity`; `run_server.py` `build_config`; `pilot_preflight.py` `check_model_and_runtime` and `check_server`; `app/main.py` `deployment_summary` (`model_cache`) | **At launch** (launcher refuses conflicts) and **at preflight** (configured model, conflicts, hashed files, server's cache id and revision). The server's report is self-reported (limitation). |
| A5 | **Fixed** | `backend/app/config.py` `Settings._known_environment`, `ENVIRONMENTS` | **Always** (at start-up): normalised; unknown names refuse to start. |
| A6 | **Not fixed: needs faculty decision D2/D6** | `backend/app/routers/enrollments.py` `list_enrollments` returns every enrolled and revoked e-mail to any teacher | Documented in `PILOT_READINESS.md` §3 and §4a, with least-privilege options. |
| A7 | **Partly fixed** | `backend/app/routers/auth.py` `register` writes a `registered` event; `enrollments.py` `enroll` and `revoke` | **Always**, but not atomic (limitation). New finding S6-1 (§6). |
| A8 | **Fixed (test gap); limitation documented** | `backend/app/routers/evaluations.py` `evaluate_one` → `services/publication.py` `record`; tests in `backend/tests/test_security_sprint5.py` (§8 there) with `run_engine` stubbed | **Always**. A failed record write leaves the result unpublished without a log entry (limitation). |
| A9 | **Fixed** | `config.py` `canonical_origin`, `cors_problems` | **Always** in production and pilot (start-up). Development is not validated (unchanged). The approved origins are a **deployment property** (D7). |
| A10 | **Fixed (wording)** | `docs/SPRINT3_SECURITY_REPORT.md` §5 correction note; `docs/SPRINT5_SECURITY_REPORT.md` §6 | 48 distinct protected files; the locked sets are among them (§5). |

**Sprint 2 controls, checked by inspection:**

| Control | Where it lives | What I found |
|---|---|---|
| V1: proxy headers | `run_server.py` `build_config` | Proxy-header processing is on only for explicitly listed `TRUSTED_PROXIES`; it is never uvicorn's implicit 127.0.0.1 |
| V1: launcher required | `app/main.py` lifespan | A PILOT_MODE server refuses to start without the launcher marker |
| V2: manifest hash | `pilot_preflight.py` `check_manifest_hash` | The supervisor's hash is mandatory and must be 64 hexadecimal characters; the manifest's exact bytes are compared |
| V3: concurrency-safe throttling | `app/ratelimit.py` `reserve`/`reserve_all`, used in `auth.py` login, invite and password change | Each attempt reserves a slot before any slow check runs |
| V4: bounded limiter memory | `ratelimit.py` `_sweep`, `MAX_KEYS` | At most 50,000 keys are held; when the table is full of live keys, a new key is refused rather than an existing one evicted |
| V5: password-change throttling | `auth.py` `change_password` | Limited to `PWCHANGE_MAX_FAILURES` failures per `PWCHANGE_WINDOW` |
| V8: pilot marker | `app/deployment.py` `marker_problems`, `fingerprint` | A malformed marker is refused; the fingerprint is tied to the server, the database and the `instance_id` |
| V8: seed safety | `scripts/seed.py` `_not_demo_only` | Seeding refuses any database that is not identifiably demo data |

No discrepancy was found. Their tests in `test_security_hardening2.py` were also re-run (§3).

## 3. Checks actually performed (this sprint)

**Static inspection** of the files and functions listed in §2 and §6, and of
`frontend/src/pages/teacher/QuestionEditor.tsx` and `frontend/src/lib/api.ts`.

**Backend tests.** These ran against a **new, throw-away MongoDB 8.2** server on `127.0.0.1:27999`, with an empty data
directory in the session scratchpad; it was shut down afterwards with only `admin`, `config` and `local` left. They ran
under the guard plugin `s5guard` (also in the scratchpad), which:
- refuses and logs any connection to port 27017;
- replaces the scoring entry point and the model loader with objects that fail if used;
- refuses to open the locked sets, their locks, `dataset.json` and `evaluation/results/*`.

The guard logged **no blocked event** in these runs. Command, run from `backend/` with
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<scratchpad>/guard MONGODB_URI=mongodb://127.0.0.1:27999`:

```
python -B -m pytest -p s5guard -p no:cacheprovider tests/test_security_sprint5.py tests/test_security_hardening2.py -q
```

Result: **exit 0; 154 passed** (sprint5 114, hardening2 40); 0 failed, 0 errors, 0 skipped.

**Withdrawal-window probe (§6).** This one-test file lives **outside the repository**. It ran with the same guard and
throw-away database (`-p s5guard -p tests.conftest`). Result: exit 0, 1 passed, with the observations in §6.

**Frontend tests.** These ran through a vitest config kept **in the scratchpad**. It sets `root` to `frontend/` and
puts the cache in the scratchpad, and it does not load the project's `vite.config.ts` (Vite would bundle that into
`node_modules/.vite-temp`). Command, from `frontend/`:

```
node node_modules/vitest/vitest.mjs run --config <scratchpad>/vitest.isolated.mjs
```

Result: **exit 0; 3 files, 23 passed**: the 22 existing tests and the new `src/test/questionEditor.test.tsx`.
Afterwards, every file under `frontend/` outside `node_modules`, and the `node_modules/.vite*` cache folders, were
byte-for-byte and timestamp-identical to the snapshot taken just before the run.

**Integrity checks:** see §5.

**After the tests:** the comment in `backend/app/routers/enrollments.py` was edited (comment only). That file was
parse-checked; the tests were not re-run for a comment change.

**Historical results, not re-verified now:** the sprint 5 regression run (285 passed) and the sprint 3 runs are
recorded output only. The files they cover that were not re-run here (`test_security_sprint3.py`,
`test_security_remediation.py`, `test_pilot_readiness.py`, `test_auth.py`, `test_assessments.py`,
`test_submissions.py`) are **not re-verified** in this sprint.

## 4. Checks deliberately not run

| Not run | Why |
|---|---|
| Scorer, keyword-list, evaluation-workflow, integrity, preprocessing, metrics and study suites; the 5 scorer-calling security tests | They execute the scoring engine or the study tooling (forbidden) |
| Browser E2E (`docs/e2e_smoke.py`) | Forbidden; it needs the running app |
| Frontend build, typecheck, lint | `tsc -b` and `vite build` write into the working tree (`*.tsbuildinfo`, `dist/`). Type correctness of the new test file was **not** checked by `tsc` (vitest strips types without checking them) |
| Preflight against a real deployment; real TLS, proxy or multi-machine behaviour | No IT topology or certificate exists (D7, B4) |
| Any access to the main MongoDB server (port 27017) | Forbidden. None occurred (§3, guard log) |
| Supervisor's manifest, study-lock or report hashes | Must be computed and kept by the supervisor alone (B5) |

## 5. Protected artifacts

| Group | Distinct files | Compared with | Result |
|---|---|---|---|
| Scoring sources `backend/app/nlp/*.py` | 10 | Hash list recorded in sprint 1 | **10/10 identical** |
| Scoring wiring `backend/app/services/evaluation_service.py` and the engine manifest `backend/scripts/pilot_frozen_engine.json` | 2 | End-of-sprint-3 tree record | **identical** (the manifest's hash value is deliberately not written down: B5) |
| Manifest coverage | 11 | Per-file hashes inside the manifest | **11/11 match** |
| Historical evaluation files | **48**: 43 `results/*`, `dataset.json`, `final_test.json`, `v4_fresh_test.json`, `final_test.sha256`, `v4_fresh_test.sha256` | Recorded hash list | **48/48 identical** |
| Locked sets (2 of the 48 above, not extra) | 2 | Locks in the repository (`*.sha256`), using the project's rule | **both match** |

The locked sets were read only as bytes for hashing. Their contents were not parsed, displayed or used.

**Line-ending rule for `final_test.json`.** `backend/evaluation/common.py` `_load_locked` verifies a locked set by
hashing its bytes **after converting Windows line endings (CRLF) to LF**.
- `final_test.json` is stored with 770 CRLF line endings. Its LF-normalised hash equals its lock (`506c633e…`), but a
  plain `sha256sum` of the raw file gives a different value (`c061c150…`).
- That raw value equals the recorded baseline, so **the file has not changed**.
- `v4_fresh_test.json` has no CRLF, so both methods agree.
- Anyone checking `final_test.json` must apply the CRLF→LF rule, or compare against the recorded raw value.

**What this evidence can and cannot show**
- The scoring and historical hash lists were written **by the development agent itself**, in its session scratchpad.
  They show that nothing changed **during these sprints**. They are **not independent baselines**.
- The `*.sha256` lock files are stored in the repository: they detect accidental change, not deliberate replacement of
  a file and its lock together.
- The project has **no version control**; no third-party baseline exists.
- **Independent verification exists only when the supervisor keeps their own hashes (B5).** None has been taken.

## 6. Enrollment audit and atomicity (A7, S6-1)

No transaction or session abstraction exists anywhere in the code (no `start_session`/`start_transaction`). Each
change is a sequence of separate writes:

| Path | Write 1 | Write 2 | Write 3 | If it fails after write 1 |
|---|---|---|---|---|
| `enroll` (per e-mail, up to 500 per request) | upsert `enrollments` (active) | `users.pilot_enrolled = true` | `enrolled` event | Enrollment active but access not yet granted (**fails closed**); e-mails earlier in the same request are done. Repeating the request completes it (idempotent) |
| `register` (pilot) | insert user, already `pilot_enrolled: true` | link `enrollments.user_id` and `used_at` | `registered` event | The account exists and has access; the list shows "registered: false"; no event. A later revoke still works (it matches by e-mail) |
| `revoke` | `enrollments.revoked_at` | `users.pilot_enrolled = false` | `revoked` event | **S6-1: fails open** (below) |

Access checks read **`users.pilot_enrolled`** (`backend/app/services/access.py`, line 40), not the enrollment document.

**S6-1, reproduced** against the throw-away database by forcing write 2 of `revoke` to fail:
- the request returned 500, and `GET /api/enrollments` showed the participant **inactive**;
- `users.pilot_enrolled` stayed `true`, and the student **could still open an assessment** (HTTP 200);
- repeating the revoke returned **404 "No active enrollment for this e-mail"** and changed nothing;
- the events were `enrolled`, `registered`: no `revoked`;
- recovery worked: enroll the e-mail again, then revoke again. Access then ended (404), with events `enrolled`,
  `registered`, `enrolled`, `revoked`.

This needs a database failure at exactly that moment, but its effect is that a **withdrawal silently does not take
effect** while the list says it did.

**Proposed fixes. None is implemented; approval is needed first, because they change enrollment and access behaviour.**
None needs new infrastructure.
- (a) In `revoke`, clear `users.pilot_enrolled` **first**, so any partial failure fails closed.
- (b) Make a repeated revoke finish a half-done one instead of answering 404.
- (c) Make the student access check also require an active `enrollments` document (defence in depth).

**Other options:**
- Transactions, which need the pilot MongoDB to run as a replica set: an IT decision (D7).
- Unchanged in every case: the event log is **not tamper-proof** against direct database access; events written
  before sprint 5 (and registrations before it) are not back-filled.

**Meanwhile:** `PILOT_RUNBOOK.md` §7 now tells operators how to recover from a failed revoke, and
`PILOT_READINESS.md` §3 lists S6-1.

## 7. Frontend handling of the override refusal (A1)

**Verified.** Static reading of `QuestionEditor.tsx`:
- **On error:** the `save` mutation's `onError` shows `toast.error(err.message)`, which is the server's `detail` text
  carried by `ApiError` (`lib/api.ts`, `request`).
- **On success only:** `onSuccess` (success toast, cache invalidation, navigation) runs only when the save succeeds.
- **Form state:** it lives in `useState` and is not reset. The load effect is guarded by `loadedId`, so a refetch does
  not overwrite edits.

**New test** `frontend/src/test/questionEditor.test.tsx`. It mocks `fetch` (no backend, database or engine), so the
PATCH returns the documented 403 with `{detail, code: "pilot_overrides_disabled"}`. The test checks that:
- the server's refusal text is shown;
- exactly one PATCH carried the override;
- no success message appears and the page does not navigate away;
- the edited question text and both threshold values are still in the form;
- the Save button is usable again.

It passed.

**Not verified:**
- that the backend's 403 reaches the browser unchanged through a real deployment (TLS, proxy);
- type-checking of the test file (§4).

The policy is unchanged: the pilot default stays fail-closed, and D5 is a faculty decision.

## 8. Handoff checklist

Nothing below is approved. Each item stays open until the named evidence exists. **Do not infer approval from code,
tests or completed templates.**

### Blockers

| # | Status | Owner | Evidence needed to close |
|---|---|---|---|
| B1 Acceptance criteria | **OPEN** | Faculty (approve); supervisor (confirm) | All **13** criterion values in the study's `acceptance_criteria.json`. The template lists: `min_answers`, `min_questions`, `min_answers_per_question`, `min_teacher_concept_kappa`, `min_teacher_within_1`, `max_normalised_mae_ci_upper`, `min_within_1_ci_lower`, `max_mae_ratio_to_teacher_mae`, `max_severe_error_share`, `max_severe_error_share_per_question_type`, `keyword_baseline_rule`, `v3_rule`, `require_flagged_mae_above_unflagged`. Also `approved_by`, `approved_on`, `approval_evidence` (e.g. signed minutes), and both attestations. The supervisor checks the evidence independently. The file lives in the study directory, outside the repository |
| B2 Ethics and consent | **OPEN** | Ethics reviewers | Ethics approval or a documented exemption (with its reference); approved information sheet and consent form (`study_templates/information_sheet_and_consent.template.md` is a template, not an approval); retention and deletion rules (D4) |
| B3 Independent marking | **OPEN** | Faculty | A named second marker and a named adjudicator, independent of the developer; the blind-marking and adjudication procedure, agreed in writing (`REAL_STUDENT_EVALUATION_PROTOCOL.md`) |
| B4 Safe deployment | **OPEN (technically prepared)** | Faculty (authorise); IT (topology) | Written deployment authorisation. A dedicated pilot database initialised with `scripts.pilot_init_db`. IT's written network topology: who terminates TLS, the certificate and CA, approved https CORS origins in exact browser form, any proxy address, whether MongoDB is a replica set. Model-cache variables unset on the server. `pilot_preflight --url https://… --manifest-sha256 …` → **PASSED** on the real deployment. Written acceptance of the residual risks (D10), including S6-1 or its approved fix |
| B5 Supervisor evidence | **OPEN** | Supervisor | A named supervisor who computes and keeps, **outside the repository and the study team's control**: the SHA-256 of `backend/scripts/pilot_frozen_engine.json`, and later the study-lock and report hashes. They run `verify` and supply the manifest hash to every preflight. Hashes prove file integrity only, not consent, blind marking or adjudication |

### Decision register

The labels, owners and decision questions are copied exactly from `PILOT_READINESS.md` §4. The technical-fact column
is a summary of that register, including its dated sprint 5 corrections and the verified sprint 6 finding S6-1; the
register itself stays authoritative. **All are undecided.**

| # | For | Decision | Current technical fact | Status | Action needed from |
|---|---|---|---|---|---|
| D1 | Faculty | Global or study-specific enrollment? | One global allowlist | Undecided | Faculty |
| D2 | Faculty | Who may enroll, revoke and view participants? | Any teacher; enroll, revoke and registration are logged, viewing is not; writes not atomic (S6-1) | Undecided | Faculty; also decides A6 |
| D3 | Faculty + ethics | What happens to existing submissions after withdrawal? | Access to assessments ends; existing work can still be reviewed, re-evaluated and published | Undecided | Faculty and ethics |
| D4 | Ethics | Retention and deletion obligations | Nothing is deleted automatically | Undecided | Ethics |
| D5 | Faculty | Per-question threshold overrides in the pilot? | Preflight fails on any override; API refuses them in PILOT_MODE (developer default) | Undecided | Faculty |
| D6 | Faculty | Teacher-to-student scoping | None beyond enrollment; the pilot directory lists only enrolled participants (developer default) | Undecided | Faculty; also decides A6 |
| D7 | IT | TLS topology, certificates, approved CORS origins, proxy addresses | Launcher and preflight enforce TLS; no values supplied | Undecided | IT (plus whether MongoDB is a replica set) |
| D8 | Faculty | Refuse fallback evaluations outright in the pilot? | Fallback allowed; publication needs a teacher mark with a reason | Undecided | Faculty |
| D9 | Faculty | Token storage migration | `localStorage` with server-side revocation | Undecided | Faculty |
| D10 | Faculty | Acceptance of the §3 residual risks | Not accepted | Undecided | Faculty (and the supervisor witnesses B5) |

**Also needs approval:** the S6-1 fix proposal (developers propose; faculty or the project lead approves, because it
changes access behaviour), and the developer defaults in `PILOT_READINESS.md` §4a (faculty confirm or reverse).

### What each group does next

- **Faculty:**
  - decide D1, D2, D3 (with ethics), D5, D6, D8, D9 and D10;
  - confirm or reverse the developer defaults;
  - approve or reject the S6-1 fix;
  - approve B1 with evidence;
  - name the second marker, the adjudicator (B3) and the supervisor (B5);
  - authorise or decline deployment (B4).
- **Ethics reviewers:**
  - decide B2 and D4;
  - advise on D3;
  - advise whether withdrawn participants' e-mails may stay visible to teachers (A6).
- **IT:**
  - deliver the D7 topology in writing, with certificates or a CA and the origins;
  - say whether the pilot MongoDB is a replica set;
  - confirm that the model-cache variables are unset on the server.
- **Supervisor:**
  - after authorisation, compute and keep the manifest hash independently;
  - later keep the study-lock and report hashes;
  - run `verify` and the preflight;
  - check B1's evidence.
- **Developers:**
  - wait for approval before implementing the S6-1 fix;
  - put the project under version control only when approved, with the initial commit recorded externally;
  - run `tsc` on the new frontend test in an isolated copy of the project;
  - do not start any further work toward a pilot until B1–B5 change.

## 9. Real-world accuracy

**Real-world grading accuracy remains unknown.** It can only be established by the study in
`REAL_STUDENT_EVALUATION_PROTOCOL.md`: real, consented answers, two independent markers, adjudication and pre-approved
criteria.

## 10. High-stakes use

**High-stakes, summative and unreviewed grading remain NO-GO.** At most, after B1–B5 are verified, D1–D10 are
decided and the risks are accepted, a CONDITIONAL GO is possible for a low-stakes pilot in which a teacher reviews
every AI suggestion before publication. That is not granted here.

## Files changed in sprint 6

| File | Reason |
|---|---|
| `frontend/src/test/questionEditor.test.tsx` (new) | A1 frontend regression test |
| `backend/app/routers/enrollments.py` | Comment only: the three-write sequence and S6-1 |
| `docs/PILOT_READINESS.md` | §3: S6-1 row with the proposed fixes (not implemented) |
| `docs/PILOT_RUNBOOK.md` | §7: recovery steps after a failed revoke |
| `docs/SPRINT5_SECURITY_REPORT.md` | Correction note (A7 wording; A1 frontend now verified) |
| `docs/SPRINT6_FINAL_SIGNOFF.md` (new) | This report |

No scoring source, historical file, locked set, lock file, engine manifest or scoring wiring was changed. Git was not
added. No database was accessed except the throw-away one. Nothing was deployed and no account was created.
