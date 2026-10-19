# AnswerWise AI: final quality audit (engine 4.0.0 → 4.1.0)

**Audit date:** 2026-10-16
**Scope:** NLP scoring engine, evaluation methodology and history, teacher-in-the-loop workflow, privacy.
**Audit rule:** neither held-out set was used for any decision. No result file was overwritten, and no
database was reset.

## 1. Summary

* **Integrity of history: intact.** All 36 pre-audit evaluation artifacts are byte-identical after the audit
  (SHA-256 checked): both locked sets, `dataset.json`, and every v1–v4 result. The v3 final set and the v4
  fresh set still match their recorded hashes. The fresh set was **not** re-run.
* **Engine:** 3 fixes adopted as **4.1.0** (2 former expected failures, 1 feedback-wording defect), 1 candidate
  rejected, and 2 limitations newly documented. Thresholds and weights are unchanged. 4.1 has **dev-only
  evidence** (LOQO MAE 0.594 → 0.582, driven by one answer) and **no held-out result**.
* **Evaluation tooling:** 3 latent reproducibility defects fixed. None of them had corrupted a recorded result yet.
* **Workflow:** 1 auditability gap fixed (teacher overrides were overwritten in place). No authorization or
  privacy regression was found.
* **Headline numbers are unchanged and remain synthetic.** Fresh-set MAE: v4.0 0.547, v3 configuration 0.562,
  keyword baseline 0.961. Within ±1: 87.5% for both v4.0 and v3, and 75.0% for the baseline. **The v4.0-vs-v3 difference
  is one mark of total error over 64 answers**, well inside the 95% CI of 0.41–0.72.
* **Recommendation: conditional GO** for a controlled, low-stakes classroom pilot in which every mark is teacher-reviewed
  (§9). **NO-GO** for unsupervised or high-stakes use.

## 2. Historical results: protection checks

| Check | Result |
|---|---|
| `final_test.json` vs `final_test.sha256` (`506c633e…`) | match |
| `v4_fresh_test.json` vs `v4_fresh_test.sha256` (`fac9428c…`) | match |
| 36 artifacts hashed before the audit, re-checked after it | all identical |
| Missing or inconsistent historical artifacts | none found. One historical *recipe* problem was found: see §4, R1 |
| Fresh set re-run | **no**. Its uncertainty was computed from the archived report only (`uncertainty_v4_fresh.py`) |

## 3. Scoring engine audit

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | Rubric is the primary authority | ✔ | Marks come only from per-concept levels × rubric marks (`scorer.py`). Holistic similarity only raises flags. |
| 2 | Keywords alone do not guarantee marks | ✔ | `c = s + 0.15·k·(1−s)`: k can raise a score by at most 0.15·(1−s). Keyword lists are downgraded. Tests: `test_wrong_statement_with_keywords_*`, `test_keyword_list_*`. |
| 3 | Dense sentences vs keyword lists | ✔ | v4 predicate cues; 24 tests in `test_keyword_list_v4.py`. |
| 4 | Echo guard does not reject genuine explanations that reuse the question's terms | ✔ with a limitation | New tests cover explanations that reuse question terms and expanded abbreviations. **Limitation introduced by 4.1:** a minimal definition built only from expanded words scores 0 (strict xfail). It is now flagged for review, which was not true at first (see F2b). |
| 5 | Antonym and negation checks do not penalise valid statements | ✘ partly, documented | **Found:** since 4.0, a correct contrast paraphrase ("frequent … whereas *rare* distinctive words …") is downgraded and flagged. An exemption (F4) was measured and **rejected**, because it would let real contradictions pass *unflagged*. The false positive is always flagged for review (test). |
| 6 | Swapped-definition and reversed-comparison safeguards active | ✔ | `correctness_checks=True`; v3 tests pass. Swaps inside one concept are now caught too (4.1). |
| 7 | No duplicate credit | ✔ | Similar-concept blocking, duplicate-sentence removal; `test_similar_concepts_*`, `test_repetition_*`. |
| 8 | Scores within limits | ✔ | Per-item `min(awarded, marks)`, total clamped to [0, max]; `test_marks_always_within_bounds`; API rejects teacher scores above max, below 0, or off the 0.25 step. |
| 9 | Overrides need a reason and are auditable | ✔ (fixed) | A reason was already required (422). **Gap found and fixed:** a second review overwrote the first score and reason. There is now an append-only `review_log`, archived on re-evaluation (API test plus E2E check). |
| 10 | Uncertain answers flagged | ✔ with caveat | Flagged MAE 0.61 vs 0.33 unflagged (fresh set, 4.0). The flags cover most answers (49/64), so review load is high. |
| 11 | Model-loading failure handled | ✔ | Any load error falls back to TF-IDF, with `fallback_reason` stored and a `fallback_backend` *review* flag; `test_model_load_failure_falls_back_to_tfidf`. |

