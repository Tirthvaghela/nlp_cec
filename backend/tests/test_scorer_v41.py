"""Engine 4.1 (final quality audit) regression tests. Real MiniLM model; dev-style fixtures only.

Covers: the two 4.0 expected failures that 4.1 fixes, the cases those fixes must not touch, the new
known limitation the echo fix introduces (and its review-flag mitigation), the remaining short-definition
limitation's mitigation, and feedback wording that must stay true. These fixtures are regression checks,
not an accuracy estimate.
"""

import pytest

from app.nlp import EvaluationConfig, evaluate_answer
from app.nlp import correctness as cx
from tests.conftest import QUESTION
from tests.test_scorer_v4 import TFIDF, run

CONTRAST = TFIDF["rubric"][3]["description"]  # "... common ... get a low weight while distinctive words get a high weight"
LABEL = "Common vs distinctive words"


def concept(r, label):
    return next(c for c in r.concepts if c.label == label)


def codes(r):
    return {f.code: f for f in r.flags}


# --- attribute-swap check -------------------------------------------------------------

def test_swapped_attributes_are_downgraded_and_flagged(backend):
    r = run(TFIDF, "Common words like 'the' get a high weight while distinctive words get a low weight.", backend)
    c = concept(r, LABEL)
    assert c.level != "matched" and c.issue == "antonym" and "opposite properties" in c.note
    assert "possible_contradiction" in codes(r) and r.needs_review


@pytest.mark.parametrize("text", [
    "Distinctive words get a high weight, while common words like 'the' get a low weight.",  # reordered
    "Common words get a low weight; high weight goes to distinctive words.",  # mixed order
    "A high weight goes to distinctive words and a low weight to common words.",  # attribute first
])
def test_correct_contrasts_are_not_treated_as_swaps(backend, text):
    assert not cx.swapped_attributes(CONTRAST, text, 1.0)
    assert concept(run(TFIDF, text, backend), LABEL).issue is None


SYNONYM_CONTRAST = "Frequent words such as 'the' receive low weights whereas rare distinctive words receive high weights."


@pytest.mark.xfail(strict=True, reason="Known limitation (README, antonym check since 4.0, found in the 4.1 audit): in a "
                                       "contrast concept, an antonym that describes the OTHER side ('rare distinctive "
                                       "words' vs 'common words') is read as a contradiction. An exemption was measured "
                                       "(experiments_v41 F4) and rejected: it would let real contradictions pass silently.")
def test_correct_synonym_contrast_is_not_penalised(backend):
    assert concept(run(TFIDF, SYNONYM_CONTRAST, backend), LABEL).issue is None


def test_antonym_false_positive_is_sent_to_review(backend):
    """Mitigation of the limitation above: the wrong downgrade is never silent."""
    assert not cx.swapped_attributes(CONTRAST, SYNONYM_CONTRAST, 1.0)  # the 4.1 swap check is not the cause
    r = run(TFIDF, SYNONYM_CONTRAST, backend)
    assert concept(r, LABEL).level == "partial" and "possible_contradiction" in codes(r) and r.needs_review
    # the rejected exemption (switch kept for measurement only) would remove the downgrade
    assert concept(run(TFIDF, SYNONYM_CONTRAST, backend, antonym_contrast_exemption=True), LABEL).issue is None


def test_swap_unit_rules():
    enc = "The encoder maps the input to a vector and the decoder produces the output"
    assert cx.swapped_attributes(enc, "The encoder maps the output to a vector and the decoder produces the input", 1.0)
    assert not cx.swapped_attributes(enc, "The decoder produces the output from the vector the encoder computed from the input", 1.0)
    assert not cx.swapped_attributes(CONTRAST, "Common words get low weight.", 1.0)  # one member only
    assert not cx.swapped_attributes(CONTRAST, "Common words get a high weight while distinctive words get a low weight.", 0.1)


