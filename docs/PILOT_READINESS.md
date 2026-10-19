# AnswerWise AI 4.1.0: classroom pilot readiness

**Status date:** 2026-10-17, after sprint 9 (database incident containment). **A database incident is open**: a local
dev server wrote to the main `answerwise` database; the database review is pending (§3, INC-1). Evidence, newest first:
- [SPRINT10_FINAL_TECHNICAL_REVIEW.md](SPRINT10_FINAL_TECHNICAL_REVIEW.md) (guard review; finding S10-1: development
  and test databases still share the main MongoDB server);
- [SPRINT9_INCIDENT_CONTAINMENT.md](SPRINT9_INCIDENT_CONTAINMENT.md);
- [SPRINT8_IMPORT_INVESTIGATION.md](SPRINT8_IMPORT_INVESTIGATION.md) (original incident record);
- [SPRINT7_WITHDRAWAL_HARDENING.md](SPRINT7_WITHDRAWAL_HARDENING.md);
- [SPRINT6_FINAL_SIGNOFF.md](SPRINT6_FINAL_SIGNOFF.md) (handoff checklist);
- [SPRINT5_SECURITY_REPORT.md](SPRINT5_SECURITY_REPORT.md);
- [SPRINT3_SECURITY_REPORT.md](SPRINT3_SECURITY_REPORT.md).

**Decision: NO-GO.** The application is technically improved but **not authorised for a pilot**:
- all five external blockers (§5) are open;
- the policy decisions in §4 are unmade;
- the residual risks in §3 have not been accepted in writing.

Completed fields, passing tests and existing documents are not approvals.

**Real-world grading accuracy is unknown.** All existing results are synthetic, developer-written and single-marker.
**High-stakes and unreviewed grading remain NO-GO** under every outcome. Nothing here claims the application is
fully secure.

## 1. Decision

| Question | Answer |
|---|---|
| Can the pilot start now? | **NO-GO**: B1–B5 open; §4 decisions unmade; §3 risks not accepted |
| After B1–B5 are VERIFIED, §4 is decided and §3 is accepted in writing | **CONDITIONAL GO** for a low-stakes, teacher-reviewed pilot run as the study in `REAL_STUDENT_EVALUATION_PROTOCOL.md`, following `PILOT_RUNBOOK.md` |
| Unreviewed, summative or high-stakes grading | **NO-GO** |

## 2. Technical controls in place (verified by tests that do not run the scoring engine)

