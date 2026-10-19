# Classroom pilot: acceptance criteria (pre-registration)

**Status: criteria defined, thresholds NOT yet set.** Every numeric threshold and comparison rule below
must be chosen and approved by the **project team / faculty supervisor before the study set is frozen**.
None has a default. The values are recorded in the study's `acceptance_criteria.json`, and
`python -m evaluation.real_study` enforces the following:

* `freeze` refuses to run while any value is unset, while the approval is not documented (`approved_by`, `approved_on` and
  an `approval_evidence` reference), or while a required attestation is false. Documented approval is still **not**
  independently verified by software; `status` says so, and the supervisor confirms the evidence;
* `freeze` stores the file's SHA-256 in the locked set, and `score` refuses to run if the file changed afterwards
  (criteria cannot be adjusted after seeing results);
* `score` evaluates every criterion and reports `PASS` / `FAIL` / `NOT_EVALUABLE`, plus an overall outcome.

> An earlier draft of the protocol (audit, 2026-10-16) contained example numbers: 85% within ±1, 1.5× the
> teacher-vs-teacher error, and 10% severe errors. They were the developer's suggestions, not derived from data and not approved,
> so they have been **removed**. This document intentionally proposes no values.

## 1. Criteria and the decisions they need

| # | Criterion | Metric (as computed by `score`) | Value to be approved | Decided by |
|---|---|---|---|---|
| S1 | Minimum sample | `n_answers ≥ min_answers`, `n_questions ≥ min_questions`, smallest question `≥ min_answers_per_question` | `min_answers`, `min_questions`, `min_answers_per_question` | project team / faculty |
| T1 | Teacher agreement: concepts | linear-weighted Cohen's κ between teacher A and teacher B on M/P/X concept levels | `min_teacher_concept_kappa` | faculty |
| T2 | Teacher agreement: question totals | share of answers where the two teachers' totals differ by ≤ 1 mark | `min_teacher_within_1` | faculty |
| E1 | Grading error | **upper** 95% CI bound of normalised MAE (error / question max), engine 4.1 vs adjudicated reference | `max_normalised_mae_ci_upper` | faculty |
| E2 | Agreement within one mark | **lower** 95% CI bound of within-±1 | `min_within_1_ci_lower` | faculty |
| E3 | Error relative to teachers | engine MAE ÷ teacher-vs-teacher MAE | `max_mae_ratio_to_teacher_mae` | faculty |
| V1 | Severe scoring errors: overall | share of answers with \|engine − reference\| ≥ 2 marks | `max_severe_error_share` | faculty |
| V2 | Severe scoring errors: by question type | worst question type with n ≥ 20 | `max_severe_error_share_per_question_type` | faculty |
| C1 | Versus keyword baseline | paired MAE difference (engine − baseline) on the same locked answers | `keyword_baseline_rule`: `ci_upper_below_zero` / `point_estimate_not_worse` / `report_only` | project team |
| C2 | Versus v3 configuration | paired MAE difference (engine − v3) on the same locked answers | `v3_rule`: same options | project team |
| F1 | Review flags useful | MAE of flagged answers > MAE of unflagged answers | `require_flagged_mae_above_unflagged` (true/false) | project team |

All CIs are 95% percentile bootstraps over **questions** (10,000 resamples). With fewer than 5 questions, the
CI-based criteria (E1, E2, and C1/C2 under `ci_upper_below_zero`) are reported as `NOT_EVALUABLE`, because the
interval is not meaningful (with one question it has zero width).

## 2. Non-negotiable conditions (no threshold, always required)

**Privacy compliance.** The tool enforces each of these; any failure stops the study.

| Condition | Enforced by |
|---|---|
| Ethics approval or authorisation reference, purpose, data controller, deletion procedure, pseudonymisation and manual PII review recorded | `manifest.json` validation at every step (no placeholders allowed) |
| Informed consent for every answer | `consent_obtained_for_all_answers` must be `true` at every step |
| Retention date in the future; data deleted after it | every step refuses to run after `retention_until` |
| De-identification passed on the exact answers file, using the class name list | `check-pii --names` writes `pii_check.json`; `freeze` requires it to have passed and to match the SHA-256 of `answers.csv` |
| Study data outside the repository | every step refuses a study directory inside the repo, except the git-ignored `backend/evaluation/study_data/` |
| Reports contain no answer text | `score` writes ids and numbers only (tested) |

**Independent reference marks.**
* At least two markers are declared in the manifest, and both are declared blind to model scores and to each other.
* Each marker has exactly one marks file covering every concept once; no duplicates.
* Every disagreement is adjudicated with a reason before `freeze`.

**Mandatory teacher review in the pilot.**
* The pilot deployment runs with `REQUIRE_REVIEW_BEFORE_PUBLISH=true`, so the server refuses to publish a result until the
  teacher has accepted or adjusted every question. With `PILOT_MODE=true` the server refuses to start otherwise. Confirm with
  `python -m scripts.pilot_preflight --url <server>` (which reads `/api/health`) and attest it in `acceptance_criteria.json`
  (`pilot_deployment_requires_review_before_publish`).
* Students are told that marks are teacher-decided and AI-assisted (`students_informed_marks_are_teacher_decided`).
* Before each pilot session, `/api/health` must show `"engine_version": "4.1.0"` and `"similarity_backend": "embedding"`.
  The TF-IDF fallback is not the evaluated system, and `score` refuses to use it.

## 3. Decision rule

| Overall outcome | Meaning | Next step |
|---|---|---|
| **MET** | Sample adequate and every criterion PASS. `report_only` comparisons are shown but do not decide. | Continue the **teacher-reviewed** pilot. This is not a certification of grading accuracy. |
| **NOT MET** | Sample adequate and at least one FAIL | Stop AI-assisted marking for the course; report the failure. |
| **INCONCLUSIVE** | Sample too small, or any criterion NOT_EVALUABLE | No conclusion. Collect a new study (new questions, new frozen set) or stop. |

Unreviewed or high-stakes use is out of scope under every outcome.

## 4. Context for the approvers (not thresholds)

* The only existing evidence is synthetic, developer-written and single-marker. On the v4 fresh set (engine 4.0):
  MAE 0.547 (95% CI 0.41–0.72), normalised MAE 14.8%, 87.5% within ±1, 4 of 64 answers with error ≥ 2. Real answers are expected
  to be harder; these numbers should **not** be used as targets.
* Teacher-vs-teacher agreement on this course's questions is unknown. T1/T2 protect against judging the engine
  against an unreliable reference.
* The maximum marks per question (3–5 so far) change what "1 mark" means; E1 is normalised for this reason.

## 5. Approval record

To be completed in `acceptance_criteria.json` (study directory, not this repository):
`approved_by`, `approved_on`, `approval_evidence`, all values in §1, and both attestations in §2.
