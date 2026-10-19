# Classroom pilot runbook

**Use only after every blocker in [PILOT_READINESS.md](PILOT_READINESS.md) is VERIFIED.** Until then the pilot is
**NO-GO**. This runbook does not authorise a deployment.

## 0. Local development is never the main database (sprint 9)

On 2026-10-17 a local `uvicorn app.main:app --reload` server wrote to the main `answerwise` database
([SPRINT8_IMPORT_INVESTIGATION.md](SPRINT8_IMPORT_INVESTIGATION.md), [SPRINT9_INCIDENT_CONTAINMENT.md](SPRINT9_INCIDENT_CONTAINMENT.md)).
Since then:
* **every application process refuses to start** when `MONGODB_DB` resolves to `answerwise` (any mode, any
  capitalisation). Local development uses `MONGODB_DB=answerwise_dev` in `backend/.env` (the template and the default);
* application start-up **always writes** missing collections and indexes to the selected database, so selecting a
  database is never read-only;
* before an audit or test session, **stop any running dev server** (`uvicorn … --reload` also re-imports the app when
  `.py` files change) or tell the person running the session that it is running;
* the backend tests create throw-away databases (`answerwise_test_<pid>` and similar) on the server named by
  `MONGODB_URI`. While INC-1 is open and that server has no access control, run them against a **separate, disposable**
  `mongod` instead (for example `MONGODB_URI=mongodb://127.0.0.1:27999` with its own data directory), as sprints 5–7 did;
* the guard is part of the application only: `mongosh`, Compass and other tools can still reach every database while
  the main MongoDB server runs without access control (see the incident report).

## 1. Roles: AI suggestion vs teacher decision

| | AnswerWise AI | Teacher |
|---|---|---|
| What it produces | A **suggested** mark per question, the evidence sentences, review flags and draft feedback | The **final** mark and feedback |
| Can publish a result | **No** | Yes, and only after reviewing every question (enforced by `REQUIRE_REVIEW_BEFORE_PUBLISH=true`) |
| Can be wrong without warning | Yes. Known weaknesses: short definitions, paraphrases, factual errors that keep the expected wording (README §17) | Teachers decide; the AI score is kept beside the teacher's score for comparison |

The interface already labels every AI value as "AI-suggested". The app banner states that AI marks are
suggestions and that the teacher makes the final decision. A student sees "Teacher adjusted (AI suggested X)" when the
teacher changed a mark. Results are invisible to students until the teacher publishes them.

## 2. Teacher instructions (each assessment)

1. Write the rubric **before** reading answers. Do not change it after evaluation without re-evaluating; the app blocks
   publication of results made with an outdated rubric.
2. Do not use the per-question threshold settings (Question editor → *Advanced*) during the pilot. They change how the AI
   scores that question, outside the frozen engine identity. In PILOT_MODE the server **refuses to save** one (error
   `pilot_overrides_disabled`, sprint 5), and the preflight **fails** while any question in the pilot database has any
   settings value (sprints 3 and 5). Allowing overrides would need faculty authorisation (decision D5) and a recorded
   override policy. The server block is a developer default, not that decision.
3. Run the evaluation. Treat every AI mark as a **draft**.
4. For **every** question of every submission:
   * read the student's answer, not only the highlighted evidence;
   * check the concepts the AI marked missing as well as those it credited;
   * read the review flags, especially "Careful review needed" and "fallback";
   * either **Accept AI score** or set your own mark. When you change it, give a reason (required) and add feedback if useful.
     A review is only recorded when it states one of these decisions; an empty review is refused (sprint 3, V10). Your
     mark is stored as entered, even if it equals the AI suggestion.
5. Publish only when every question shows *Reviewed*. The server refuses otherwise.
6. A student who queries a mark goes to the teacher, never to the AI. Unpublish, re-mark with a reason, and publish again; every
   review is kept in the review log, and every publish/unpublish records who did it and when (sprint 3, V10).
