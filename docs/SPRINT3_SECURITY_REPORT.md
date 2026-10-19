# Sprint 3: residual-risk closure. Security report

**Date:** 2026-10-17. **Scope:** residual technical risks after security hardening sprint 2. **Not** a scoring change:
no scoring code, weight, threshold, normalisation, similarity, fallback behaviour, question override, locked data
or historical result was modified.

## 1. Executive decision: **NO-GO**

The application is technically improved but **not authorised for a pilot**:
- all five external blockers B1–B5 are open (§8);
- the policy decisions D1–D10 are unmade (`PILOT_READINESS.md` §4);
- the residual risks have not been accepted in writing.

Passing tests and completed documents are not approvals.
**Real-world grading accuracy remains unknown.** All existing evaluation results are synthetic, developer-written and
single-marker. **High-stakes and unreviewed grading remain NO-GO** regardless of any result.

## 2. Findings

| Finding | Status | What changed | Tests (`tests/test_security_sprint3.py` unless noted) |
|---|---|---|---|
| **F5/V9** Sessions survived password changes | **Fixed (revocation)** | Server-side session version: tokens carry `sv`, and every request compares it with `users.session_version`. A password change and the new `POST /api/auth/logout-all` increment the version, revoking every earlier token (including a stolen one), and return a fresh token for the requesting device. Tokens issued before this change (no `sv`) count as version 0 and stay valid until the first revocation event. Malformed `sv` values are rejected. The frontend stores the renewed token after a password change. | old tokens refused on `/me` and on a protected route after a password change (both devices); sign out everywhere; legacy token valid until revocation; forged `sv` values rejected; sprint 2 test updated to use the renewed token |
| **F5** Token in `localStorage` | **Not fixed: documented** | Migrating to httpOnly cookies needs CSRF protection, credentialed CORS and a same-site deployment. The plan is in §7. Revocation now limits a stolen token's useful life. | — |
| **F6** Secret quality, CORS | **Fixed** | `secret_problems` (missing, placeholder words, < 32 characters, < 16 distinct characters, repeated patterns, < 128-bit entropy estimate; never echoes the value) applies in PILOT_MODE **and production**. `cors_problems` requires well-formed `scheme://host[:port]` origins with no `*`, `null`, path, query or wildcard host; https is required in PILOT_MODE. The approved origins are operator/IT-supplied, never invented. | 6 weak-secret cases; 20 random secrets accepted; 10 CORS cases; production refuses a weak secret and `*` (secret not echoed); pilot requires https |
| **V6** Enrollment / withdrawal / publication | **Partly: audit fixed, policy open** | Every enroll and revoke is appended to `enrollment_events` (action, e-mail, actor, time). The `enrollments` document is documented as **mutable current state** (not append-only). Withdrawal behaviour is **unchanged** and characterised by a test; whether withdrawal blocks review and publication is a faculty and ethics decision (D1–D4). | event log keeps the history across re-enrollment; characterisation test of current withdrawal behaviour |
| **V7** Frozen model/configuration identity | **Partly fixed** | Manifest extended: `model_artifacts` (cached snapshot revision + exact-byte SHA-256 of all 11 model, tokenizer and config files, hashed from disk **without loading the model**) and `runtime` (Python + 10 scoring-library versions from package metadata). The preflight fails closed on any mismatch, a missing cache, a missing section, or **any per-question threshold override** in the pilot database. The launcher sets `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` in PILOT_MODE so the model is loaded only from the hashed cache. The manifest's identity and source-file hashes are unchanged. | model/runtime PASS on this machine; 6 tamper cases; missing cache; missing sections; overrides fail; launcher pins offline |
| **V10** Empty reviews; publication identity | **Fixed** | A review that marks work reviewed must state a decision: the `teacher_score` field (null = accept the AI score, as the UI sends it) or `accept_ai_score=true`. `{}` → 422; both together → 422. Each review-log entry records its `decision`. New `app/services/publication.py` records `published_by`/`unpublished_by` and appends to `publication_log` on publish, unpublish, bulk publish and re-evaluation unpublish. **Older records are not back-filled.** The UI now stores the teacher's mark as entered, even when equal to the AI score, which fixes a conflict with the fallback gate. | empty review refused (nothing logged); conflicting body refused; 3 decision types logged with the reviewer; publish/unpublish/bulk identity and timestamps; legacy records untouched |
| **V11** Student directory | **Partly fixed** | In PILOT_MODE the teacher directory lists only enrolled participants (non-participants cannot take part, so their e-mails are not needed). Development is unchanged. Per-teacher scoping needs a class model that does not exist (D6). | directory scoping pilot vs development |
| **V12** TLS and topology | **Fixed for the launcher path; topology itself open** | The PILOT_MODE launcher **refuses to start** beyond loopback without TLS: either `--ssl-certfile` + `--ssl-keyfile` (both readable) → `tls-direct`, or `TLS_TERMINATED_BY_PROXY=true` with the proxy in `TRUSTED_PROXIES` → `tls-proxy`. Health reports the transport; the preflight requires `tls-direct` or `tls-proxy`. Certificates and proxy addresses are never generated or assumed. | 7 transport-mode cases; preflight transport (6 cases); proxy declaration needs a proxy; health reports transport without secrets |

