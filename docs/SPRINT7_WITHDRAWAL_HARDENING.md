# Sprint 7: withdrawal fail-safety (fix for S6-1)

**Date:** 2026-10-17. **Scope:** fixes (a), (b) and (c) proposed in
[SPRINT6_FINAL_SIGNOFF.md](SPRINT6_FINAL_SIGNOFF.md) §6, implemented at the project's request.

This is a technical fix. It is **not** a faculty, ethics, IT or supervisor decision:
- **B1–B5 stay OPEN**;
- **D1–D10 stay undecided**, including who may revoke (D2) and what withdrawal means for existing work (D3);
- **the decision stays NO-GO**;
- **real-world grading accuracy remains unknown**;
- **high-stakes and unreviewed grading remain NO-GO**.

## 1. Root cause

In PILOT_MODE, student access to assessments was decided **only** by the account flag `users.pilot_enrolled`.
`DELETE /api/enrollments/{email}` wrote, in this order:
1. `enrollments.revoked_at`;
2. the flag;
3. the event.

A failure after write 1 left the list showing the participant as inactive while the flag still granted access. A
repeated DELETE looked only for an *active* enrollment, so it answered 404 and repaired nothing.

## 2. Changes

| File | Change |
|---|---|
| `backend/app/services/access.py` | **(c)** New `pilot_access_ok(db, student)`. In PILOT_MODE it requires `pilot_enrolled is True` **and** an enrollment with the account's e-mail and `revoked_at: None`, whose `user_id` is unset or this account. Outside PILOT_MODE it always returns `True`, so development is unchanged. `student_can_see` now takes the result as a required keyword (`pilot_ok=`), so no caller can skip it; `visible_assessment` passes it. |
| `backend/app/routers/assessments.py` | `list_assessments` computes `pilot_access_ok` once per request and passes it to `student_can_see`. |
| `backend/app/routers/enrollments.py` | **(a)** and **(b)**: `revoke` rewritten (described below). The module comment is updated to match. |
| `backend/tests/test_withdrawal_sprint7.py` (new) | 18 tests (§3) |
| `docs/PILOT_READINESS.md`, `docs/PILOT_RUNBOOK.md` | S6-1 row, participants control, status line; withdrawal and retry procedure (runbook §7) |

**Every assessment entry point is covered** (all go through `student_can_see`):

| Entry point | Route |
|---|---|
| list | `GET /api/assessments` |
| detail | `GET /api/assessments/{id}` → `visible_assessment` |
| save draft | `PUT /api/submissions/draft` → `_check_open` → `visible_assessment` |
| submit | `POST /api/submissions/submit` → `_check_open` → `visible_assessment` |

**Deliberately unchanged.** A student's own submissions, published results and progress (`/api/submissions/mine`,
`GET /api/submissions/{id}`, `/api/results/*`, `/api/analytics/student`) stay visible after withdrawal, as before.
Changing that would decide D3.

The teacher directory (`/api/users/students` in PILOT_MODE) still lists accounts by the flag alone. It grants no
access, but after a partial failure it may still list an account whose access is gone.

### How `revoke` now works

1. **404** "No enrollment for this e-mail" only if the e-mail was **never** enrolled. Nothing is written.
2. **Access off first (a):** `users.pilot_enrolled = false`.
3. Mark the enrollment revoked, with `revoked_at = ts` and `revoked_by`, if it is still active.
4. If step 3 changed it, write the `revoked` event with `at = ts` (the same time as `revoked_at`) and return
   "Enrollment revoked…".
5. **If it was already revoked (b):** when no `revoked` event exists with `at >= revoked_at`, write the missing one.
   It keeps `by` = the original revoker and `at` = `revoked_at`, and adds `completed_by` and `completed_at`. Return
   "An interrupted revocation was completed…". Otherwise write nothing and return "This enrollment was already
   revoked…".
6. **If the enrollment became active again in between** (someone re-enrolled at the same moment), return **409**
   `enrollment_changed` and do not touch the new state.

Any failed write returns 500. Success is never reported for an incomplete revocation. Authorisation is unchanged:
any teacher may revoke, students get 403 and anonymous callers 401.

### Failure analysis, with (c) in force

