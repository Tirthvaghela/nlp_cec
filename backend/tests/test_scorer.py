"""Behavioural tests of the scoring engine with the real embedding model."""

import pytest

from app.nlp import EvaluationConfig, QuestionSpec, RubricError, evaluate_answer
from app.nlp.similarity import TfidfBackend
from tests.conftest import GOOD_ANSWER, QUESTION


def spec(**overrides) -> QuestionSpec:
    d = {"id": "q1", **QUESTION, **overrides}
    return QuestionSpec.from_dict(d)


def score(answer, backend, **overrides):
    return evaluate_answer(spec(**overrides), answer, backend=backend)


def test_good_answer_scores_high_with_evidence_from_original_text(backend):
    r = score(GOOD_ANSWER, backend)
    assert r.suggested_score >= 3
    assert r.suggested_score <= r.max_marks
    for c in r.concepts:
        if c.evidence:
            # Evidence is quoted verbatim from the student's answer.
            assert GOOD_ANSWER[c.evidence.start : c.evidence.end] == c.evidence.text
    assert r.feedback["strengths"]


def test_ordering_full_partial_irrelevant(backend):
    full = score(GOOD_ANSWER, backend).suggested_score
    partial = score("A good tokenizer must handle punctuation marks and contractions such as don't.", backend).suggested_score
    irrelevant = score(
        "Cricket is a popular sport in India. The IPL attracts millions of viewers every year. Players train hard and "
        "teams compete for the trophy. Fans celebrate every boundary and wicket with great enthusiasm.", backend)
    assert full > partial > irrelevant.suggested_score
    assert irrelevant.suggested_score == 0
    assert any(f.code == "off_topic" for f in irrelevant.flags)


@pytest.mark.xfail(strict=True, reason="Known limitation (see README): topic-debiased similarity under-credits short "
                   "definitions whose wording is close to the question itself.")
def test_short_definition_gets_credit(backend):
    assert score("Tokenization is dividing a sentence into words.", backend).suggested_score >= 1


def test_empty_answer(backend):
    r = score("   ", backend)
    assert r.suggested_score == 0
    assert all(c.level == "missing" for c in r.concepts)
    assert r.flags[0].code == "empty_answer"
    assert "No answer" in r.feedback["summary"]


def test_scores_are_bounded_and_in_half_steps(backend):
    for ans in [GOOD_ANSWER, GOOD_ANSWER * 3, "tokens", "Tokenization splits text into tokens."]:
        r = score(ans, backend)
        assert 0 <= r.suggested_score <= r.max_marks
        assert (r.suggested_score * 2) == int(r.suggested_score * 2)
        assert sum(c.awarded for c in r.concepts) >= r.suggested_score - 1e-9


def test_repetition_does_not_earn_extra_marks(backend):
    once = score("Tokenization splits text into tokens such as words.", backend)
    many = score("Tokenization splits text into tokens such as words. " * 4, backend)
    assert many.suggested_score == once.suggested_score
    assert any(f.code == "repeated_content" for f in many.flags)


def test_similar_concepts_are_not_credited_twice_from_one_sentence(backend):
    rubric = [
        {"label": "Splitting", "description": "Tokenization splits text into tokens such as words", "marks": 2},
        {"label": "Splitting again", "description": "Tokenization divides text into word tokens", "marks": 2},
    ]
    r = score("Tokenization splits text into word tokens.", backend, rubric=rubric)
    credited = [c for c in r.concepts if c.level != "missing"]
    assert len(credited) <= 1
    assert any(c.note and "not counted twice" in c.note for c in r.concepts) or len(credited) == 0 or any(
        f.code == "similar_concepts" for f in r.flags)


def test_keyword_list_gets_reduced_credit_and_flag(backend):
    r = score("tokenization tokens words subwords characters punctuation contractions pipeline first step", backend)
    assert any(f.code == "keyword_list" for f in r.flags) or r.suggested_score <= 1
    assert all(c.level != "matched" for c in r.concepts if c.keyword_list_evidence)


def test_spelling_mistakes_are_tolerated(backend):
    clean = score("Tokenization splits raw text into tokens like words or characters.", backend).suggested_score
    typos = score("Tokenizaton spliting raw text into tokns like words or charecters.", backend)
    assert typos.suggested_score >= clean - 0.5
    assert any(f.code == "spelling_normalised" for f in typos.flags)


def test_rubric_marks_not_matching_max_are_scaled_and_flagged(backend):
    rubric = [{"label": "Definition", "description": QUESTION["rubric"][0]["description"], "marks": 1},
              {"label": "Special cases", "description": QUESTION["rubric"][2]["description"], "marks": 1}]
    r = score(GOOD_ANSWER, backend, rubric=rubric)  # sums to 2, max is 4
    assert sum(c.marks for c in r.concepts) == pytest.approx(4)
    assert any(f.code == "rubric_marks_scaled" for f in r.flags)
    assert r.confidence != "high"


def test_missing_rubric_derived_from_reference_and_low_confidence(backend):
    r = score(GOOD_ANSWER, backend, rubric=[])
    assert r.concepts and all(c.id.startswith("auto") for c in r.concepts)
    assert r.confidence == "low" and r.needs_review


def test_no_rubric_and_no_reference_raises(backend):
    with pytest.raises(RubricError):
        score(GOOD_ANSWER, backend, rubric=[], reference_answer="")


def test_different_max_marks_respected(backend):
    rubric = [dict(i, marks=i["marks"] * 2.5) for i in QUESTION["rubric"]]
    r = score(GOOD_ANSWER, backend, rubric=rubric, max_marks=10)
    assert r.max_marks == 10 and 0 <= r.suggested_score <= 10


def test_deterministic_and_reproducible_metadata(backend):
    a = score(GOOD_ANSWER, backend).to_dict()
    b = score(GOOD_ANSWER, backend).to_dict()
    assert a == b
    meta = a["metadata"]
    assert meta["engine_version"] and meta["config_fingerprint"] and meta["rubric_fingerprint"]
    assert meta["config"]["match_threshold"] == EvaluationConfig.for_backend("embedding").match_threshold


def test_per_question_threshold_override_changes_strictness(backend):
    answer = "Tokenization is dividing a sentence into words."
    lenient = score(answer, backend, settings={"match_threshold": 0.3, "partial_threshold": 0.2}).suggested_score
    strict = score(answer, backend, settings={"match_threshold": 0.95, "partial_threshold": 0.9}).suggested_score
    assert lenient > strict


def test_feedback_only_quotes_the_student(backend):
    r = score(GOOD_ANSWER, backend)
    for c in r.concepts:
        if c.evidence:
            assert c.evidence.text in GOOD_ANSWER
    for line in r.feedback["missing"]:
        assert "not found in your answer" in line


def test_tfidf_fallback_backend_works_and_is_flagged():
    r = evaluate_answer(spec(), GOOD_ANSWER, backend=TfidfBackend())
    assert r.metadata["backend"] == "tfidf"
    assert any(f.code == "fallback_backend" for f in r.flags)
    assert r.confidence == "low"
    assert 0 <= r.suggested_score <= 4