**Re-verification of V1–V5 and V8.** The sprint 2 tests still pass unchanged in assertion (`test_security_hardening2.py`,
40 tests): forged-header resistance through uvicorn's real middleware, the mandatory supervisor hash, atomic
reservations under 20 parallel requests, bounded and swept limiter storage, password-change throttling, and marker,
identity and seed safety. **No regression was found.** Setup-only updates: the proxy-list test now declares TLS
termination (sprint 3 enforces TLS in the pilot), the real-health test reports `tls-direct`, and the password-change test
uses the renewed token.

## 3. Files changed

| File | Reason |
|---|---|
| `backend/app/security.py` | Session version `sv` in tokens; strict decoding (F5/V9) |
| `backend/app/deps.py` | Reject tokens whose `sv` differs from the user's session version (F5/V9) |
| `backend/app/routers/auth.py` | Revoke sessions on password change; `logout-all`; pilot-scoped student directory (F5/V9, V11) |
| `backend/app/schemas/auth.py` | `SessionRenewedOut` response (F5/V9) |
| `backend/app/config.py` | `secret_problems`, `cors_problems`, `TLS_TERMINATED_BY_PROXY`; production checks (F6, V12) |
| `backend/app/main.py` | Health reports the transport (V12) |
| `backend/app/routers/evaluations.py` | Explicit review decision; decision in the review log; re-evaluation unpublish recorded (V10) |
| `backend/app/schemas/evaluation.py` | `accept_ai_score` field (V10) |
| `backend/app/routers/results.py` | Record publish/unpublish identity (V10) |
| `backend/app/services/publication.py` (new) | Publication identity and log (V10) |
| `backend/app/routers/enrollments.py` | Append-only `enrollment_events`; mutable-state documentation (V6) |
| `backend/scripts/run_server.py` | TLS enforcement in the pilot; offline model cache (V12, V7) |
| `backend/scripts/pilot_preflight.py` | Model/runtime/override checks; TLS check (V7, V12) |
| `backend/scripts/pilot_frozen_engine.json` | Added `model_artifacts` and `runtime`; identity and source hashes unchanged (V7). **Its SHA-256 changed: the supervisor must record the new value themselves.** |
| `backend/scripts/seed.py` | `enrollment_events` is an app collection (keeps the seed guard correct) |
| `backend/.env.pilot.example`, `README.md` | `TLS_TERMINATED_BY_PROXY`; https CORS and secret guidance |
| `frontend/src/pages/Profile.tsx` | Store the renewed token after a password change (F5/V9) |
| `frontend/src/pages/teacher/SubmissionReview.tsx` | Send the teacher's mark as entered (V10 / fallback gate) |
| `backend/tests/test_security_sprint3.py` (new) | 51 regression tests |
| `backend/tests/test_pilot_readiness.py`, `test_security_hardening2.py`, `test_security_remediation.py` | Setup-only updates required by the stricter rules (random test secret, https test origin, TLS in the health helper, explicit accept decision, renewed token). **No assertion removed or loosened.** |
| `docs/PILOT_READINESS.md`, `docs/PILOT_RUNBOOK.md`, this report | Evidence, decision register, procedures |

