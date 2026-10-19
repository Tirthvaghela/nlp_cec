# Real-student evaluation protocol for AnswerWise AI

**Status: prepared, not run.** No real student answers, teacher marks, consent records or results exist
in this repository. Every accuracy figure reported so far comes from **synthetic, developer-written
answers marked by one person**. This protocol describes how to measure grading reliability on real
answers, and the tool `backend/evaluation/real_study.py` enforces its order of steps.

---

## 1. Question the study answers

How closely do AnswerWise AI's suggested marks agree with **adjudicated marks from two independent
teachers** on real student answers? Is the current engine (4.1) better than the v3 configuration and a
keyword-overlap baseline? The study does **not** test whether the tool may replace teachers. It may not:
the application presents AI marks only as suggestions.

## 2. Before collecting anything

| Requirement | How |
|---|---|
| Authorisation | Approval, or a recorded exemption, from the institution's ethics committee. Where no committee exists, written authorisation from the head of department. Record the reference in `manifest.json`. |
| Authorised educational purpose | State the purpose in `manifest.json`. Collect only answers to the assessments named there. Never collect personal data for this study that the course does not already hold. |
| Informed consent | Use `study_templates/information_sheet_and_consent.template.md`, adapted and approved. Participation must not affect marks. Answers without consent are excluded *before* any step below. Signed forms are stored separately and never enter the study directory. |
| Withdrawal | Possible until the set is frozen (step 6). The cut-off date is stated on the information sheet. |
| Retention and deletion | Set `retention_until` and `deletion_procedure` in `manifest.json`. After that date the tool refuses to run, and raw answers and marks must be deleted. Only aggregate results may be kept. |
| Storage | Keep the study directory **outside this repository**, on storage the institution approves. `backend/evaluation/study_data/` is git-ignored only as a safety net. |
| Pseudonymisation key | If a key linking answer codes to students is needed (for example, to honour a withdrawal), it is held by one named role, stored separately, and destroyed at the freeze date or the retention date. |

## 3. Design

* **Questions.** Use at least 6 questions, mixing types (definition, explanation, comparison,
  process/application) and maximum marks. The rubric for each question is written and frozen **before** any
  answer is read for the study.
* **Sample size.** Aim for at least 150 answers in total and at least 20 per question. With fewer than
  about 8 questions, confidence intervals are wide, because answers to the same question are correlated
  (see §8). Report whatever n is reached; do not stop early when results "look good".
* **Independence from development.** Study questions and answers must never be used to design, tune or
  test-debug the engine. Engine development stops (the version is frozen) before scoring.
* **Comparison systems**, all scored once on the frozen set:
  * the current engine (4.1, default configuration);
  * the v4.0 and v3 configurations (historical profiles pinned in `evaluation/common.py`);
  * the keyword-overlap baseline, **fitted on the synthetic dev split only**.

## 4. Steps (enforced by `python -m evaluation.real_study <step> --study DIR`)

| Step | Command | What it does / refuses |
|---|---|---|
| 1. Set up | `init` | Copies the templates: manifest, acceptance criteria, questions, answer and mark CSVs, consent template. The CSVs contain headers only and every criterion value is empty. Refuses a study directory inside the repository (except the git-ignored `backend/evaluation/study_data/`). |
| 2. De-identify | `check-pii --names class_names.txt` | Flags e-mail addresses, phone numbers, URLs, long ID-like numbers, roll-number patterns, "my name is…", and any listed names. Redact by hand and re-run until clean. The result is recorded in `pii_check.json` together with the SHA-256 of `answers.csv`. It **passes only with a name list and zero findings**, and any later edit of `answers.csv` invalidates it. Regexes cannot find every name, so a person must also read the answers (recorded as `manual_pii_review` in the manifest). |
| 3. Independent marking | (teachers) | Each teacher declared in the manifest (`markers`, both flagged blind to model scores and to each other) fills `marks_<id>.csv` with one level per rubric concept: **M** fully addressed, **P** partly addressed, **X** missing. Teachers mark **independently**, without seeing each other's marks or any AI score. AnswerWise must not be run on these answers before step 7. |
| 4. Agreement | `agreement` | Computes teacher-vs-teacher agreement and writes `adjudication_worklist.csv` listing every concept on which the teachers disagree. Refuses to run without: a complete manifest (no placeholders); consent; an unexpired retention date; marks files that match the declared markers exactly; and marks covering every (answer, concept) exactly once. Duplicate or conflicting rows are rejected. Questions still containing template placeholders are also rejected. κ is reported as undefined when neither teacher used more than one level. |
| 5. Adjudication | (third teacher or consensus) | For every worklist row, record `final_level`, `adjudicator_id` and a `reason` in `adjudication.csv`. Agreed levels are used unchanged. The reference mark is the rubric total of the final levels. |
| 6. Freeze | `freeze` | Builds `study_set.json`, which holds the reference marks and each teacher's marks kept separately. It also records the **frozen engine** (version, model, config fingerprint, SHA-256 of the NLP source code), the SHA-256 of the approved `acceptance_criteria.json`, and the set's own SHA-256. Refuses if: the criteria are incomplete or unapproved; no passing PII check exists for the current answers; any disagreement is unadjudicated; an answer also appears in the development dataset; or a frozen set already exists. **Send the hash to the faculty supervisor** before step 7. |
| 7. Score | `score` | Verifies the set hash, that the criteria are unchanged, and that the installed engine and embedding model equal the frozen ones (the TF-IDF fallback is refused). It then scores the four systems on the same locked answers, evaluates the criteria, and writes `results/score_report.{json,md}` and `SCORED.json`. Reports contain ids and numbers, **never answer text**. Refuses a second run (even if the report file is deleted, `SCORED.json` remains). `--historical-rerun` writes a separately labelled `score_report_rerun.*` and is refused if the set was never scored. **Send the report hash to the faculty supervisor.** |

