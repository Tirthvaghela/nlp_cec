"""v4 engine regression tests: echo guard, antonym check, dense sentences, partial credit,
review flags, reproducibility of earlier configurations. Real MiniLM model; dev-style
fixtures only (nothing from the held-out sets). Keyword-list detector tests live in
test_keyword_list_v4.py; v3 safeguards in test_scorer_v3.py.
"""

import pytest

from app.nlp import EvaluationConfig, evaluate_answer
from app.nlp import correctness as cx

TFIDF = {
    "id": "tfidf", "text": "What is TF-IDF? Explain how it assigns weights to terms.", "max_marks": 4,
    "reference_answer": "Term frequency counts how often a term occurs in a document. Inverse document frequency is "
                        "log(N/df) and is high for rare terms. The TF-IDF weight is TF x IDF. Common words like 'the' "
                        "get a low weight while distinctive words get a high weight.",
    "rubric": [
        {"label": "Term frequency", "description": "Term frequency counts how often a term occurs in a document", "marks": 1},
        {"label": "Inverse document frequency", "description": "Inverse document frequency measures how rare a term is across the corpus, computed as log(N / df)", "marks": 1},
        {"label": "Weight = TF x IDF", "description": "The TF-IDF weight of a term is the product of its TF and IDF values", "marks": 1},
        {"label": "Common vs distinctive words", "description": "Words common to many documents such as 'the' get a low weight while distinctive words get a high weight", "marks": 1},
    ],
}
GD = {
    "id": "gd", "text": "What is gradient descent?", "max_marks": 3,
    "reference_answer": "Gradient descent is an optimisation algorithm that minimises a loss function. It moves the "
                        "parameters in the opposite direction of the gradient. The learning rate controls the step size.",
    "rubric": [
        {"label": "Minimises loss", "description": "Gradient descent is an optimisation algorithm that minimises a loss function", "marks": 1},
        {"label": "Against the gradient", "description": "Parameters move in the opposite direction of the gradient", "marks": 1},
        {"label": "Learning rate", "description": "The learning rate controls the size of each step", "marks": 1},
    ],
}


def run(q, text, backend, **cfg):
    config = EvaluationConfig.for_backend(backend.name, **cfg) if cfg else None
    return evaluate_answer(q, text, config, backend)


def codes(r):
    return {f.code for f in r.flags}


# --- echo guard: naming or restating the topic is not explaining ----------------------

@pytest.mark.parametrize("q,text", [
    (TFIDF, "TF-IDF gives weights to words."),
    (GD, "Gradient descent is used in machine learning."),
    (TFIDF, "TF-IDF is an important concept."),
])
def test_vague_restatements_earn_nothing(backend, q, text):
    r = run(q, text, backend)
    assert r.suggested_score == 0


def test_echo_guard_reports_its_decision(backend):
    r = run(TFIDF, "TF-IDF gives weights to words.", backend)
    assert "restates_question" in codes(r)
    assert any(c.issue == "echo" for c in r.concepts)
    # v3 behaviour (echo guard off) over-credited this answer because "TF-IDF" is expanded
    # to "term frequency inverse document frequency" by preprocessing
    v3 = run(TFIDF, "TF-IDF gives weights to words.", backend, echo_guard=False, antonym_check=False)
    assert v3.suggested_score > r.suggested_score


def test_echo_guard_unit_rules():
    q = "What is TF-IDF? Explain how it assigns weights to terms."
    assert cx.echo_only("TF-IDF gives weights to words.", q)
    assert not cx.echo_only("TF-IDF = TF x IDF.", q)  # a formula relates the terms
    assert not cx.echo_only("TF counts how often a word appears in a document.", q)
    q2 = "What are stop words? When should stop-word removal be avoided?"
    assert not cx.echo_only("Stop words are words like the, a, an, is.", q2)  # examples are content
    assert cx.echo_only("Stop words are words.", q2)


def test_formula_is_credited_not_echo(backend):
    r = run(TFIDF, "TF-IDF = TF x IDF.", backend)
    assert r.suggested_score >= 1
    assert all(c.issue != "echo" for c in r.concepts)


# --- short, dense, partial ---------------------------------------------------------

def test_short_correct_definition_beats_vague(backend):
    good = run(GD, "Gradient descent is an optimisation algorithm that minimises a loss function.", backend)
    vague = run(GD, "Gradient descent is used in machine learning.", backend)
    assert good.suggested_score >= 1 > vague.suggested_score
    assert good.suggested_score < GD["max_marks"]


