"""Regression tests for the v3 grading weaknesses (real MiniLM model, no mocks of scoring).

Scenario map (task list -> test):
  1 short correct definition ........ test_short_correct_definition_beats_vague_answer, test_scorer.py::test_short_definition_gets_credit (xfail, known limitation)
  2 short vague answer ............... test_short_correct_definition_beats_vague_answer
  3 correct, different wording ....... test_scorer.py::test_good_answer_scores_high_with_evidence_from_original_text, test_correct_comparison_is_not_penalised
  4 partially correct ................ test_scorer.py::test_ordering_full_partial_irrelevant, test_partial_credit_levels_are_ordered
  5 wrong definition with keywords ... test_wrong_statement_with_expected_keywords_is_not_full_marks
  6 swapped definitions .............. test_swapped_definitions_are_flagged_and_not_full_marks
  7 negated / contradicted statement . test_negated_statement_does_not_earn_the_concept, test_reversed_comparison_earns_nothing
  8 long irrelevant .................. test_scorer.py::test_ordering_full_partial_irrelevant, test_irrelevant_long_answer_does_not_beat_concise_correct
  9 bare keyword list ................ test_scorer.py::test_keyword_list_gets_reduced_credit_and_flag
 10 repeated sentences ............... test_scorer.py::test_repetition_does_not_earn_extra_marks
 11 one sentence vs similar items .... test_scorer.py::test_similar_concepts_are_not_credited_twice_from_one_sentence
 12 spelling mistake ................. test_scorer.py::test_spelling_mistakes_are_tolerated
 13 abbreviation ..................... test_abbreviation_is_expanded_and_credited
 14 empty answer ..................... test_scorer.py::test_empty_answer
 15 rubric marks do not add up ....... test_scorer.py::test_rubric_marks_not_matching_max_are_scaled_and_flagged
 16 model-loading failure / fallback . test_model_load_failure_falls_back_to_tfidf, test_scorer.py::test_tfidf_fallback_backend_works_and_is_flagged
 17 marks within [0, max] ............ test_marks_always_within_bounds, test_scorer.py::test_scores_are_bounded_and_in_half_steps
 18 reproducibility .................. test_v3_reproducible_with_metadata, test_scorer.py::test_deterministic_and_reproducible_metadata
Fixtures are dev-style questions; nothing from the held-out or final sets is used.
"""

import pytest

from app.nlp import EvaluationConfig, evaluate_answer
from app.nlp import correctness as cx
from app.nlp import similarity as sim

STEM = {
    "id": "stem", "text": "Differentiate between stemming and lemmatization.", "max_marks": 4,
    "reference_answer": "Stemming removes suffixes using heuristic rules, so the stem may not be a real word. Lemmatization "
                        "uses a vocabulary and the part of speech to return the dictionary form called the lemma. "
                        "Lemmatization is more accurate but slower than stemming.",
    "rubric": [
        {"id": "c1", "label": "Stemming uses rules", "description": "Stemming removes word suffixes using simple heuristic rules such as the Porter stemmer", "marks": 1},
        {"id": "c2", "label": "Stems may not be real words", "description": "The stem produced by stemming may not be a valid dictionary word", "marks": 1},
        {"id": "c3", "label": "Lemmatization returns the lemma", "description": "Lemmatization uses a vocabulary, morphological analysis and the part of speech to return the dictionary form called the lemma", "marks": 1},
        {"id": "c4", "label": "Accuracy vs speed", "description": "Lemmatization is more accurate but slower than stemming", "marks": 1},
    ],
}
TOK = {
    "id": "tok", "text": "Explain tokenization in NLP and why it is important.", "max_marks": 4,
    "reference_answer": "Tokenization splits raw text into tokens such as words, subwords or characters. It is the first step "
                        "of an NLP pipeline and later steps operate on tokens. A tokenizer must handle punctuation, "
                        "contractions and special cases.",
    "rubric": [
        {"label": "Definition", "description": "Tokenization splits raw text into smaller units called tokens such as words, subwords or characters", "marks": 2},
        {"label": "First pipeline step", "description": "Tokenization is the first preprocessing step and later NLP steps operate on the tokens", "marks": 1},
        {"label": "Special cases", "description": "A tokenizer must handle punctuation, contractions and other special cases", "marks": 1},
    ],
}
STOP = {
    "id": "stop", "text": "What are stop words? When should stop-word removal be avoided?", "max_marks": 3,
    "reference_answer": "Stop words are very frequent words such as the and is that carry little meaning. Removing them "
                        "reduces noise. They should be kept when they carry meaning, such as not in sentiment analysis.",
    "rubric": [
        {"label": "Definition", "description": "Stop words are very frequent function words such as 'the', 'is' and 'and' that carry little meaning on their own", "marks": 1},
        {"label": "Benefit", "description": "Removing stop words reduces noise and the size of the data, making search and classification more efficient", "marks": 1},
        {"label": "When to keep", "description": "Stop words should not be removed when they carry meaning, such as negations like 'not' in sentiment analysis", "marks": 1},
    ],
}
NER = {
    "id": "ner", "text": "Explain Named Entity Recognition and its applications.", "max_marks": 2,
    "reference_answer": "Named entity recognition finds named entities in text and classifies them into categories such as "
                        "person, organization and location.",
    "rubric": [
        {"label": "Definition", "description": "Named entity recognition locates named entities in text and classifies them into categories", "marks": 1},
        {"label": "Categories", "description": "Typical categories include person, organization, location and date", "marks": 1},
    ],
}


