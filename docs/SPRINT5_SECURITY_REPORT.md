# Sprint 5 security report: closing audit findings A1–A10

**Date:** 2026-10-17. **Scope:** the technical findings of the sprint 4 independent read-only audit.
No scoring code, weight, threshold, normalisation, similarity or fallback behaviour was changed. No locked evaluation
data was loaded, and the scoring engine was not run. Nothing was deployed. The main database was not accessed (§7).

## 1. Executive decision: **NO-GO**

| Reason | Status |
|---|---|
| B1 acceptance criteria approved with evidence | **OPEN**: no approval evidence exists |
| B2 ethics approval or exemption; consent material | **OPEN** |
| B3 named second marker and adjudicator | **OPEN** |
| B4 deployment authorisation, IT topology and certificates, preflight PASS on the real deployment | **OPEN**: technically prepared only |
| B5 supervisor holds the manifest, study-lock and report hashes and runs `verify` | **OPEN**: no supervisor hash exists; none was computed for them |
| Decisions D1–D10 | **None decided** (`PILOT_READINESS.md` §4) |
| Residual risks (§8, `PILOT_READINESS.md` §3) | **Not accepted** in writing |

Passing tests are not approvals. **Real-world grading accuracy remains unknown**: all existing results are synthetic,
developer-written and single-marker. **High-stakes and unreviewed grading remain NO-GO** under every outcome.

## 2. Findings A1–A10

> **Sprint 6 corrections** ([SPRINT6_FINAL_SIGNOFF.md](SPRINT6_FINAL_SIGNOFF.md)).
> - **A7:** "the change stands (access is still revoked, which fails safe)" holds only when the *event* write fails.
>   Revocation is itself two state writes, and a failure between them leaves access in place (finding S6-1).
> - **A1:** the frontend handling of the 403, listed as not verified in §5, is now verified by a frontend test.