7. Lost or shared device: change your password or use **sign out everywhere** (`POST /api/auth/logout-all`). Either ends
   every earlier session, including a stolen token; the device you used continues with a fresh session (sprint 3, F5/V9).

## 3. What students are told (adapt and approve with the consent material)

> Your answers are marked by your teacher. An AI tool suggests marks and points to the parts of your answer that
> match the marking scheme, but your teacher reads your answer and decides every mark. If you disagree with a mark,
> contact your teacher.

## 4. Deployment checklist (requires authorisation, see blocker B4)

### 4.1 Supported topology (the only one this runbook covers)

```
student / teacher browser ──HTTPS──▶ pilot API server (python -m scripts.run_server, ONE process, TLS)
          │                                      │
          └──HTTPS──▶ static frontend files      └──▶ MongoDB (pilot database only)
               (npm run build output, VITE_API_URL = the API's https URL; CORS_ORIGINS = this site's origin)
```

* **Direct, no reverse proxy.** Browsers connect to the API server itself, so the TCP peer address IS the client
  address. `TRUSTED_PROXIES` stays empty and the launcher turns uvicorn's proxy-header processing **off**:
  `X-Forwarded-For` sent by anyone is ignored. This is enforced by the launcher, not merely assumed.
* **Never plain `uvicorn app.main:app`.** Plain uvicorn trusts `X-Forwarded-For` from 127.0.0.1 by default, so any
  local process (including the Vite dev server, which forwards client headers) could choose its own address and bypass
  the per-IP limits. In PILOT_MODE the server refuses to start without the launcher.
* **Never the Vite dev server (`npm run dev`)** for the pilot: serve the production build.
* **TLS is enforced in PILOT_MODE** (sprint 3, V12). The launcher **refuses to start** when it would serve beyond
  loopback without TLS. Exactly one of these must hold:
  - **(a) this server terminates TLS**: `--ssl-certfile` and `--ssl-keyfile`, both readable files issued by IT
    (transport `tls-direct`);
  - **(b) an IT-approved reverse proxy terminates TLS**: `TLS_TERMINATED_BY_PROXY=true` and the proxy's address in
    `TRUSTED_PROXIES` (transport `tls-proxy`). This is an explicit operator statement that the launcher cannot verify,
    so IT must confirm it in writing.

  The server reports its transport in `/api/health`, and the preflight requires `tls-direct` or `tls-proxy`. That report
  is the server's own statement, so **the preflight must also be given an `https://` URL** (sprint 5): it then checks
  the certificate and host name itself and fails on a plain `http://` URL, an unverifiable certificate or a redirect.
  If IT issues the certificate from an internal CA, pass IT's CA certificate with `--cafile`; never disable
  verification. Outside PILOT_MODE, plain HTTP beyond loopback is still only a warning (local development).
* **CORS origins** must be the IT-approved frontend origin(s), each `https://host[:port]` with no path or wildcard,
  written exactly as browsers send it: lowercase, **no trailing slash**, no `:443`, a port from 1 to 65535 (sprint 5).
  PILOT_MODE and production refuse anything else and print the expected spelling; the values themselves come from IT
  and are never assumed.
* **`ENVIRONMENT`** must be `production` for the pilot. Since sprint 5 only `development` and `production` are accepted
  (any capitalisation); any other value stops the server.