**What the tool cannot enforce.** Anyone with write access to the study directory can delete `SCORED.json`
and the results, or edit files, and start over. Blind marking and consent are *declared*, not verified.
These are controlled by the external record: the freeze and report hashes go to the supervisor at the time
they are produced, and a scoring run that the supervisor has not seen does not count. The supervisor keeps them
(`study_templates/integrity_record.template.md`) and checks them with
`python -m evaluation.real_study verify --study STUDY --set-hash H --report-hash H`. `verify` hashes the exact file
bytes (the same value as `sha256sum`), and reports VERIFIED only if the lock matches **and**, whenever a report exists, the
report hash is given and matches. A match proves file integrity only, not consent or blind marking. `python -m evaluation.real_study status --study STUDY` lists the steps still pending.

Teacher reference marks and model marks are kept apart. Reference marks come only from steps 3–5. Model
output exists only from step 7, after the reference is frozen, so it cannot influence the reference.

## 5. Metrics reported

| Metric | Definition |
|---|---|
| MAE | Mean \|model − reference\| in marks. |
| Normalised MAE | Mean of \|error\| / question max marks; comparable across questions with different maxima. |
| Within ±1 | Share of answers with \|error\| ≤ 1 mark. |
| Exact | Share with error 0. |
| Severe errors | Count with \|error\| ≥ 2 marks. |
| Mean signed error | Positive values mean over-crediting. |
| Paired differences | MAE(current) − MAE(other) on the same answers, with a CI. A difference whose CI includes 0 is **not** evidence of an improvement. |
| Review flags | MAE of answers the engine flagged for review versus answers it did not flag. |
| Subgroups | Per question type and per question, reported **only when n ≥ 20**. Otherwise listed as "not reported". |
| Teacher agreement | Concept exact agreement, linear-weighted kappa, and teacher-vs-teacher MAE and within ±1 on question totals. This is the practical **ceiling**: the model should not be expected to agree with the reference better than teachers agree with each other. |

Every report states n, the number of questions, the question types, the maximum marks, the engine version,
the model, the config fingerprint and the set hash.

## 6. Interpreting the result (criteria are fixed before freezing)

The pass/fail criteria are defined in [PILOT_ACCEPTANCE_CRITERIA.md](PILOT_ACCEPTANCE_CRITERIA.md). They cover
grading error, teacher agreement, severe errors, comparisons with v3 and the keyword baseline, review-flag
usefulness, privacy compliance and mandatory teacher review.

* The threshold values are set and approved by the project team / faculty in the study's `acceptance_criteria.json`.
* `freeze` refuses to run until they are complete, and `score` refuses to run if they changed after freezing.
* The score report states MET / NOT MET / INCONCLUSIVE for each criterion and overall.

(An earlier version of this section listed example numbers. They were unapproved suggestions and have been removed.)

A MET outcome supports only **continued teacher-reviewed use**. It does not support unsupervised or
high-stakes grading.

## 7. Limitations to report alongside the numbers

* One institution, a few courses, and one language register; results may not transfer.
* Two teachers do not define the "truth". Report their agreement and treat the reference as one reasonable marking.
* Students who consent may differ from those who do not.
* Rubric quality strongly affects the engine. Report how the rubrics were written.
* The engine's known limitations (README §17) still apply: short definitions, paraphrase, factual errors
  that keep the expected wording, pronouns and sarcasm.

## 8. Statistics

`evaluation/stats.py` computes 95% percentile bootstrap intervals (10,000 resamples) that resample
**questions** (cluster bootstrap), because answers to the same question share a rubric and are not
independent. With few questions the intervals are wide, and that width must be reported, not hidden.
Answer-level bootstrap intervals are available but are narrower than is justified.

## 9. What exists today

| Item | Status |
|---|---|
| Protocol (this document) | Ready |
| Templates (`backend/evaluation/study_templates/`) | Ready: placeholders and headers only, no data; criteria values empty |
| Pre-registered acceptance criteria | Defined in [PILOT_ACCEPTANCE_CRITERIA.md](PILOT_ACCEPTANCE_CRITERIA.md); **values awaiting project-team / faculty approval** |
| Pilot deployment setting `REQUIRE_REVIEW_BEFORE_PUBLISH` | Implemented, off by default; must be switched on for the pilot |
| Tool (`backend/evaluation/real_study.py`) and tests (`backend/tests/test_real_study.py`, synthetic fixtures) | Ready, tested |
| Ethics approval, consent, real answers, teacher marks, results | **None. Not collected, not fabricated.** |