| ID | Finding (sprint 4) | Status | What changed | What remains |
|---|---|---|---|---|
| **A1** | Questions API accepted threshold overrides in PILOT_MODE; the preflight caught them only when it ran | **Partly fixed; D5 needs a human decision** | In PILOT_MODE, `POST /api/questions` and `PATCH /api/questions/{id}` refuse a non-empty override (403 `pilot_overrides_disabled`). Removing an override is still allowed. Development behaviour is unchanged. | An override written **directly to the database** still changes AI suggestions until the next preflight. Refusing to evaluate such a question would change evaluation behaviour, which is a policy decision (D5). |
| **A2** | Preflight did not require `https://`; TLS came only from the server's own report | **Fixed in code; not verified on a real deployment** | In PILOT_MODE `--url` must be an absolute `https://` base URL with a host. The preflight verifies the certificate and host name itself (`ssl.create_default_context`), and nothing can switch verification off. `--cafile` adds IT's CA for an internal CA. A redirect fails. An empty `--url` now fails instead of skipping the server check. | No real certificate or topology exists (D7). The check covers the URL the preflight was given, not every route a browser could take. |
| **A3** | Preflight checked only two settings keys; the engine applies any `EvaluationConfig` field | **Fixed** | The preflight fails on **any** non-null settings key in the pilot database: every engine configuration field, any unknown key, and any non-object `settings`. It reports key names and counts, never values, and modifies nothing. | No override is permitted until D5 is decided and an approved policy is recorded. |
| **A4** | `SENTENCE_TRANSFORMERS_HOME` (and similar) ignored, so the server could load files the preflight never hashed | **Fixed (self-reported binding)** | New `app/model_cache.py` resolves the cache with the libraries' precedence (`HF_HUB_CACHE` > `HUGGINGFACE_HUB_CACHE` > `HF_HOME/hub` > `$XDG_CACHE_HOME/huggingface/hub` > `~/.cache/huggingface/hub`). It flags as conflicts: `SENTENCE_TRANSFORMERS_HOME`, `TRANSFORMERS_CACHE`, `PYTORCH_TRANSFORMERS_CACHE` and `PYTORCH_PRETRAINED_BERT_CACHE` when they point elsewhere; set-but-empty variables; two hub variables that disagree; and a local directory named like the model in the working directory, which sentence-transformers would load instead. In PILOT_MODE the launcher refuses to start on any conflict. The preflight fails on conflicts, on an `EMBEDDING_MODEL` other than the frozen model, and when the server reports a different cache, a different revision or a conflict. | The server's cache report is self-reported: it catches mistakes, not a deliberate lie by someone controlling the server. The preflight must run on the server machine in the server's environment. |
| **A5** | `ENVIRONMENT` compared case-sensitively, so `Production` ran as development | **Fixed** | `ENVIRONMENT` is stripped and lower-cased, and must be `development` or `production`; anything else (including empty) refuses to start. `Production` and `PRODUCTION` now trigger the secret check, the CORS check and the seed block. A missing value stays `development`. | — |
| **A6** | `GET /api/enrollments` exposes enrolled **and revoked** e-mails to every teacher | **Not fixed: needs a faculty decision (D2/D6)** | Confirmed in code (`routers/enrollments.py`, `list_enrollments`). Documented with least-privilege options in `PILOT_READINESS.md` §4a and §3. | The policy is undecided; no access rule was changed. |
| **A7** | Registration changed the enrollment without an event; the docstring overstated completeness; writes are not atomic | **Partly fixed** | Registration now writes a `registered` event (actor: the student). The docstring and the readiness document are corrected. Tests cover the order of enroll → registered → revoke, and characterise a failed event write. | Atomicity is **not** implemented. MongoDB transactions need a replica set, and the pilot database topology is not decided. On a failed event write, the change stands (access is still revoked, which fails safe) and the request returns 500; no event is ever written for a change that did not happen. Migration path: replica-set pilot database, then both writes in one transaction. The log is not tamper-proof. |
| **A8** | `evaluate_one`'s re-evaluation publication record was untested | **Fixed (test gap); limitation documented** | Tests with `evaluation_service.run_engine` **stubbed** (the real engine also guarded) cover: the re-evaluation record (action, actor, timestamp within the request window, the earlier record not rewritten, the evaluations unpublished); re-evaluation without confirmation leaves publication untouched; and a failed publication-record write. | No atomic guarantee. If the record write fails, the result is unpublished **without** a log entry and the request returns 500; it is never shown as published. |
| **A9** | CORS validator accepted a trailing slash, port 99999 and `HTTPS://` | **Fixed** | `canonical_origin` parses the origin structurally. It requires the http(s) scheme; a valid DNS host, IPv4 or bracketed IPv6; a port from 1 to 65535; and no path, query, fragment, credentials, wildcard, whitespace or non-ASCII characters. An entry not already in the exact form browsers send is **refused with its canonical spelling**, never rewritten. The pilot still requires https. Development defaults are unaffected. | Origin values come from IT (D7). |
| **A10** | Reports counted "48 historical files **and** both locked sets" | **Fixed (wording)** | A correction note in `SPRINT3_SECURITY_REPORT.md` §5, and §6 below. | — |
| A11 (INFO) | Developer defaults presented as facts | **Documented** | `PILOT_READINESS.md` §4a lists every developer default and the decision it anticipates. | Faculty confirmation. |

### Why the A1 API block was implemented, not left pending

Before this sprint, the documented requirements already made any override incompatible with a valid pilot:
- the runbook (§2 item 2) says not to use overrides;
- the preflight fails while one exists, and it must pass before every session;
- D5's stated default is "Keep forbidden".

The API block therefore enforces the **existing** fail-closed rule earlier. It does not change the score of any
question that the pilot could legitimately run, and it changes nothing outside PILOT_MODE. It is reversible. It does
**not** decide D5. If faculty permit overrides, the block would be replaced by an approved, manifest-recorded override
policy. It is listed as a developer default in `PILOT_READINESS.md` §4a.

## 3. Files changed