def test_dense_correct_multi_concept_sentence_gets_full_credit(backend):
    r = run(TFIDF, "TF counts a term in a document, IDF = log(N/df) rewards rare terms, and their product gives low "
                   "weight to common words like 'the'.", backend)
    assert r.suggested_score >= 3.5
    assert "keyword_list" not in codes(r)


def test_incomplete_explanation_gets_partial_credit(backend):
    r = run(TFIDF, "IDF gives more importance to rare words.", backend)
    assert 0 < r.suggested_score < TFIDF["max_marks"]


# --- incorrect statements --------------------------------------------------------------

def test_antonym_flip_is_not_fully_credited_and_flagged(backend):
    r = run(GD, "Gradient descent is an algorithm that maximises a loss function.", backend)
    c = next(c for c in r.concepts if c.label == "Minimises loss")
    assert c.level != "matched" and c.issue == "antonym"
    assert "possible_contradiction" in codes(r) and r.needs_review


def test_wrong_statement_with_keywords_is_flagged_for_review(backend):
    r = run(GD, "Gradient descent maximises the loss function by moving the parameters in the same direction as the "
                "gradient.", backend)
    assert r.suggested_score < GD["max_marks"]
    assert r.needs_review and r.confidence == "low"


def test_antonym_unit_rules():
    assert cx.antonym_flip("minimises a loss function", "maximises a loss function", 1.0)
    # comparatives are left to reversed_comparison(), which knows the subject
    assert not cx.antonym_flip("Lemmatization is more accurate but slower than stemming",
                               "Lemmatization is more accurate, but stemming is faster.", 1.0)
    # a concept that contains both members of a pair is never flipped
    assert not cx.antonym_flip("common words get a low weight while distinctive words get a high weight",
                               "distinctive words get a high weight", 1.0)
    assert not cx.antonym_flip("minimises a loss function", "maximises a loss function", 0.1)  # little shared wording


# The next two were strict xfails (documented limitations) in engine 4.0; fixed in 4.1 by the attribute-swap
# check and the expanded-topic echo guard. More 4.1 tests, including the cases these fixes must NOT touch,
# are in test_scorer_v41.py.
def test_swapped_attributes_inside_one_concept(backend):
    r = run(TFIDF, "Common words like 'the' get a high weight while distinctive words get a low weight.", backend)
    assert next(c for c in r.concepts if c.label == "Common vs distinctive words").level != "matched"


def test_naming_the_expanded_term_is_not_an_explanation(backend):
    r = run(TFIDF, "TF-IDF stands for term frequency inverse document frequency.", backend)
    assert r.suggested_score <= 1


# --- configuration, reproducibility, history ---------------------------------------

def test_v4_metadata_and_determinism(backend):
    text = "TF counts how often a word appears in a document."
    a, b = run(TFIDF, text, backend).to_dict(), run(TFIDF, text, backend).to_dict()
    assert a == b
    cfg = a["metadata"]["config"]
    assert a["metadata"]["engine_version"].startswith("4.")
    assert cfg["echo_guard"] and cfg["antonym_check"] and cfg["keyword_list_predicate_cues"]
    assert cfg["adaptive_debias"] is False and cfg["token_recall_weight"] == 0


def test_v3_configuration_remains_reproducible(backend):
    """Historical v3 behaviour can be re-run by switching the v4 features off."""
    dense = "Supervised learning uses labelled data, while unsupervised learning uses unlabelled data."
    q = {"id": "s", "text": "Differentiate between supervised and unsupervised learning.", "max_marks": 2,
         "reference_answer": "Supervised learning uses labelled data. Unsupervised learning uses unlabelled data.",
         "rubric": [{"label": "Supervised", "description": "Supervised learning trains on labelled data with known outputs", "marks": 1},
                    {"label": "Unsupervised", "description": "Unsupervised learning finds structure in unlabelled data", "marks": 1}]}
    v3 = run(q, dense, backend, keyword_list_predicate_cues=False, antonym_check=False, echo_guard=False)
    v4 = run(q, dense, backend)
    assert any(c.keyword_list_evidence for c in v3.concepts)  # the v3 bug, reproduced on demand
    assert not any(c.keyword_list_evidence for c in v4.concepts)
    assert v4.suggested_score >= v3.suggested_score