def score(q, answer, backend, **cfg):
    config = EvaluationConfig.for_backend(backend.name, **cfg) if cfg else None
    return evaluate_answer(q, answer, config, backend)


def codes(r):
    return {f.code for f in r.flags}


def level(r, label):
    return next(c for c in r.concepts if c.label == label)


# --- correctness safeguards ---------------------------------------------------------------

def test_correct_comparison_is_not_penalised(backend):
    r = score(STEM, "Stemming chops endings with fixed rules like the Porter algorithm, so 'studies' can become 'studi', "
                    "which is not a real word. Lemmatization looks words up in a dictionary and uses the part of speech to "
                    "return the lemma. Lemmatization is more accurate but slower.", backend)
    assert r.suggested_score >= 3.5
    assert not codes(r) & {"possible_swap", "possible_contradiction"}
    assert all(c.issue is None for c in r.concepts)


def test_swapped_definitions_are_flagged_and_not_full_marks(backend):
    swapped = ("Lemmatization simply cuts the end of the word using rules, so it is very fast. Stemming uses a "
               "dictionary and grammar to find the correct root word, so stemming is more accurate.")
    r = score(STEM, swapped, backend)
    assert "possible_swap" in codes(r) and r.confidence == "low" and r.needs_review
    assert r.suggested_score < STEM["max_marks"]
    # Known fragility (README): depending on rubric wording some swapped content can still earn credit,
    # but the swap safeguard must never make things worse than the v2 engine.
    v2 = score(STEM, swapped, backend, correctness_checks=False)
    assert r.suggested_score <= v2.suggested_score


def test_reversed_comparison_earns_nothing(backend):
    r = score(STEM, "Stemming is more accurate than lemmatization.", backend)
    c = level(r, "Accuracy vs speed")
    assert c.level == "missing" and c.issue == "reversed_comparison"
    assert "possible_swap" in codes(r)


def test_negated_statement_does_not_earn_the_concept(backend):
    r = score(TOK, "Tokenization is not the first step; it is done only after stemming and tagging are finished.", backend)
    assert level(r, "First pipeline step").level != "matched"
    positive = score(TOK, "Tokenization is the first step, and later steps such as tagging operate on the tokens.", backend)
    assert level(positive, "First pipeline step").level == "matched"


def test_wrong_statement_with_expected_keywords_is_not_full_marks(backend):
    r = score(STOP, "Stop words are rare technical words that carry the most meaning, so removing them makes "
                    "classification less efficient.", backend)
    assert r.suggested_score < 2
    assert level(r, "Benefit").level == "missing"


def test_negation_check_skips_implicitly_negative_concepts():
    # "light-independent" is correctly paraphrased as "does not need light"
    assert not cx.added_negation("the light-independent Calvin cycle", "the Calvin cycle does not need light", 1.0)
    assert cx.added_negation("Tokenization is the first step", "Tokenization is not the first step", 1.0)
    assert not cx.has_negation("keep the word 'not' in sentiment analysis")  # quoted mention, not a negation
    assert not cx.has_negation("TF = no. of times a term occurs")