| Area | Control | Since |
|---|---|---|
| Review before publication | `REQUIRE_REVIEW_BEFORE_PUBLISH`; **explicit review decision** (an empty review is refused); fallback-scored results need a teacher mark with a reason | pilot work, sprint 1, sprint 3 |
| Pilot fail-safe | `PILOT_MODE` refuses to start on an unsafe configuration: review gate, production, **random JWT secret**, strong invite code, dedicated and **validly marked** database, preload, embedding backend, **https CORS allowlist**, safe trusted proxies | pilot work, sprints 1–3 |
| Configuration names | `ENVIRONMENT` is case-normalised and must be `development` or `production`; anything else refuses to start (so `Production` can no longer run as development). CORS origins are parsed structurally and must already be in the exact form browsers send (no trailing slash, lowercase, no default port, valid host, port 1–65535) | sprint 5 (A5, A9) |
| Authentication | Atomic per-IP, per-account, invite and password-change throttling with bounded memory; **sessions revoked on password change and on "sign out everywhere"** | sprints 1–3 |
| Client address | Launcher `scripts/run_server.py` ignores `X-Forwarded-For` unless explicitly trusted proxies are configured; refuses loopback/wildcard proxies in the pilot | sprint 2 |
| Transport | **PILOT_MODE launcher refuses plain HTTP beyond loopback**: TLS by the server itself (IT certificate) or by a declared, IT-approved proxy. Health reports the transport and the preflight requires TLS. **Since sprint 5 the preflight's `--url` must be `https://` in PILOT_MODE, and the preflight verifies the certificate and host name itself** (optional `--cafile` for an internal CA; verification cannot be switched off; a redirect fails). This tests the URL the preflight was given, not every route a browser could take. | sprints 3, 5 (A2) |
| Participants | Enrollment allowlist gates registration and every student assessment path; since sprint 7 that path needs both the account flag and an active enrollment, and an interrupted withdrawal fails closed and can be completed by repeating it (S6-1). **Pilot teacher directory lists only enrolled participants.** Enroll, revoke and (since sprint 5) registration each add an event to `enrollment_events`. The application only inserts events, but the log is **not tamper-proof** (direct database access can change it), and a state change and its event are **two separate writes, not a transaction** (§3). | sprints 1, 3, 5 (A7) |
| Database identity and seeding | Validated pilot marker; fingerprint bound to the MongoDB server, database and instance; seed refuses anything not identifiably demo data | sprints 1–2 |
| Protected main database | Every application process (dev server, launcher, seed, pilot scripts) refuses to start when the resolved `MONGODB_DB` is `answerwise`; the preflight will not open it; the default is `answerwise_dev`. Application-level only: it does not stop other tools | sprint 9 |
| Frozen identity | Mandatory supervisor manifest hash, compared with exact bytes. The manifest covers 11 scoring source files, **11 cached model files (revision plus exact bytes)** and **the Python and 10 scoring-library versions**. The preflight **fails on any non-empty per-question settings key**: every engine configuration field and any unknown key, not only the two thresholds (sprint 5, A3). **In PILOT_MODE the API refuses to save a threshold override** (sprint 5, A1: a developer default pending D5, not a faculty decision); an override written directly to the database is still caught only by the next preflight. The launcher keeps the model cache offline and, like the preflight, **refuses any variable or local directory that could make the libraries load model files other than the hashed cache** (`SENTENCE_TRANSFORMERS_HOME`, `TRANSFORMERS_CACHE`, …; sprint 5, A4). The server reports which cache it resolves, and the preflight compares that with its own. | sprints 1–3, 5 |
| Auditability | Review log with an explicit decision per entry; **publication log (who and when) for publish, unpublish and re-evaluation** (the re-evaluation record is tested since sprint 5, A8, with the engine stubbed). Each record is a separate write after the state change: if it fails, the request fails and the change stands without a record (§3). Older records are not back-filled. | sprints 1, 3, 5 |
| Study integrity | Exact-byte lock and report hashes; `verify` needs the supervisor's hashes; `status` never reports approval as verified | sprint 1 |

**Fallback scoring.** A preflight PASS is a snapshot: it **does not guarantee** that fallback scoring cannot occur after the
check, for example after a restart that fails to load the model. Re-run it after every server restart and before every
session. Publication of fallback-scored results is blocked until each has a teacher-entered mark with a reason.

## 3. Residual risks (need written acceptance or a later change)