**Feedback-wording defect (fixed, F5).** When a stronger sentence was rejected (echo, misattributed or reversed)
but another sentence earned the concept, the student read "…so it was not credited" and "earned no marks for X"
while X was marked *matched*. This was found on dev answer Q2-v1. The note and flag text are now true in both cases.
Matched concepts are described as "addressed", not "correctly explained", because the engine cannot verify facts.
This changes no score.

## 4. The documented expected failures

| 4.0 expected failure | Path | Cause | Grading risk | Outcome |
|---|---|---|---|---|
| Short definitions under-credited (`test_scorer.py::test_short_definition_gets_credit`) | `scorer.py`: debiased cosine | Projecting out the question's direction also removes most of a definition that restates the question. "Tokenization is dividing a sentence into words" scores 0/4; with debiasing off it scores **4/4**, because one sentence then matches all 3 concepts. | Under-credit of correct short answers | **Not fixed.** No defensible signal was found in v3/v4 (token recall and adaptive debias were both rejected on dev). Mitigation verified: these answers raise `divergent_signals` and get low confidence, so they go to review (new test). |
| Attributes swapped inside one concept (`test_scorer_v4.py::test_swapped_attributes_inside_one_concept`) | `antonym_flip` skips concepts containing both antonyms | Nothing checked *which side* each antonym is attached to | A wrong statement earns **full credit with no flag** (silent) | **Fixed (F1):** `swapped_attributes()`, an anchor-word mutual-exchange rule. It fires on no dev answer, so no dev false positives and no dev benefit; it was adopted because it closes a silent failure. Four correct phrasings are tested as non-firing. |
| Expanded name credited as explanation (`…::test_naming_the_expanded_term_is_not_an_explanation`) | `echo_only` compares against the unexpanded question | The expansion words counted as "new content" | +3 marks of over-credit (flagged for review) | **Fixed (F2):** the question's abbreviations are expanded before comparison. Dev: 2 concept changes, both agreeing with the human label. **Side effect:** minimal definitions from expanded words now score 0, which is a new strict xfail. **F2b:** without the flag change, that loss was *high-confidence and unflagged*; `restates_question` is now a review flag whenever the guard withholds credit. |

**Expected failures after the audit (strict xfails):**
1. short definitions (since v2);
2. minimal definition built from expanded words (introduced by F2, mitigated);
3. contrast paraphrase misread by the antonym check (since 4.0, newly documented, mitigated by review).

No safeguard was weakened, and no regression fixture was used as a performance claim.

## 5. Evaluation methodology