* **Model cache: one location only** (sprint 5). The model is loaded from the Hugging Face hub cache (`HF_HUB_CACHE`,
  else `HF_HOME/hub`, else the user's `~/.cache/huggingface/hub`). Leave `SENTENCE_TRANSFORMERS_HOME`,
  `TRANSFORMERS_CACHE`, `PYTORCH_TRANSFORMERS_CACHE` and `PYTORCH_PRETRAINED_BERT_CACHE` unset (or equal to that
  directory), and keep no directory named `sentence-transformers/all-MiniLM-L6-v2` in the server's working directory.
  Otherwise the launcher and the preflight refuse. Run the preflight **on the server machine, in the same environment
  as the server**: it compares the cache the server reports with its own.
* **JWT secret** must be random. PILOT_MODE and production refuse missing, placeholder, short, repetitive or
  low-entropy values (generate it with `python -c "import secrets; print(secrets.token_urlsafe(48))"`).
* **Reverse proxy:** not part of the supported pilot topology. If IT requires one, list its exact address(es) in
  `TRUSTED_PROXIES` (never `*`, never loopback in PILOT_MODE, both refused). Faculty/IT must review it first, because
  the proxy then decides which client address the rate limits see.
* **One process only.** Rate-limit counters live in process memory: no `--workers`, no second instance, no load balancer.

### 4.2 Steps

Run on the pilot machine, from `backend/`. Only the commands marked **writes** change anything.

```bash
# 1. configuration: copy .env.pilot.example to .env and fill every <...> value (never commit it).
#    PILOT_MODE refuses: weak/short invite code, model preloading off, review gate off, non-production, dev database,
#    loopback/wildcard TRUSTED_PROXIES.
# 2. new, empty pilot database (writes: the pilot marker only)
python -m scripts.pilot_init_db                        # prints the database fingerprint - record it
#    NEVER run scripts.seed: it refuses any pilot-marked database and any database that is not identifiably demo data.
# 3. offline check - the supervisor's manifest hash is REQUIRED (without it the preflight fails)
python -m scripts.pilot_preflight --manifest-sha256 <hash the supervisor keeps>     # must print PREFLIGHT PASSED
# 4. start ONE server process through the launcher (refuses plain uvicorn, and plain HTTP beyond loopback, in PILOT_MODE).
#    In PILOT_MODE it also sets HF_HUB_OFFLINE so the model is loaded only from the cache the preflight hashed.
python -m scripts.run_server --host <server address> --port 8000 --ssl-certfile <IT cert.pem> --ssl-keyfile <IT key.pem>
# 5. bind the preflight to the running server: same database fingerprint (same MongoDB server, database and marker),
#    same configuration, launcher-started (client-address mode "direct"), same model cache, model loaded.
#    The URL MUST be https:// and use the host name on the IT certificate; add --cafile <IT CA certificate> for an
#    internal CA.
python -m scripts.pilot_preflight --url https://<server address>:8000 --manifest-sha256 <hash>   # PREFLIGHT PASSED
# 6. enroll the participants whose consent is recorded (writes; teacher login required). Enrollment is an access
#    control, not evidence of consent. Example with the API (or any HTTP client):
#    POST /api/enrollments  {"emails": ["..."]}   |   GET /api/enrollments   |   DELETE /api/enrollments/<email>
```

The server and the preflight must use the **same `MONGODB_URI` host spelling** (for example both `localhost`): the
database fingerprint includes the MongoDB server address, so a copy of the database on another server - or a different
spelling of the same host - does not match, and the check fails closed.

`pilot_preflight` fails closed. All of the following mean **do not start**:
* an unreachable database or server;
* a server whose database fingerprint differs from the preflight's;
* a missing or malformed pilot marker;
* a server not started by the launcher;
* a model that is still loading, or the TF-IDF fallback;
* demo accounts in the pilot database;
* a weak invite code or a disabled review gate;
* a missing, malformed, incomplete or changed engine manifest;
* model weights, tokenizer or config files on disk that differ from the frozen snapshot (exact bytes), or a model
  that is not cached;
* Python or scoring-library versions that differ from the frozen runtime;
* any per-question settings value in the pilot database (any engine setting or unknown key, not only thresholds);
* a server that does not report TLS (`tls-direct` or `tls-proxy`);
* a `--url` that is not an absolute `https://` URL, a certificate the preflight cannot verify, or a redirect;
* `EMBEDDING_MODEL` different from the frozen model, a cache variable or local directory that could redirect the
  model, or a server that reports a different model cache or revision;
* a missing, malformed or wrong supervisor manifest hash.

**When to run the preflight with `--url`:** after every server restart (and the first start, including any unplanned
restart) and before every teaching or study session. A PASS is a snapshot: it does not guarantee that fallback scoring cannot happen
later, for example after a restart in which the model fails to load.

**Supervisor's manifest hash (mandatory).** After deployment is authorised, the supervisor:
1. computes the SHA-256 of the exact bytes of `backend/scripts/pilot_frozen_engine.json` (`sha256sum`, or
   `Get-FileHash -Algorithm SHA256` on Windows);
2. keeps it **outside the project directory and outside the study team's control** (for example in their own e-mail
   or on paper);