| File | Change | Finding |
|---|---|---|
| `backend/app/config.py` | `ENVIRONMENT` validator (normalise, refuse unknown); `canonical_origin` and stricter `cors_problems` | A5, A9 |
| `backend/app/model_cache.py` (new) | Cache resolution, conflict detection, snapshot lookup, opaque cache id; reads paths only, never loads the model | A4 |
| `backend/app/main.py` | `/api/health` deployment summary also reports `model_cache` (id, revision, conflicts; no path) | A4 |
| `backend/app/routers/questions.py` | Refuse saving overrides in PILOT_MODE | A1 |
| `backend/app/routers/auth.py` | `registered` enrollment event on pilot registration | A7 |
| `backend/app/routers/enrollments.py` | Docstring corrected: what is logged, non-atomic writes, not tamper-proof | A7 |
| `backend/scripts/pilot_preflight.py` | URL validation, verifying TLS context, `--cafile`, redirect check; every settings key; configured-model, cache-conflict and server-cache rows | A2, A3, A4 |
| `backend/scripts/run_server.py` | In PILOT_MODE, refuse an ambiguous model location | A4 |
| `backend/tests/test_security_sprint5.py` (new) | 114 tests for A1–A9 | all |
| `backend/tests/test_pilot_readiness.py` | **Setup only:** the health stub reports `model_cache`; the scratch-database fixture uses the configured `MONGODB_URI` instead of a hard-coded `localhost:27017`; the preflight URL is now `https://` | A2, A4, isolation |
| `backend/tests/test_security_hardening2.py`, `test_security_remediation.py` | **Setup only:** preflight URLs `http://pilot` → `https://pilot`; fixtures use the configured `MONGODB_URI` | A2, isolation |
| `backend/tests/test_security_sprint3.py` | **Setup only:** the override row's name follows its rename (the same PASS/FAIL assertions) | A3 |
| `docs/PILOT_READINESS.md` | Controls, residual risks (A1 rest, A6, A7), §4a developer defaults and privacy; D2/D5 fact columns get dated corrections, with labels and questions unchanged | A1, A6, A7, A11 |
| `docs/PILOT_RUNBOOK.md` | https `--url` and `--cafile`, CORS spelling, `ENVIRONMENT` values, model-cache rules, new fail-closed items | A1–A5, A9 |
| `docs/SPRINT3_SECURITY_REPORT.md` | Correction note on the 48-file count and baseline independence | A10 |

No assertion was removed or loosened. The edits to existing tests change URLs, a renamed row label, a stub field and a
database URI. `app/nlp/*.py`, `app/services/evaluation_service.py` and `scripts/pilot_frozen_engine.json` are
**unchanged**, so the manifest bytes, and any supervisor hash of them, are unaffected.

## 4. Tests run

**Isolation set-up**, all outside the repository, in the session scratchpad `$S`:
- **A throwaway MongoDB 8.2 server** started on `127.0.0.1:27999` with a new, empty data directory
  (`mongod --port 27999 --bind_ip 127.0.0.1 --dbpath $S/mongo-data`). Before the tests it held only `admin`, `config`
  and `local`; afterwards the same, because every test database was dropped. It was then shut down.