| # | Severity | Residual risk | Why not closed now |
|---|---|---|---|
| F5 (storage) | LOW | Tokens are still stored in browser `localStorage`, so script injected into the page could read them. Revocation now limits a stolen token's lifetime to "until the next password change or sign-out-everywhere". | Moving to httpOnly cookies is an architecture change (CSRF protection, same-site deployment, credentialed CORS); the plan is in the sprint 3 report §7 |
| V6 | LOW | Enrollment is global (any teacher can manage it and view participant e-mails); withdrawn participants' existing work can still be reviewed and published (characterised by a test) | Research policy: §4 D1–D4 |
| V7 | LOW | The preflight hashes the model **on disk**, not the weights loaded in the running server's memory. The server reports its version string, not its source hash. Transitive dependencies, the OS and the CPU are not pinned. The study tool's comparison profiles and keyword baseline are not in the manifest. | Not provable without loading the model in the server, or remote attestation |
| V11 | INFO | In the pilot, all teachers see all **enrolled** participants (no per-teacher scoping) | No teacher-to-class model exists: §4 D6 |
| V12 | LOW | `TLS_TERMINATED_BY_PROXY=true` is an operator statement the software cannot verify; certificate validity is not checked by the launcher (uvicorn fails on unusable files). The preflight now verifies the certificate of the URL it is given (sprint 5). The server's `transport`, `client_address_mode` and `model_cache` reports remain self-reported: they detect mistakes, not a deliberate bypass by someone who controls the server's environment | Needs IT's written topology: §4 D7 |
| A1 (rest) | LOW | A per-question override written **directly to the database** (not through the API) changes AI suggestions until the next preflight detects it. Each evaluation records its `config_fingerprint`, so it is visible afterwards | Refusing to evaluate would change evaluation behaviour (policy, D5) |
| A6 | LOW | `GET /api/enrollments` shows **every** enrolled and revoked participant e-mail to **every** teacher (also in the pilot) | Who may see participants is decision D2/D6 (§4a) |
| A7 / audit writes | LOW | State changes and their audit entries (`enrollment_events`, `publication_log`) are separate writes without a transaction; a failure between them leaves the change without an entry (the request then fails visibly). Audit logs are not tamper-proof against direct database access | MongoDB transactions need a replica set; the pilot database topology is IT's decision (D7). Migration path: replica set, then both writes in one transaction |
| S6-1 withdrawal window | LOW (was LOW–MEDIUM) | *Fixed in code in sprint 7* ([SPRINT7_WITHDRAWAL_HARDENING.md](SPRINT7_WITHDRAWAL_HARDENING.md)). In PILOT_MODE, assessment access needs **both** `users.pilot_enrolled` and an active enrollment for the account (`services/access.py` `pilot_access_ok`). `revoke` clears the flag first, and repeating it completes an interrupted revocation without duplicating events; 404 now means "never enrolled". Tested with each single write failing, against a throw-away database. **Remaining:** a partial failure can leave the list showing "active" while access is already gone, until the revoke is repeated (fail-closed direction only). Two revokes at exactly the same moment could each write a "revoked" event. No transaction; events not tamper-proof. Not tested on the real pilot database or deployment | The access rule and revoke behaviour were changed at the project's request in sprint 7. This is a technical fix, **not** a faculty decision on D1–D3 (who may revoke, what withdrawal means for existing work); those stay open. Transactions remain an option if IT provides a replica set (D7) |
| INC-1 database incident (2026-10-17) | **OPEN** | A local dev server (`uvicorn app.main:app --reload`) connected to the main MongoDB server and created `answerwise.enrollments` with two indexes (confirmed by the server log). It reported registering one student account (persistence and identity **unverified**). The main server appears to run without access control (inferred from the log). See [SPRINT8_IMPORT_INVESTIGATION.md](SPRINT8_IMPORT_INVESTIGATION.md) and [SPRINT9_INCIDENT_CONTAINMENT.md](SPRINT9_INCIDENT_CONTAINMENT.md) | Recurrence guard added in sprint 9. **Pending:** the database administrator's review and the data owner's decision (sprint 9 report §4), and MongoDB access control (IT). Developers cannot close this alone |
| Rate limits | LOW | In-memory counters: reset on restart, one process only; a known e-mail can be locked out for 15 min | By design for the single-process pilot |
| Deployment assumptions | — | Untested here: multi-machine deployment, a real TLS certificate chain, a real reverse proxy, load beyond 20 parallel requests | Only a disposable single-machine test environment was available |

## 4. Decision register (technical facts vs proposals: none of these is decided)