# --- expanded-topic echo guard --------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Term frequency counts how often a term occurs in a document.",
    "Inverse document frequency is high for rare terms.",
    "IDF measures how rare a term is across documents.",
])
def test_explanations_that_use_the_expanded_name_are_not_echo(text):
    assert not cx.echo_only(text, TFIDF["text"], expand_topic=True)


@pytest.mark.parametrize("text", [
    "Tokenization splits text into tokens.",
    "Tokenization is important because later NLP steps such as tagging work on tokens.",
])
def test_explanations_repeating_question_terms_are_not_echo(backend, text):
    """Concern from the audit: repeating the question's terminology must not by itself reject an explanation."""
    assert not cx.echo_only(text, QUESTION["text"], expand_topic=True)
    r = evaluate_answer({"id": "q", **QUESTION}, text, None, backend)
    assert r.suggested_score > 0 and all(c.issue != "echo" for c in r.concepts)


@pytest.mark.xfail(strict=True, reason="Known limitation (README, introduced by the 4.1 expanded-topic echo guard): a "
                                       "minimal definition made only of the expanded name's words ('TF is the frequency "
                                       "of a term in a document') is treated as a restatement. Mitigated by a review flag.")
def test_minimal_definition_from_expanded_words_gets_credit(backend):
    r = run(TFIDF, "TF is the frequency of a term in a document.", backend)
    assert concept(r, "Term frequency").level != "missing"


def test_echo_guard_withholding_credit_requires_teacher_review(backend):
    """Mitigation of the limitation above: when the echo guard is why a concept earned nothing, review is required."""
    r = run(TFIDF, "TF is the frequency of a term in a document.", backend)
    f = codes(r)["restates_question"]
    assert f.severity == "review" and "valid definition" in f.message
    assert r.needs_review and r.confidence != "high"


def test_echo_rejection_without_lost_credit_stays_informational(backend):
    text = ("TF counts a term in a document, IDF = log(N/df) rewards rare terms, and their product gives low weight to "
            "common words like 'the'.")
    r = run(TFIDF, text, backend)
    echoed = [c for c in r.concepts if c.issue == "echo"]
    if echoed:  # the concept was still earned from another sentence: notes and flags must say so, not "no marks"
        assert all(c.level != "missing" and "Another sentence was credited" in c.note for c in echoed)
        f = codes(r)["restates_question"]
        assert f.severity == "info" and "earned no" not in f.message


def test_v40_profile_reproduces_the_old_behaviour(backend):
    v40 = dict(echo_expanded_topic=False, attribute_swap_check=False)
    r = run(TFIDF, "TF-IDF stands for term frequency inverse document frequency.", backend, **v40)
    assert r.suggested_score > 1  # the documented 4.0 over-credit, reproducible on demand
    r = run(TFIDF, "Common words like 'the' get a high weight while distinctive words get a low weight.", backend, **v40)
    assert concept(r, LABEL).level == "matched"


# --- remaining limitation: short definitions --------------------------------------------

def test_under_credited_short_definition_is_sent_to_review(backend):
    """test_scorer.py::test_short_definition_gets_credit stays a strict xfail. This checks the mitigation:
    the under-credited answer is not silently accepted - its signals disagree and it needs review."""
    r = evaluate_answer({"id": "q", **QUESTION}, "Tokenization is dividing a sentence into words.", None, backend)
    assert r.suggested_score < 1
    assert "divergent_signals" in codes(r) and r.needs_review and r.confidence == "low"


# --- feedback wording -------------------------------------------------------------------

def test_feedback_does_not_claim_factual_correctness(backend):
    r = run(TFIDF, "Term frequency counts how often a term occurs in a document.", backend)
    assert "correctly" not in r.feedback["text"] and not any("correctly" in s for s in r.feedback["strengths"])


def test_v41_metadata(backend):
    r = run(TFIDF, "TF counts how often a word appears in a document.", backend)
    cfg = r.metadata["config"]
    assert r.metadata["engine_version"] == "4.1.0"
    assert cfg["echo_expanded_topic"] and cfg["attribute_swap_check"]
    assert EvaluationConfig.for_backend(backend.name).fingerprint() == r.metadata["config_fingerprint"]