| Topic | Finding |
|---|---|
| Leakage between splits | None. There are no shared or near-duplicate answers (similarity > 0.8) across dev / seen-test / v3 final / v4 fresh, and no shared topics (key-term Jaccard < 0.3). This is now a test. |
| Question overlap | Template only: Q15/Q18 (v3 final) and R3/R6 (fresh) reuse dev Q3's "Differentiate between X and Y". The comparison safeguards were therefore tested on a familiar format. |
| Threshold calibration | LOQO re-fits thresholds per fold, which is correct. **Selection bias:** choosing the best candidate by LOQO MAE makes the selected candidate's figure optimistic (v3 0.574, v4 0.594, 4.1 0.582). The other weights were fixed earlier on dev. |
| MAE and within ±1 | Correct (`metrics.py`, `experiments.summary`): within ±1 is inclusive with float tolerance, and normalised MAE is computed per question maximum. |
| Different maximum marks | MAE in marks is not comparable across sets (3–5 vs 3–4). Normalised MAE is reported alongside it. |
| Baseline comparability | Comparable. The keyword baseline is a linear fit on the same data the engine thresholds were fitted on (dev), and LOQO per fold in the experiments. |
| Safeguard precision | A **proxy**: it counts firings on human-*missing* concepts. A correct downgrade to *partial* counts as a miss, and note-only firings count as firings. The README's "14 of 16" is accurate as labelled but should not be read as precision. |
| Flagged-answer error | Computed correctly (flagged vs not-flagged MAE). |
| Uncertainty | Not reported before. Added: fresh-set MAE 95% CI 0.41–0.72 (question-cluster bootstrap); within ±1 CI 81–94%. A paired v4-v3 CI needs v3 per-answer predictions, which were not archived, so the difference is reported as total error (35 vs 36 marks). |
| Config and model provenance | Every report records the engine version, model, full config and fingerprint. |

**Reproducibility defects (fixed; no recorded number was wrong):**
* **R1.** Experiment scripts recorded only their *overrides*. After later default changes, re-running
  `experiments.py` (v3) or `experiments_v4.py` (E0–E4) silently ran different configurations. The v2, v3 and v4.0 profiles
  are now pinned in `common.py`, and the archived dev numbers reproduce **exactly**: 0.7635 and 0.5743 (v3 dev, 74 answers),
  0.7118 and 0.5941 (v4 dev), and 0.5706 (the v4.0 in-sample report).
* **R2.** `evaluate.py` named outputs by *major* version, so any 4.x run would have overwritten the archived 4.0
  reports. Outputs are now tagged `_v4.1`, and every archived file is write-protected: reproductions go to `*_rerun.*`.
* **R3.** `--v4-fresh` had no "spent" guard. It now requires `--historical-rerun`, like `--final`, and such
  reports are labelled "HISTORICAL RERUN".

No corrected report was needed: no historical calculation was found to be wrong.

## 6. Teacher-in-the-loop and privacy

| Requirement | Verdict |
|---|---|
| AI marks presented as suggestions | ✔ "AI-suggested" labels throughout, "You have the final say", "Accept AI score". The app shell states that AI marks are suggestions. |
| Evidence and feedback inspectable | ✔ Concept evidence is highlighted in the original text; reasons, flags and feedback are shown. |
| Mark changes need a reason | ✔ (server-side 422 and client-side) and are now logged append-only. |
| Unpublished results hidden | ✔ Results return 404 until published; totals are hidden in submission lists (tested). |
| No access to others' data, reference answers, rubric keywords or thresholds | ✔ (tested). After publication, concept labels and descriptions *are* shown by design; this is now documented in README §17. |
| Rubric change blocks stale publication | ✔ (`rubric_outdated`, tested). An engine-version change does not invalidate stored evaluations; they keep their 4.0.0 label. |
| Database | Not reset. E2E ran on a separate database; the main database's content fingerprint was identical before and after. |

## 7. Changes made