`backend/app/services/evaluation_service.py` and all `backend/app/nlp/*.py` files were **not** modified.

## 4. Tests run

Commands were run from `backend/` with `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider -o addopts=""`.

| Command | Exit | Result |
|---|---|---|
| `pytest tests/test_security_sprint3.py` (final) | 0 | **51 passed**, 0 skipped (the model is cached on this machine, so the model-hash checks ran) |
| `pytest tests/test_security_sprint3.py tests/test_security_hardening2.py tests/test_security_remediation.py tests/test_pilot_readiness.py tests/test_auth.py tests/test_assessments.py tests/test_submissions.py tests/test_real_study.py -k "not score_once and not score_refuses and not supervisor_verify"` | 0 | **192 passed, 3 deselected** (51 + 40 + 39 + 25 + 8 + 8 + 7 + 14) |
| `npm test` (frontend) | 0 | 22 passed (2 files) |
| `npm run typecheck` / `npm run lint` / `npm run build` | 0 / 0 / 0 | clean / clean / built |

During development, intermediate runs failed and were fixed **in code or test setup, never by loosening assertions**:
- a syntax error in `config.py`;
- preflight row order (implementation reordered so existing positional assertions hold);
- a revoked token reused by an old test (the test now uses the renewed token);
- a too-short fixture title;
- a missing `evaluated` status in a new fixture.

**Deliberately not run**, because they execute the scorer or load locked data:
- the scorer suites (`test_scorer*.py`) and `test_keyword_list_v4.py`;
- `test_evaluation_flow.py`, `test_evaluation_integrity.py` and `test_preprocessing.py`;
- the three study-scoring tests in `test_real_study.py`;
- browser E2E.

Code paths that only those suites exercise remain **untested in this sprint**, notably the publication record written by `evaluate_one`'s re-evaluation path.

## 5. Protected artifacts (before → after)

| Artifact | Before (sprint 3 baseline) | After |
|---|---|---|
| 10 scoring source files (`app/nlp/*.py`) | combined `3e955cae8eaff6a5`; 10/10 equal the original baseline | **10/10 byte-identical**; combined `3e955cae8eaff6a5` |
| 48 historical evaluation files | combined `7a8831b0183d0810`; 48/48 equal the original recorded list | **48/48 byte-identical**; combined `7a8831b0183d0810` |
| Locked sets `final_test.json` / `v4_fresh_test.json` | match the recorded locks `506c633e…` / `fac9428c…` | **match** |

Method: SHA-256 per file against hash lists kept in the session scratchpad (outside the repository).

> **Sprint 5 correction (finding A10).** The rows above overlap: the 48 historical files **already include** both locked
> sets, their two `.sha256` lock files and `dataset.json` (the other 43 are `results/*` files). "48 files plus both
> locked sets" therefore means 48 distinct files, not 50. The locked-set row is a second, stronger check of two of those
> files: against the lock hashes stored in the repository rather than against the session lists. The session hash lists
> were written by the same development agent that made the changes, so they show the files did not change during the
> sprint. They are **not independent evidence**. See [SPRINT5_SECURITY_REPORT.md](SPRINT5_SECURITY_REPORT.md) §6.

## 6. Database-access statement