| Write that fails | List shows | Student access | Repeating the DELETE |
|---|---|---|---|
| Step 2 (flag) | active | allowed: consistent with the list; nothing changed | performs the full revocation |
| Step 3 (enrollment) | **active** | **denied** (flag off), fail closed | marks revoked, writes one event |
| Step 4 (event) | inactive | denied | writes the missing event once, then "already revoked" |
| Enroll, flag write | active | denied (flag off), fail closed | repeating the enroll grants access |
| Register, enrollment link | active, "registered: false" | allowed: email matches an active enrollment and the flag is on | — |

No partial failure of enroll, register or revoke can now grant access that the enrollment list does not show.

## 3. Fresh test results (this sprint)

**Database.** A **new, throw-away MongoDB 8.2 server** on `127.0.0.1:27999`:
- its data directory was created empty in the session scratchpad;
- before the tests it held only `admin`, `config` and `local`, and the same after them (test databases are dropped);
- it was shut down at the end, and a ping confirmed port 27999 was down.

**Guard.** The scratchpad guard plugin `s5guard`:
- refuses and logs any connection to port 27017;
- blocks the scoring entry point and the model loader;
- blocks opening the locked sets, their locks, `dataset.json` and `evaluation/results/*`.

It logged **no blocked event** in any run. The new module also stubs `run_engine`, `evaluate_answer` and
`get_backend` to fail if used.

Environment for all runs: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<scratchpad>/guard MONGODB_URI=mongodb://127.0.0.1:27999`,
from `backend/`.