def test_entity_groups_and_reversed_comparisons():
    ents = cx.concept_entities(STEM["text"], [i["description"] for i in STEM["rubric"]])
    assert ents[0].own == {"stem"} and ents[0].foreign == {"lemmat"}
    assert ents[2].own == {"lemmat"} and ents[2].foreign == {"stem"}
    assert cx.misattributed(ents[2], cx.term_set("Stemming uses a dictionary"))
    assert not cx.misattributed(ents[2], cx.term_set("It uses a dictionary"))  # no entity named -> no decision
    concept = "Lemmatization is more accurate but slower than stemming"
    ent = {"stem", "lemmat"}
    assert cx.reversed_comparison(concept, "Stemming is more accurate.", ent)
    assert cx.reversed_comparison(concept, "Lemmatization is less accurate than stemming.", ent)
    assert not cx.reversed_comparison(concept, "Lemmatization is better than stemming because it is more accurate, "
                                               "but stemming is faster.", ent)
    # one-hot "encoding" and "vectors" concepts form one entity group
    q = "What are word embeddings? How do they differ from one-hot encoding?"
    groups = cx.concept_entities(q, ["One-hot encoding represents each word as a sparse vector",
                                     "One-hot vectors carry no notion of similarity",
                                     "Word embeddings are dense, low-dimensional vectors"])
    assert groups[0].own == groups[1].own and "encod" in groups[1].own


def test_single_entity_questions_skip_entity_checks():
    ents = cx.concept_entities(TOK["text"], [i["description"] for i in TOK["rubric"]])
    assert all(not e.own and not e.foreign for e in ents)


# --- partial credit, short answers, irrelevance -------------------------------------------

def test_short_correct_definition_beats_vague_answer(backend):
    short = score(STOP, "Stop words are very common words like 'the' and 'is' that carry little meaning.", backend)
    vague = score(STOP, "Stop words are words.", backend)
    assert level(short, "Definition").level == "matched"
    assert short.suggested_score >= 1 > vague.suggested_score
    assert short.suggested_score < STOP["max_marks"]  # one concept only - never full marks


def test_partial_credit_levels_are_ordered(backend):
    full = score(STOP, "Stop words are very common words such as 'the' and 'is' with little meaning. Removing them "
                       "reduces noise and makes classification faster. But keep negations like 'not' for sentiment "
                       "analysis.", backend).suggested_score
    two = score(STOP, "Stop words are very common words such as 'the' and 'is' with little meaning. Removing them "
                      "reduces noise and makes classification faster.", backend).suggested_score
    one = score(STOP, "Stop words are very common words such as 'the' and 'is' with little meaning.", backend).suggested_score
    assert full > two > one > 0


def test_irrelevant_long_answer_does_not_beat_concise_correct(backend):
    concise = score(TOK, "Tokenization splits text into tokens such as words and handles punctuation and contractions.", backend)
    long_irrelevant = score(TOK, "Natural language processing is a very interesting field of artificial intelligence. "
                                 "It has many applications such as chatbots, translation and voice assistants. Many "
                                 "companies invest heavily in it and many jobs will be created in the future. Students "
                                 "should learn Python because it has many libraries for data science.", backend)
    assert long_irrelevant.suggested_score == 0 < concise.suggested_score


def test_abbreviation_is_expanded_and_credited(backend):
    abbr = score(NER, "NER finds named entities in text and classifies them into categories like person, org and location.", backend)
    full = score(NER, "Named entity recognition finds named entities in text and classifies them into categories like "
                      "person, organization and location.", backend)
    assert 0 < abbr.suggested_score <= full.suggested_score


# --- bounds, reproducibility, fallback -----------------------------------------------------

@pytest.mark.parametrize("answer", [
    "", "x", "tokens " * 300, "Tokenization splits text into tokens. " * 20,
    "Tokenization is not the first step and it does not split text.", "TF-IDF = TF x IDF; NER; POS; LSTM.",
])
def test_marks_always_within_bounds(backend, answer):
    for q in (TOK, STEM, STOP):
        r = score(q, answer, backend)
        assert 0 <= r.suggested_score <= q["max_marks"]
        for c in r.concepts:
            assert 0 <= c.awarded <= c.marks


def test_v3_reproducible_with_metadata(backend):
    text = "Stemming uses a dictionary. Lemmatization cuts endings with rules."
    a, b = score(STEM, text, backend).to_dict(), score(STEM, text, backend).to_dict()
    assert a == b
    assert int(a["metadata"]["engine_version"].split(".")[0]) >= 3  # v3 safeguards remain in v4+
    assert a["metadata"]["config"]["correctness_checks"] is True


def test_model_load_failure_falls_back_to_tfidf(monkeypatch, backend):
    saved = sim.loaded_backend()
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    try:
        sim.set_backend(None)
        fb = sim.get_backend("auto", "this-model/does-not-exist-anywhere")
        assert fb.name == "tfidf" and fb.fallback_reason
        r = evaluate_answer(TOK, "Tokenization splits text into tokens.", backend=fb)
        assert "fallback_backend" in codes(r) and r.metadata["backend"] == "tfidf" and r.needs_review
    finally:
        sim.set_backend(saved)