| # | For | Question | Technical fact today | Proposal (not implemented, unless marked) |
|---|---|---|---|---|
| D1 | Faculty | Global or study-specific enrollment? | One global allowlist | Per-study allowlist owned by the study lead |
| D2 | Faculty | Who may enroll, revoke and view participants? | Any teacher (all actions logged in `enrollment_events`). *Sprint 5 correction: enroll, revoke and registration are logged; viewing the list is not, and an event is not written atomically with its change (§3).* | Study lead only; other teachers see their assigned students |
| D3 | Faculty + ethics | What happens to existing submissions after withdrawal? | Access to assessments ends immediately; existing submissions and evaluations remain and can be reviewed and published | Block publication and study export for withdrawn participants, and exclude them from analysis |
| D4 | Ethics | Retention and deletion obligations | Nothing is deleted automatically | Retention date and deletion procedure as in the study manifest; a deletion tool after approval |
| D5 | Faculty | Per-question threshold overrides in the pilot? | The preflight fails while any override exists. *Since sprint 5 the API also refuses to save one in PILOT_MODE (developer default, §4a); direct database writes are caught only by the preflight.* | Keep forbidden (default), or record approved overrides in the manifest |
| D6 | Faculty | Teacher-to-student scoping | None (enrolled participants visible to all teachers in the pilot) | Introduce class/assignment ownership |
| D7 | IT | TLS topology, certificates, approved CORS origins, proxy addresses | The launcher enforces TLS; the values must be supplied | IT documents the topology in writing |
| D8 | Faculty | Refuse fallback evaluations outright in the pilot? | Fallback is allowed; publication needs a teacher mark | Optional refusal (changes evaluation behaviour) |
| D9 | Faculty | Token storage migration | `localStorage` with server-side revocation | httpOnly cookie sessions (report §7) |
| D10 | Faculty | Acceptance of the §3 residual risks | Not accepted | Written acceptance or change requests |

## 4a. Developer defaults and privacy boundaries (not faculty decisions)

The following behaviour was **chosen by developers** as the most restrictive, or the least-change, option while the
matching decision is open. None of it is approved policy; faculty may confirm or reverse each item.

| Default | Implemented | Decision it anticipates |
|---|---|---|
| Per-question overrides make the preflight fail; the API refuses to save them in PILOT_MODE | sprints 3, 5 | D5 |
| Pilot teacher directory lists only enrolled participants | sprint 3 | D6 |
| Withdrawal ends access to assessments only; existing work stays reviewable, re-evaluable and publishable (unchanged, characterised by a test) | sprint 1 | D3 |
| Any teacher can enroll, revoke and list participants | sprint 1 | D1, D2 |
| Fallback-scored results need a teacher mark with a reason before publication (fallback itself is allowed) | sprint 1 | D8 |

**Privacy (finding A6, confirmed in `backend/app/routers/enrollments.py`, `list_enrollments`).** Any signed-in teacher
can list every e-mail address ever enrolled, including **revoked** (withdrawn) participants, with their status.
Consequence: a withdrawn participant's address stays visible to all teachers, including teachers with no role in the
study. Least-privilege options for faculty (D2/D6), none implemented: restrict the list to a named study lead; hide
revoked entries from everyone but the study lead; give other teachers counts only; scope by class once D6 exists.

## 5. Blockers

| # | Blocker | Status | Evidence required to close |
|---|---|---|---|
| B1 | Acceptance criteria | **OPEN** | All 13 values set, with `approved_by`, `approved_on` and `approval_evidence`; the supervisor confirms the evidence independently |
| B2 | Ethics and consent | **OPEN** | Ethics approval or documented exemption; approved information sheet and consent form |
| B3 | Independent marking | **OPEN** | Named second marker and adjudicator; blind-marking and adjudication procedure accepted |
| B4 | Safe deployment | **OPEN (technically prepared)** | Written deployment authorisation; IT-approved TLS topology and origins (D7); dedicated pilot database initialised; `pilot_preflight --url https://… --manifest-sha256 …` → PASSED on the real deployment, with the certificate verified by the preflight; written acceptance of §3 and decisions D1–D10 |
| B5 | Supervisor evidence | **OPEN** | Named supervisor holds the manifest, study-lock and report hashes outside the repository and the study team's control, and runs `verify`. Hashes prove file integrity only, not consent, blind marking or adjudication. |