| Run | Command | Exit code | Result |
|---|---|---|---|
| 1. Focused | `python -B -m pytest -p s5guard -p no:cacheprovider tests/test_withdrawal_sprint7.py -v` | 0 | **18 passed**, 0 failed. (A first attempt had 1 failure caused by an invalid name in the test's own request body, 422 instead of 403. The test input was fixed; no assertion was changed.) |
| 2. Detection check | the same 18 tests run against a scratchpad copy of `app/` with the **sprint 6** `revoke` and the flag-only access check restored (no `.env`, no evaluation data) | 1 | **11 failed, 7 passed**. Every S6-1 case fails on the old code: failure after access is disabled, retry completion, unknown participant, flag without a valid enrollment ×3, and others. The 7 that pass check behaviour that did not change. The copy was deleted afterwards. |
| 3. Regression | `python -B -m pytest -p s5guard -p no:cacheprovider` on the 9 files in the table below, `-k "not (<the 5 scorer-calling tests>)"` | 0 | **303 passed**, 0 failed, 0 errors, 0 skipped; 7 items deselected |

Per-file results for the regression run:

| File | Passed |
|---|---|
| `test_withdrawal_sprint7.py` | 18 |
| `test_security_sprint5.py` | 114 |
| `test_security_sprint3.py` | 45 |
| `test_security_hardening2.py` | 40 |
| `test_security_remediation.py` | 38 |
| `test_pilot_readiness.py` | 25 |
| `test_auth.py` | 8 |
| `test_assessments.py` | 8 |
| `test_submissions.py` | 7 |

The existing revoke tests pass unchanged: success, an event-write failure, unknown e-mail → 404, and the
remediation test in which revocation removes access immediately.

**Failure scenarios covered by the 18 tests.** All of them check the student's **actual** access on list, detail,
draft and submit, not only status codes.
- successful revocation;
- step 2 failure, then retry;
- **failure after access is disabled** (step 3), then retry;
- event-write failure, then retry by another teacher (recorded once, original revoker kept);
- repeated revocation after success (×3, no duplicate, no state change);
- a flag turned back on after revocation;
- unknown participant (404, nothing written);
- an enrollment that was never registered;
- a concurrent re-enrollment (409, new state untouched);
- flag off with an active enrollment;
- flag on with a **missing**, **revoked** or **other-account** enrollment;
- both valid; an unlinked enrollment (user_id unset) still allowed;
- re-enrollment restores access;
- a partial enroll failure fails closed;
- a student or an anonymous caller cannot revoke;
- development mode ignores enrollment.

**Not run:**
- The 7 deselected items (5 tests). They call the scoring engine. One of them,
  `test_withdrawal_policy_is_undecided_current_behaviour_documented`, covers teacher review and publication for a
  withdrawn participant, which this sprint did not change; it was **not** re-verified.
- Scorer, evaluation, preprocessing, metrics, study and browser E2E suites: forbidden.
- Frontend tests: no frontend file changed. The frontend shows server messages as before (sprint 6), but the new
  revoke messages were not exercised in a browser.
- Anything against a real deployment or a real pilot database.

Earlier sprints' results are not counted as fresh evidence.

## 4. Protected files

| Group | Compared with | Result |
|---|---|---|
| 10 scoring sources `app/nlp/*.py` | Sprint 1 hash list | **10/10 identical** |
| Scoring wiring `app/services/evaluation_service.py` | End-of-sprint-3 record | **identical** |
| Engine manifest `scripts/pilot_frozen_engine.json` | End-of-sprint-3 record (value not written down) | **identical** |
| Manifest coverage | The manifest's own per-file hashes | **11/11 match** |
| 48 historical evaluation files (they include both locked sets and their locks) | Recorded list | **48/48 identical** |
| Locked sets `final_test.json`, `v4_fresh_test.json` | Repository locks, using `evaluation/common.py` `_load_locked`'s CRLF→LF rule | **both match** (read as bytes for hashing only) |
| Whole tree, before the documentation updates | Per-file diff | Only the 4 code and test files in §2 changed or were added |

**Unexplained bytecode write: please check.**
- **What was written:** between 17:02:07 and 17:02:10, 20 `__pycache__/*.pyc` files were written for `app/main.py` and
  the modules it imports (`app/*`, `app/routers/*`, `app/schemas/*`, `app/services/*`). Their headers show they were
  compiled from the **current** repository sources.
- **What it suggests:** the order, starting with `app/main.py`, points to a process outside my commands that
  **imported the application entry point**: for example a server start (`uvicorn app.main:app`), an IDE run or debug
  configuration, or an editor tool.
- **Why it was not my test runs:** it happened after the last test run ended (17:01:53) and after the throw-away server
  stopped (17:02:02). My commands in that window did not import the application. Every test run used `-B` with
  `PYTHONDONTWRITEBYTECODE=1`. No pytest bytecode or `.pytest_cache` entry was written. No Python process was running
  when checked afterwards.
- **What was not done or checked:** I did not start the application. Whether that other process connected to a
  database is **not known**: checking would require inspecting the main database, which is forbidden here.
- **What was not affected:** these are regenerable caches, excluded by `.gitignore` and by the integrity checks. No
  source file other than those listed in §2 changed, and no `app/nlp` bytecode was rewritten. The files were left in
  place.
- **Action for the developer:** confirm what was started at about 17:02.

**Limits of this evidence:**
- The scoring and historical hash lists were written by the development agent itself in earlier sprints. They show
  "unchanged during these sprints"; they are **not independent baselines**.
- The lock files are stored in the repository.
- There is no version control.
- Independent verification requires the supervisor's own hashes (B5). None were computed or claimed.

## 5. Remaining risks and unverified points

| Risk | Note |
|---|---|
| List lags behind access | After a step-3 failure, the list shows "active" although access is gone, until the revoke is repeated. This is the fail-closed direction; the runbook says to repeat until success and check the list |
| Two simultaneous revokes | Each could write a "revoked" event (a duplicate history line). Neither can grant access. Not tested |
| No transaction | Still three writes per change; transactions need a replica set (D7) |
| Audit log | Not tamper-proof against direct database access; legacy events are not back-filled |
| Teacher directory | Still uses the flag alone (no access impact) |
| Existing work after withdrawal | Still visible to the student; reviewable, re-evaluable and publishable by teachers. Unchanged, because it is a D3 decision |
| Real deployment | Not tested on the real pilot database or MongoDB topology, or under real network failures; the failures were simulated in the driver layer |
| Directly edited `revoked_at` older than an existing event | The completion check (`at >= revoked_at`) could then miss a missing event. Only reachable by direct database edits |

## 6. Status

**Still NO-GO.** B1–B5 are OPEN, D1–D10 are undecided, and the residual risks are not accepted in writing. Nothing in
this sprint is evidence of approval by faculty, ethics, IT or the supervisor. **Real-world grading accuracy remains
unknown.** **High-stakes and unreviewed grading remain NO-GO.**