| Id | Change | Files |
|---|---|---|
| F1 | Attribute-swap check (on) | `nlp/correctness.py`, `nlp/scorer.py`, `nlp/config.py` |
| F2 / F2b | Expanded-topic echo (on), plus a review flag when the echo guard withholds credit | same |
| F4 | Antonym contrast exemption: measured, **rejected** (off; kept for measurement) | same |
| F5 | Truthful notes and flags for rejected-but-replaced evidence; "addressed" wording | `nlp/scorer.py`, `nlp/feedback.py` |
| W1 | Append-only `review_log` for teacher overrides | `routers/evaluations.py` |
| R1–R3 | Pinned profiles, write-protected history, spent-set guard, `--profile` | `evaluation/common.py`, `evaluate.py`, `experiments.py`, `compare_*.py` |
| E1 | 4.1 dev experiment with per-concept firings | `evaluation/experiments_v41.py` |
| S1 | Cluster-bootstrap CIs; post-hoc fresh-set uncertainty | `evaluation/stats.py`, `uncertainty_v4_fresh.py` |
| P1 | Real-student protocol, templates and tool | `docs/REAL_STUDENT_EVALUATION_PROTOCOL.md`, `evaluation/real_study.py`, `evaluation/study_templates/`, `.gitignore` |
| T | Tests: `test_scorer_v41.py`, `test_evaluation_integrity.py`, `test_real_study.py`, review-log API test; two 4.0 xfails converted to ordinary tests | `backend/tests/` |

## 8. Remaining issues

1. Real-world grading reliability is unknown; all evidence is synthetic and single-marker.
2. No unused held-out set exists, so 4.1 is unvalidated beyond dev and fixtures.
3. Short definitions are under-credited (sent to review).
4. Paraphrases and dense correct answers are the largest error categories (fresh MAE 1.12 / 1.00).
5. A formula-heavy dense answer scored 0/4 on the fresh set. It was deliberately left undiagnosed and needs new dev data.
6. Antonym false positive on contrast paraphrases (flagged); echo false positive on minimal expanded-word definitions (flagged).
7. Factual errors that keep the expected wording are not detected.
8. Review flags fire on most answers (55/85 on dev), so review load is high.
9. The review log has no UI. Students see rubric concept descriptions after publication.
10. JWT stored in `localStorage`; no rate limiting (unchanged).

## 9. Go / no-go

**Conditional GO for a controlled classroom pilot**, under all of these conditions:
* low-stakes or formative assessment only;
* **every** AI suggestion is reviewed by the teacher before publication, not only the flagged ones;
* students are told that marks are teacher-decided and AI-assisted, and how to query a mark;
* the pilot runs as the real-student study in `docs/REAL_STUDENT_EVALUATION_PROTOCOL.md` (consent, de-identification,
  two markers, frozen set, scoring once), with the decision thresholds written down before scoring;
* the engine is frozen at 4.1.0 for the pilot.

*Update 2026-10-17:* the review requirement is now enforceable (`REQUIRE_REVIEW_BEFORE_PUBLISH=true`). The criteria are
defined in `PILOT_ACCEPTANCE_CRITERIA.md`; their values await approval. See `PILOT_READINESS.md`.

**NO-GO** for summative, high-stakes or unreviewed grading. Nothing measured so far supports it.

## 10. Verification (actual outcomes on 2026-10-16)

| Check | Outcome |
|---|---|
| `cd backend && pytest` | **149 passed, 3 xfailed** (strict; §4) |
| Targeted NLP suites (`test_scorer*.py`, `test_keyword_list_v4.py`) | pass, with the same 3 xfails |
| `npm test` | 22 passed |
| `npm run typecheck`, `npm run lint` | clean |
| `npm run build` | success |
| `python docs/e2e_smoke.py` | **passed** on engine 4.1.0, against a separate database |
| Historical artifact hashes | 36/36 unchanged |
| Main database fingerprint | unchanged |

Environment-dependent: the E2E test needs the Edge browser, Playwright, MongoDB and both servers. The NLP tests need the cached MiniLM model.

**Reproduce (from `backend/`):**

```bash
pytest
python -m evaluation.experiments_v41          # dev F0-F4
python -m evaluation.evaluate                 # 4.1 dev report
python -m evaluation.evaluate --profile v4.0  # reproduces the archived 4.0 dev report -> *_rerun.*
python -m evaluation.uncertainty_v4_fresh     # CIs from the archived fresh-set report
cd ../frontend && npm test && npm run typecheck && npm run lint && npm run build
```