The main `answerwise` database was **not connected to, inspected, modified, seeded, migrated, reset or deleted**.
- Every test used the conftest's disposable `answerwise_test_<pid>` or a dedicated `answerwise_sec*/preflight_test_*` database, dropped afterwards.
- No deployment, pilot enablement for participants, or real account was created.

The project is not a Git repository, so the pre-sprint state was recorded as file hashes. The tree was identical to the end of sprint 2.

## 7. Remaining risks and deployment assumptions

* **Token storage (F5).** Migration plan for httpOnly cookies (needs authorisation):
  1. `/login` sets a `Secure; HttpOnly; SameSite=Strict` session cookie;
  2. the API accepts that cookie plus a required custom header (CSRF defence);
  3. CORS switches to `allow_credentials=True` with exact origins;
  4. the frontend and API are served same-site;
  5. the frontend stops using `localStorage`;
  6. `logout` clears the cookie;
  7. session versioning stays in place.

  Risks: CSRF if the header rule is missed; a cross-site deployment breaks; existing tokens need a transition period.
* **V7.** Preflight verifies model files **on disk**, not the weights in the running server's memory. Health reports a
  version string, not a source hash. Transitive dependencies, OS, CPU and numeric libraries are not pinned. The study
  tool's comparison profiles (`evaluation/common.py`) and keyword baseline are outside the manifest. Rubric text and
  keywords are teacher content, captured per evaluation by `rubric_fingerprint`.
* **V12.** `TLS_TERMINATED_BY_PROXY=true` is an unverifiable operator statement. Certificate validity is not checked by
  the launcher (uvicorn fails at start-up on unusable files).
* **Untested assumptions:** a real TLS certificate chain, a real reverse proxy, multi-machine deployment, more than 20
  parallel requests, and behaviour across restarts (in-memory rate limits reset).
* **Operational:** one server process; preflight after every restart and before every session; the fallback
  limitation (a PASS does not guarantee that fallback scoring cannot occur later).

## 8. Blocker register

| # | Status | Evidence required to close |
|---|---|---|
| B1 Acceptance criteria | **OPEN** | All 13 values plus `approved_by`, `approved_on` and `approval_evidence`; independent confirmation by the supervisor |
| B2 Ethics and consent | **OPEN** | Ethics approval or documented exemption; approved information sheet and consent form |
| B3 Independent marking | **OPEN** | Named second marker and adjudicator; blind-marking and adjudication procedure accepted |
| B4 Safe deployment | **OPEN** | Written deployment authorisation; IT-approved TLS topology, certificates, origins and proxy addresses; dedicated pilot database initialised; preflight PASSED on the real deployment with the supervisor's hash; written acceptance of residual risks and D1–D10 |
| B5 Supervisor evidence | **OPEN** | Named supervisor holds the manifest (new value after this sprint), study-lock and report hashes outside the repository, and runs `verify`. Hashes prove file integrity only. |

## 9–10. Statements

* **Real-world grading accuracy remains unknown.** No real student answers have been evaluated, and synthetic results
  are not evidence of real-world performance.
* **High-stakes and unreviewed grading remain NO-GO**, whatever this or any later technical result shows.

## Next human actions

1. **Faculty / project team:**
   - set and sign the 13 acceptance criteria with evidence (B1);
   - name the second marker, adjudicator and supervisor (B3, B5);
   - decide D1–D6 and D8–D10;
   - accept or reject the residual risks in writing;
   - authorise or decline deployment (B4).
2. **Ethics reviewers:** approve the study and consent material or record an exemption (B2); decide withdrawal,
   retention and deletion (D3, D4).
3. **IT:** document the topology; issue TLS certificates; supply the approved https origins and any proxy address
   (D7, B4).
4. **Supervisor:** after deployment approval, compute and keep the manifest's SHA-256 outside the project; later keep
   the study-lock and report hashes; run `verify` (B5).