- **A pytest plugin `s5guard`**, loaded with `-p s5guard`:
  - it sets `MONGODB_URI` to the throwaway server;
  - it refuses and logs any socket connection to port 27017 (the main server's port);
  - it replaces `app.nlp.evaluate_answer` and `get_backend` with stubs that raise;
  - it refuses to open the locked sets, their lock files, `dataset.json` and `evaluation/results/*`.
- **A probe confirmed the guard works:** a scoring call, a ping to port 27017 and an open of `final_test.json` were each
  refused (3 passed). No connection was established and no byte of that file was read.

**Commands** (from `backend/`, environment `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$S/guard MONGODB_URI=mongodb://127.0.0.1:27999`):

```
python -B -m pytest -p s5guard -p no:cacheprovider tests/test_security_sprint5.py -rs -v
python -B -m pytest -p s5guard -p no:cacheprovider tests/test_security_sprint5.py tests/test_security_sprint3.py \
  tests/test_security_hardening2.py tests/test_security_remediation.py tests/test_pilot_readiness.py \
  tests/test_auth.py tests/test_assessments.py tests/test_submissions.py \
  -k "not (test_empty_review_is_not_a_review or test_publication_records_who_and_when or
           test_review_decisions_are_explicit_and_logged or
           test_withdrawal_policy_is_undecided_current_behaviour_documented or
           test_fallback_scored_results_need_a_teacher_mark_with_reason_in_pilot_mode)" -rs -v --junitxml=$S/...xml
```

| Run | Exit code | Passed | Failed | Errors | Skipped | Deselected |
|---|---|---|---|---|---|---|
| `test_security_sprint5.py` alone | 0 | 114 | 0 | 0 | 0 | 0 |
| Regression set, final run with the corrected guard | 0 | **285** | 0 | 0 | 0 | 7 |

Per file: sprint5 114, sprint3 45, hardening2 40, remediation 38, pilot_readiness 25, auth 8, assessments 8,
submissions 7. The guard log recorded no blocked event in either run. The certificate tests used a real local TLS
server: a stdlib `http.server`, **not the application**, with a throw-away self-signed certificate made in `tmp_path`.
- no CA supplied → the certificate was not verified and the check failed;
- a certificate for another host → failed;
- the CA supplied with `--cafile` → verified.

## 5. Tests deliberately not run

| Test | Why |
|---|---|
| 7 items (5 tests) in `test_security_sprint3.py` (empty review, publication records, review decisions, withdrawal characterisation) and `test_security_remediation.py` (fallback teacher mark) | They call `/api/evaluations` and so run the real scoring engine. They are unaffected by this sprint's changes. |
| `test_scorer*.py`, `test_keyword_list_v4.py`, `test_evaluation_flow.py`, `test_evaluation_integrity.py`, `test_preprocessing.py`, `test_metrics.py`, `test_real_study.py` | Scorer, keyword-list, evaluation-workflow, integrity, preprocessing and study suites: forbidden or out of scope. None of their code changed. |
| Frontend unit tests, typecheck, lint, build | No frontend file changed. The build and typecheck write into the repository. **Not verified:** how the question editor shows the new 403 `pilot_overrides_disabled` message. |
| Browser E2E | Forbidden. |
| Preflight against a real TLS deployment | No IT certificate or topology exists (D7, B4). |

During exploration, one `python -c "import sentence_transformers"` failed at import time (a protobuf/TensorFlow
version error). No model was loaded, nothing was scored, and nothing in the repository was written.

## 6. Protected artifacts

| Group | Distinct files | Check | Result |
|---|---|---|---|
| Scoring source `backend/app/nlp/*.py` | 10 | SHA-256 against the pre-sprint baseline and the original sprint 1 list | **10/10 identical** |
| Engine-manifest coverage (`app/nlp/*.py` plus `app/services/evaluation_service.py`) | 11 | Against `scripts/pilot_frozen_engine.json` | **11/11 match**. The manifest file itself is byte-identical to the pre-sprint file; its hash value is deliberately not recorded here (B5) |
| Historical evaluation files | **48** = 43 `results/*` + `dataset.json` + `final_test.json` + `v4_fresh_test.json` + `final_test.sha256` + `v4_fresh_test.sha256` | SHA-256 of exact bytes against the recorded list | **48/48 identical** |
| The two locked sets (already **inside** the 48) | 2 | Against the repository's own locks, as `evaluation/common.py` `_load_locked` computes them (CRLF→LF normalised) | **both match** (`506c633e…`, `fac9428c…`) |
| Whole working tree | 215 before → 218 after | Per-file diff | Exactly 17 files changed or were added: the 16 in §3 plus this report; nothing else |

So the protected set is **48 distinct files**, not "48 plus 2": the locked sets are checked twice, by two methods.

**Limits of this evidence**
- The scoring and historical baselines are hash lists that this **same development agent** wrote earlier in the
  session, kept in its scratchpad. They show that nothing changed during this sprint. They are **not independent
  evidence**.
- The project is not under version control; no third-party baseline exists.
- The locked-set locks are stored in the repository, so they detect accidental change, not deliberate tampering
  with both file and lock.
- `final_test.json` has CRLF line endings on disk. Its plain `sha256sum` (`c061c150…`) is unchanged from the baseline
  but differs from its lock, because the lock is defined over LF-normalised bytes. `v4_fresh_test.json` has none, so
  both methods agree. A supervisor checking this file must use the project's rule, not plain `sha256sum`.

## 7. Database-access statement

- The main `answerwise` database **and the main MongoDB server on port 27017 were not connected to, inspected,
  seeded, migrated, reset or modified** in this sprint.
- Every test connection went to the throwaway server on port 27999.
- The guard logged no connection attempt to port 27017 during the test runs. The only blocked attempts were those of
  the deliberate guard probe, which were refused before a connection was made.
- Existing fixtures that hard-coded `localhost:27017` (and so pointed at the main server, under other database names)
  now follow `MONGODB_URI`.
- No deployment was made, pilot mode was not enabled for real use, and no participant account was created.

No version-control repository was created. **Recommendation:** put the project under Git before any further change,
with an initial commit made and its hash recorded by someone other than the developers. Later audits could then diff
tests and prove that no assertion was weakened, which this report can only assert.

## 8. Remaining risks

| Risk | Severity | Note |
|---|---|---|
| Override written directly to the database | LOW | Caught only by the next preflight; visible afterwards through each evaluation's `config_fingerprint` (A1, D5) |
| Self-reported server state (`transport`, `client_address_mode`, `model_cache`) | LOW | Detects mistakes, not an operator who deliberately fakes the environment. The preflight's own TLS check narrows this for transport |
| Non-atomic audit writes; logs not tamper-proof | LOW | Migration plan in A7 |
| Enrollment list visible to every teacher | LOW | D2/D6 (A6) |
| Model weights in server memory not attested | LOW | Unchanged (V7) |
| Withdrawal semantics, retention, scoping, token storage, fallback policy | — | D3, D4, D6, D8, D9 |
| No real TLS, proxy, multi-machine or load test | — | B4/D7 |
| Real-world grading accuracy | **unknown** | Needs the study protocol with real, consented data and independent marking (B1–B3) |

## 9. Actions required

**Developers**
1. Put the repository under version control, with an externally recorded initial commit (§7).
2. When D5 is decided, either keep the block or implement an approved, manifest-recorded override policy.
3. When IT chooses the database topology, move enrollment and publication audit writes into transactions if a
   replica set is used (A7).
4. When D2/D6 are decided, implement the chosen access rule for `/api/enrollments` (A6).
5. Check the question editor's display of `pilot_overrides_disabled` in a frontend test outside the working tree.

**Faculty**
- Decide D1, D2, D3 (with ethics), D5, D6, D8, D9 and D10.
- Confirm or reverse each developer default in `PILOT_READINESS.md` §4a.
- Approve the B1 criteria with evidence; name the second marker and adjudicator (B3) and the supervisor (B5).
- Accept or reject the residual risks in writing.

**Ethics reviewers**
- Decide B2 and D4; advise on D3, including whether withdrawn participants' e-mail addresses may remain visible (A6).

**IT**
- Document the network topology (D7): who terminates TLS, certificates and CA, the approved https CORS origins (in the
  exact browser form), any proxy address, and whether the pilot MongoDB is a replica set.
- Confirm in writing that the model-cache variables listed in `PILOT_RUNBOOK.md` §4.1 are unset or equal to the hub
  cache on the server.

**Supervisor**
- After deployment is authorised, compute and keep the SHA-256 of `backend/scripts/pilot_frozen_engine.json` outside
  the project. Its bytes did not change in sprint 5.
- Later, keep the study-lock and report hashes; run `verify`, and the preflight with `--url https://…
  --manifest-sha256 …` on the real deployment.
- No supervisor hash has been computed, stored or claimed by the development team, and **B5 is not closed**.
