"""v4 regression tests for the keyword-list detector (dense-sentence false positive).

v3 called a sentence a "keyword list" when fewer than 12% of its words were function
words. Dense but correct definitions ("Supervised learning uses labelled data, while
unsupervised learning uses unlabelled data.") have very few function words, so they
were wrongly downgraded. A bare list differs from a statement by having no
*predicate*: nothing that relates the terms (article, auxiliary, connective, pronoun
or relational verb). Fixtures use varied wording and domains; none come from the
held-out sets.
"""

import pytest

from app.nlp import evaluate_answer
from app.nlp import preprocessing as pp

BARE_LISTS = [
    "TF IDF term frequency inverse document frequency weight log rare common words documents corpus",
    "bag of words vocabulary counts vector sparse order ignored meaning synonyms",
    "photosynthesis chlorophyll sunlight carbon dioxide water glucose oxygen chloroplast",
    "stack push pop top LIFO overflow underflow array linked list",
    "photosynthesis, chlorophyll, sunlight, carbon dioxide, glucose, oxygen, chloroplast",
    "neuron weights bias activation sigmoid backpropagation gradient loss epochs",
]
CONCISE_DEFINITIONS = [
    "Stop words carry little meaning.",
    "Overfitting means memorising noise in training data.",
    "A stack follows last in first out order.",
    "Tokenization splits text into tokens such as words.",
]
DENSE_CORRECT = [
    "Supervised learning uses labelled data, while unsupervised learning uses unlabelled data.",
    "Cosine similarity ignores vector length, so long and short documents compare fairly.",
    "Stemming crudely strips suffixes by rules, whereas lemmatization returns dictionary lemmas using part of speech.",
    "Embeddings capture semantic similarity unlike sparse one-hot vectors.",
    "Mitochondria produce ATP through aerobic respiration, powering cellular processes.",
    "TCP guarantees ordered delivery whereas UDP offers fast connectionless transmission.",
    "Dropout randomly disables neurons during training, reducing overfitting.",
]
WRONG_BUT_SENTENCES = [
    # incorrect claims with the expected keywords are still *statements*; they are handled by
    # the scoring and correctness safeguards, not by the keyword-list detector
    "IDF gives common words like 'the' the highest weight.",
    "Lemmatization simply cuts word endings using fixed rules.",
    "Supervised learning uses unlabelled data to discover clusters.",
]


@pytest.mark.parametrize("text", BARE_LISTS)
def test_bare_keyword_lists_are_detected(text):
    assert pp.is_keyword_list(text)


@pytest.mark.parametrize("text", CONCISE_DEFINITIONS + DENSE_CORRECT + WRONG_BUT_SENTENCES)
def test_statements_are_not_keyword_lists(text):
    assert not pp.is_keyword_list(text)


def test_structured_notes_are_not_keyword_lists():
    assert not pp.is_keyword_list("IDF = log(N/df) where N is the number of documents")
    assert not pp.is_keyword_list("Index = B-tree / hash DS mapping key -> row location.")


SUP = {
    "id": "sup", "text": "Differentiate between supervised and unsupervised learning.", "max_marks": 2,
    "reference_answer": "Supervised learning trains on labelled data with known outputs. Unsupervised learning works with "
                        "unlabelled data and finds structure on its own.",
    "rubric": [
        {"id": "c1", "label": "Supervised uses labels", "description": "Supervised learning trains on labelled data where each input has a known output", "marks": 1},
        {"id": "c2", "label": "Unsupervised uses no labels", "description": "Unsupervised learning works with unlabelled data and finds structure on its own", "marks": 1},
    ],
}


def test_dense_correct_sentence_is_not_downgraded_and_earns_both_concepts(backend):
    r = evaluate_answer(SUP, "Supervised learning uses labelled data, while unsupervised learning uses unlabelled data.",
                        backend=backend)
    assert "keyword_list" not in {f.code for f in r.flags}
    assert not any(c.keyword_list_evidence for c in r.concepts)
    assert r.suggested_score >= 1.5


def test_bare_list_of_the_same_terms_is_still_downgraded(backend):
    r = evaluate_answer(SUP, "supervised labelled data unsupervised unlabelled data clustering classification regression",
                        backend=backend)
    assert all(c.level != "matched" for c in r.concepts)
    assert r.suggested_score <= 1


def test_repeated_dense_sentence_earns_no_extra_credit(backend):
    s = "Supervised learning uses labelled data, while unsupervised learning uses unlabelled data. "
    once = evaluate_answer(SUP, s, backend=backend)
    thrice = evaluate_answer(SUP, s * 3, backend=backend)
    assert thrice.suggested_score == once.suggested_score
    assert "repeated_content" in {f.code for f in thrice.flags}