3. gives it to the operator for every `--manifest-sha256`.

Nobody hardcodes or stores this value in the repository. Re-saving the manifest, even with only different line
endings, changes its bytes, and the preflight then fails until the supervisor re-confirms.

## 5. Fallback scoring (TF-IDF): exact procedure

The engine's behaviour is unchanged: if the embedding model cannot be loaded, the server still produces suggestions
with the TF-IDF fallback. These evaluations are stored with `backend: "tfidf"` and carry the review flag
`fallback_backend`. In the pilot they are **not** the evaluated system.

1. **Detect.** The preflight fails (`backend=tfidf`). Stop starting new evaluations. Then, from `backend/` with the pilot
   `.env`, run `python -m scripts.pilot_fallback_report`. It is read-only and prints ids and counts only, listing every
   evaluation with `backend: "tfidf"` and whether it already has a teacher mark with a reason. Exit code 1 means some
   still need one.
2. **Stop publication.** In PILOT_MODE the server refuses to publish a submission while any of its fallback-scored
   questions lacks a teacher-entered mark **with a reason** (error `fallback_requires_teacher_mark`). Accepting the AI
   score is not enough.
3. **Teacher marks.** For each listed evaluation the teacher reads the answer, enters **their own mark** in the review
   panel, and gives a reason such as "Fallback scoring - marked by teacher". This is what "mark by hand" means in the
   pilot: the teacher's mark, entered in the app, with a reason. No AI suggestion is relied on.
4. **Restore.** Restart the server and run the preflight with `--url` until it PASSES before any new evaluation.
5. **Record** the episode (date, number of affected evaluations from the report) in the pilot log. For the study, the
   offline scorer refuses the fallback anyway (`real_study score`).

## 6. Study (separate from the live app)

The evaluation study follows [REAL_STUDENT_EVALUATION_PROTOCOL.md](REAL_STUDENT_EVALUATION_PROTOCOL.md). It runs offline in
a study directory outside the repository (`python -m evaluation.real_study ...`).
* `status` lists, for each approval, three separate levels: fields completed, approval documented, approval
  independently verified. Software never sets the third.
* The supervisor keeps the lock hash and the report hash (template: `study_templates/integrity_record.template.md`)
  and checks them with `verify --set-hash ... --report-hash ...`. `verify` hashes the exact file bytes, as `sha256sum`
  does. It says VERIFIED only when every existing file matches the supervisor's values; without the report hash, an
  existing report is NOT VERIFIED.

## 7. Stop conditions

Stop AI-assisted marking (teachers enter their own marks with a reason, as in §5 step 3) if any of these happens:
* preflight fails, or cannot be run after a restart;
* a result was published without review (should be impossible; report it as a defect);
* a consent withdrawal cannot be honoured (revoke the enrollment immediately, then follow the protocol). Since sprint 7
  (fix for S6-1), a revoke removes the student's access **first**, and assessment access needs both that access and an
  active enrollment, so an interrupted revoke never leaves access in place. If the revoke request fails with a server
  error, **repeat the same request** until it succeeds. A repeat finishes whatever is missing without duplicating the
  history, and answers one of:
  - "Enrollment revoked…";
  - "An interrupted revocation was completed…";
  - "This enrollment was already revoked…".

  Then confirm that `GET /api/enrollments` shows the e-mail as inactive. 404 "No enrollment for this e-mail" means the
  address was never enrolled (check the spelling). 409 `enrollment_changed` means someone re-enrolled it at the same
  moment: check the list, then revoke again. Do **not** re-enroll a withdrawn participant to "reset" them: re-enrolling
  restores their access;
* identifying data appears in study files;
* the study outcome is **NOT MET**.
