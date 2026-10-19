from app.nlp import preprocessing as pp


def test_normalize_keeps_math_and_meaningful_punctuation():
    text = "  E = mc² — and   x² + y² ≤ 1;“quoted”  "
    out = pp.normalize_text(text)
    assert "mc²" in out and "x²" in out and "≤" in out  # NFC, not NFKC
    assert '"quoted"' in out and " - " in out
    assert "  " not in out and out == out.strip()


def test_segmentation_respects_abbreviations_decimals_and_offsets():
    text = "Pi is about 3.14 in value. Words, e.g. cats, are tokens! Is it done? Yes.\n- bullet one\n2. second item"
    spans = pp.segment_sentences(text)
    texts = [s.text for s in spans]
    assert texts[0] == "Pi is about 3.14 in value."
    assert texts[1] == "Words, e.g. cats, are tokens!"
    assert "bullet one" in texts and "second item" in texts
    for s in spans:  # offsets point into the original, unchanged string
        assert text[s.start : s.end] == s.text


def test_tokenize_and_stopwords_keep_negation():
    assert pp.tokenize("x+y=3.5, isn't it?") == ["x", "+", "y", "=", "3.5", ",", "isn't", "it", "?"]
    cw = pp.content_words("This is not a good model for the task")
    assert "not" in cw and "good" in cw and "the" not in cw and "is" not in cw


def test_abbreviation_expansion_keeps_both_forms_and_skips_when_already_expanded():
    assert pp.expand_abbreviations("NER finds names.") == "NER (named entity recognition) finds names."
    assert "TF-IDF (term frequency inverse document frequency)" in pp.expand_abbreviations("TF-IDF weights")
    already = "Named entity recognition (NER) finds names."
    assert pp.expand_abbreviations(already) == already


def test_spelling_correction_uses_question_vocabulary_only():
    vocab = pp.build_vocabulary("Tokenization splits text into tokens and handles punctuation")
    corrected, pairs = pp.correct_spelling("Tokenizaton spliting handels punctuaton", vocab)
    # "spliting" is left as written: its stem already equals "split", so stemming handles it.
    assert corrected == "tokenization spliting handles punctuation"
    assert ("Tokenizaton", "tokenization") in pairs and ("punctuaton", "punctuation") in pairs
    # unrelated words are left alone
    assert pp.correct_spelling("cricket stadium", vocab)[0] == "cricket stadium"


def test_clause_splitting_and_keyword_list_detection():
    long = pp.Span(0, 0, "Using carbon dioxide from the air and water from the soil, the plant changes light energy "
                         "into chemical energy, and oxygen is given off")
    assert len(pp.split_clauses(long)) >= 2
    assert pp.split_clauses(pp.Span(0, 0, "Short sentence here.")) == []
    assert pp.is_keyword_list("TF IDF term frequency inverse document frequency weight log rare common words")
    assert not pp.is_keyword_list("IDF = log(N/df) where N is the number of documents")
    assert not pp.is_keyword_list("Stop words are common words that carry little meaning.")


def test_concept_normalisation_matches_variants():
    assert pp.normalize_concept("The splitting of texts") == pp.normalize_concept("split text")
    assert pp.normalize_concept("Tokens are created") == pp.normalize_concept("token created")
