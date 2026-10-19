# Sprint 8: investigation of the unexplained application import (17 Oct 2026, 17:02)

**Type:** investigation only. No source, configuration, cache file or database was changed, and nothing was started,
imported or compiled (§6). **The decision remains NO-GO.**

## 1. Summary

| Question | Answer | Strength |
|---|---|---|
| What imported `app/main.py` at 17:02:07–17:02:10? | A **uvicorn development server** started with `uvicorn app.main:app --reload --port 8000` in a VS Code PowerShell terminal (working directory `backend\`, `.venv` activated) | **Established** (the terminal's saved output plus matching timestamps) |
| Can the process be identified? | Uvicorn reloader process **31380**, server process **4932** (from the terminal output) | Established |
| Who typed the command? | Not identifiable from the evidence. It was **not** this Claude Code session (§3.1). | Unknown |
| Was a server started? | **Yes**: "Started server process [4932] … Application startup complete", the embedding model loaded at 17:02:36–17:02:39, and HTTP requests were served | **Confirmed** |
| Did it connect to a database? | **Yes, to the main MongoDB server on port 27017**: PyMongo connections accepted at 17:02:10.712 and 17:03:19.97 | **Confirmed** by the main server's own log |
| Did it read or write the main database? | **Writes confirmed:** at 17:02:10.746 it created the collection `answerwise.enrollments` and its indexes `_id_` and `uniq_enrollment_email`. **A user insert is very likely:** the server logged "Registered student account 6ad35cff…" and `POST /api/auth/register` → 201 at 17:03:19. Reads are very likely (login, `/api/assessments`, `/api/results/mine` …), but MongoDB does not log reads at its default verbosity | Collection and index: confirmed. Insert: strongly supported (§4). Individual reads: not logged |
| Did my own test runs touch the main server? | **No.** The main server accepted **no connection at all between 10:08:27 and 17:02:10** on 17 Oct, a window that covers sprints 4–7. All 5 connections in the 17:00 hour belong to this dev server | Confirmed by the main server log |

**Correction to the sprint 7 report:** it said whether the importing process connected to a database was "not
known". It is now known: it connected to the main server and wrote to the `answerwise` database.

## 2. Timeline

All times are IST (UTC+05:30), as recorded by the file system, VS Code and MongoDB; the Claude transcript records UTC.

| Time | Event | Source |
|---|---|---|
| 17:01:53 | Last sprint 7 test run ends; it used the throw-away server on port 27999 | Sprint 7 output file |
| 17:02:01.4–17:02:06.1 | Claude command: shut down the throw-away server (27999). The next Claude command starts at 17:02:15.6 | Claude transcript; `Claude VSCode.log` |
| 17:02:07.30 | `app/__pycache__/main.cpython-312.pyc` written: the first of 20 | File timestamps |
| 17:02:07.70–17:02:08.05 | `deployment`, `db`, `config`, `errors`, `model_cache` `.pyc` written | File timestamps |
| (≈2.2 s gap) | Libraries load (`app/nlp` sources were unchanged, so no `.pyc` was rewritten there) | Inference |
| 17:02:10.24–17:02:10.56 | `ratelimit`, `deps`, `security`, the services, the routers and the schemas `.pyc` written | File timestamps |
| 17:02:10.712 | **Main mongod (27017): "Connection accepted" from 127.0.0.1, client PyMongo 4.17.0, CPython 3.12.4** (three connections) | Main server log |
| 17:02:10.746–.776 | **`createCollection answerwise.enrollments`; index builds `_id_` and `uniq_enrollment_email`** (`ensure_indexes` at application start-up, `app/db.py`) | Main server log |
| 17:02:36–17:02:39 | Embedding model loaded (`PRELOAD_MODEL=true`) | Terminal output |
| (no time recorded) | `POST /api/auth/login` → 401 | Terminal output |
| 17:03:19.92 | "Registered student account 6ad35cffacd1975c76878e49"; `POST /api/auth/register` → 201 | Terminal output |
| 17:03:19.97 | Main server: two more PyMongo connections | Main server log |
| (no time recorded) | `GET /api/analytics/student`, `/api/results/mine`, `/api/assessments`, `/api/submissions/mine` → 200 | Terminal output |
| 17:03:53–17:03:55 | VS Code shuts down (extension host exits with code 0); **every dev-server connection to the main server ends** | VS Code `main.log`; main server log |
| 17:03:57 | New VS Code session starts; terminals are restored at 17:04:01 without the server | VS Code logs; Windows PowerShell event log |
| 17:05:20 | Sprint 7's "no Python process running" check, which therefore came **after** the server had ended | Claude transcript |

The ObjectId `6ad35cff…` carries its creation time: 0x6ad35cff = 1792236799 seconds since 1970. The main server's
own checkpoint timestamps (`ts_sec` 1792236813 at 17:03:33.93) put that at **17:03:19 IST**, matching the
registration log line.

## 3. Evidence inspected

### 3.1 Claude Code session (this investigation's own actions)
- **Transcript** (`~/.claude/projects/.../b391590c-….jsonl`, read with `jq`): **no tool call ran between
  17:02:06.075 and 17:02:15.252**. The only event in that gap is the notice that the throw-away `mongod` had exited.
- **Hooks:** none are configured (`~/.claude/settings.json`: `hooks: null`), and the extension log confirms "Found 0
  total hooks". No other Claude transcript on this machine was active at that time.
- **Limitation:** this shows that no *Claude* process ran a command in the window. It does not identify the person
  who typed the uvicorn command.

### 3.2 File-system metadata
- The modification times, sizes and order of the 20 `.pyc` files.
- In sprint 7, their headers were shown to record the exact size and modification time of the current sources.
- **Limitation:** this investigation's own hashing **updated the files' access times** to 17:07:51. Their contents
  and modification times are unchanged (§6).

### 3.3 VS Code
- **Logs:** previous session `logs/20261016T213626`, new session `logs/20261017T170357`.
  - The Python, Pylance, Black and debugpy extensions logged nothing in the window.
  - The Python Environments extension only resolved the interpreter.
  - There are no debug or task launches.
- **Saved terminal state:** `workspaceStorage/35694c99…/state.vscdb.backup` (saved 17:03:53). Its terminal buffer
  holds the uvicorn command and output in §2. It was read as bytes with a small Node decoder kept in the scratchpad; no
  database tool was used and nothing was written.
- **Limitation:** the buffer prints uvicorn's access lines **without timestamps**; only the application's own log
  lines carry times.

### 3.4 Shell and operating system
- **PSReadLine history:** it contains repeated `uvicorn app.main:app --reload --port 8000` entries, but **no per-line
  timestamps**, so its entries cannot be dated.
- **Windows event logs** (`Windows PowerShell`, `PowerShell/Operational`, `Security`, `System`, `Application`,
  17:01:30–17:04:30):
  - no PowerShell console started until 17:04:01, so the server ran in a terminal that was **already open**;
  - script-block logging and process-creation auditing are **not enabled**, so the typed command itself is not in the
    event logs.

### 3.5 MongoDB
- **Main server log** `C:\Program Files\MongoDB\Server\8.2\log\mongod.log`: read as a file only. The connections,
  client metadata, collection creation, index builds and disconnections are in §2.
- **Counts on 17 Oct:**
  - connections accepted per hour: 00 → 29, 08 → 6, 09 → 1009, 10 → 578, 17 → 5;
  - the last before the event was at 10:08:27;
  - none after 17:03:19.
- **Configuration:** `backend/.env` (only these lines read, credentials would be redacted) sets
  `MONGODB_URI=mongodb://localhost:27017`, `MONGODB_DB=answerwise`, `ENVIRONMENT=development` and
  `PRELOAD_MODEL=true`.
- **Limitation:** at its default verbosity MongoDB does not log individual reads, inserts or updates, so the student
  insert is shown by the application's log and the HTTP 201, not by the database log.

## 4. What is confirmed, what is inferred, what is unknown

| Category | Status |
|---|---|
| Python compilation / module import | **Confirmed**: 20 `.pyc` files, in the import order of `app.main` |
| Application or server start-up | **Confirmed**: uvicorn start messages, "Application startup complete", model load, requests served |
| Database connection attempts | **Confirmed**: main server log |
| Successful database connections | **Confirmed**: connections accepted and their first commands received |
| Database writes | **Confirmed:** the new collection `answerwise.enrollments` and two indexes (main server log). **Strongly supported:** one new student user document in `answerwise.users`, from the application log line, the 201 response, the ObjectId time and the 17:03:19 connections. Which collection received it is inferred from `.env` and the code (`routers/auth.py`) |
| Database reads | **Inferred** from the served requests (login, assessments, results, analytics, submissions); not individually logged |
| Scoring or evaluation calls | **None seen** in the saved terminal output, which shows no `/api/evaluations` or `test-answer` request; the buffer may not contain everything |
| Identity of the person who started the server | **Unknown** |
| Why VS Code shut down at 17:03:53 | **Unknown** (logged as a normal exit, no reason given) |
| Whether the registered account is a test or a real person | **Unknown** (the e-mail is not in any log read here, and the database was not queried) |

**Most likely explanation (inference).** Someone working in an already-open VS Code terminal started the usual local
dev server, then signed up as a student through the frontend at about 17:03:19. The server used the configured `.env`,
which points at the **main development database `answerwise`**. Because the code had changed since the last time that
database was used, start-up created the `enrollments` collection and its unique index there. The `.pyc` files were
written because those sources were newer than their cached bytecode. Closing VS Code ended the server at 17:03:55.

## 5. Consequences for the earlier reports

- **The `answerwise` database on the main server is no longer as it was before 17:02.**
  - It now has an `enrollments` collection with two indexes, and very likely one more student account.
  - This was done by the dev server, not by any audit or test step.
  - Nothing was removed or reverted here; that decision belongs to the developer.
- **"Main database not accessed" in the sprint 4–7 reports** describes those sprints' **own** actions. The main server
  log now supports it independently: **no connection between 10:08:27 and 17:02:10**.
- **Sprint 3:** the 09:00–10:08 connections are its documented test runs. They used separate databases on the main
  server, as that report states. Which databases they touched was not re-examined here.
- **Sprint 7 test results:** not affected. Those runs ended at 17:01:53 and used port 27999 only.

## 6. What this investigation did and did not do

- **No:** application start, module import, Python execution, test run, compilation, database connection or query,
  or change to `.pyc` files, sources, configuration or environment.
- **Tools used (read-only):** `stat`, `find`, `sha256sum`, `grep`, `jq`, `dd`, PowerShell `Get-WinEvent`, and a
  Node script (in the scratchpad) that decodes the saved terminal text.
- **Before and after:** all 303 project files, **including the 20 `.pyc` files**, were byte-identical. The only side
  effect is the updated access times noted in §3.2.
- **Not available, or not checked:**
  - the typed command's exact time and author;
  - database reads;
  - the content of the inserted user;
  - the reason VS Code shut down;
  - output beyond what VS Code saved;
  - Windows process-creation records, which are not enabled.

## 7. Recommended preventive measures (non-invasive; for the developer to decide)

1. **Use a separate database for local development** from the one treated as the protected "main" database. For
   example, give the dev server its own `MONGODB_DB` in a local, uncommitted override, or rename the protected
   database. This changes no application code.
2. **Before audit or test sessions**, stop any running `uvicorn --reload` server, and tell the auditing agent if one
   must keep running. `--reload` also re-imports the app whenever `.py` files change, which can produce similar
   bytecode writes and, if it fails, misleading start-up attempts.
3. **Decide what to do with the changes the dev server made to `answerwise`**: the `enrollments` collection, the
   `uniq_enrollment_email` index and the student account `6ad35cffacd1975c76878e49`. This is a human decision; the
   database was not inspected or changed here.
4. **Optional, for better evidence next time:**
   - Windows process-creation auditing, or PowerShell transcription, on the development machine;
   - version control (Git) to date source changes;
   - `uvicorn --log-config` with timestamps on access lines.
5. **Keep the pilot fail-safes as they are.** A real pilot server cannot start this way: `PILOT_MODE` refuses plain
   uvicorn and refuses the database `answerwise`. This incident happened in development mode.

## 8. Status

- **NO-GO** is unchanged.
- B1–B5 remain **OPEN** and D1–D10 **undecided**.
- Real-world grading accuracy remains unknown; high-stakes and unreviewed grading remain NO-GO.
