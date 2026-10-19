"""Text preprocessing utilities.

Design rules:

* The original student answer is never modified. Segmentation works on the
  original string and returns character offsets, so evidence can be highlighted
  exactly where the student wrote it.
* Cleaning is conservative: Unicode NFC (not NFKC, which would turn ``x²`` into
  ``x2``), typographic quotes/dashes mapped to ASCII, whitespace collapsed.
  Mathematical symbols and meaningful punctuation are kept.
* Stop words are only removed for keyword extraction. Text passed to the sentence
  embedding model keeps its stop words (and negations such as "not").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache

from nltk.stem import PorterStemmer
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

# Negations and quantifiers change meaning, so they are never treated as stop words.
_KEEP_WORDS = {"not", "no", "nor", "never", "without", "cannot", "less", "more", "few", "many", "most", "least"}
STOP_WORDS: frozenset[str] = frozenset(w for w in ENGLISH_STOP_WORDS if w not in _KEEP_WORDS) | {
    "also", "like", "eg", "ie", "etc", "example", "examples", "use", "used", "uses", "using",
    "way", "ways", "thing", "things", "called", "known", "basically", "simply", "process",
}

_TYPOGRAPHIC = str.maketrans(
    {
        "‘": "'", "’": "'", "‚": "'", "‛": "'",
        "“": '"', "”": '"', "„": '"',
        "–": "-", "—": "-", "−": "-",
        " ": " ", " ": " ", "​": "", "﻿": "",
        "…": "...",
    }
)

# Common abbreviations. Expansion keeps the abbreviation and appends the long form,
# e.g. "NLP" -> "NLP (natural language processing)", so neither form is lost.
DEFAULT_ABBREVIATIONS: dict[str, str] = {
    "NLP": "natural language processing",
    "NLU": "natural language understanding",
    "NLG": "natural language generation",
    "AI": "artificial intelligence",
    "ML": "machine learning",
    "DL": "deep learning",
    "NN": "neural network",
    "RNN": "recurrent neural network",
    "LSTM": "long short-term memory network",
    "CNN": "convolutional neural network",
    "POS": "part of speech",
    "NER": "named entity recognition",
    "TF": "term frequency",
    "IDF": "inverse document frequency",
    "TF-IDF": "term frequency inverse document frequency",
    "BoW": "bag of words",
    "BOW": "bag of words",
    "OOV": "out of vocabulary",
    "LM": "language model",
    "LLM": "large language model",
    "QA": "question answering",
    "MT": "machine translation",
    "ATP": "adenosine triphosphate",
    "CO2": "carbon dioxide",
    "H2O": "water",
    "O2": "oxygen",
    "DB": "database",
    "OS": "operating system",
    "CPU": "central processing unit",
}

# Abbreviations that end with a period but do not end a sentence.
_NON_TERMINAL = {
    "e.g", "i.e", "etc", "vs", "dr", "mr", "mrs", "ms", "prof", "fig", "eq", "no",
    "approx", "cf", "al", "st", "jr", "sr", "dept",
}

_WORD_RE = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*|\d+(?:\.\d+)?")
_TOKEN_RE = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*|\d+(?:\.\d+)?|[^\sA-Za-z\d]")
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)]|[a-z][.)])\s+")

_stemmer = PorterStemmer()


@dataclass(frozen=True)
class Span:
    """A piece of the original text with its character offsets."""

    start: int
    end: int
    text: str


def normalize_text(text: str | None) -> str:
    """Unicode-safe normalisation: NFC, ASCII quotes/dashes, collapsed whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text).translate(_TYPOGRAPHIC)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    """Split text into word, number and symbol tokens (symbols such as + = ^ kept)."""
    return _TOKEN_RE.findall(text)


def words(text: str) -> list[str]:
    """Lower-cased word/number tokens only."""
    return [w.lower() for w in _WORD_RE.findall(text)]


def content_words(text: str) -> list[str]:
    """Words with stop words removed - used only for keyword/lexical evidence."""
    return [w for w in words(text) if w not in STOP_WORDS and (len(w) > 2 or w.isdigit())]


@lru_cache(maxsize=20000)
def stem(word: str) -> str:
    return _stemmer.stem(word.lower())


def _is_sentence_end(text: str, idx: int) -> bool:
    """Decide whether the terminal punctuation at ``idx`` really ends a sentence."""
    ch = text[idx]
    if ch in "!?":
        return True
    # Decimal numbers such as 3.14
    if idx + 1 < len(text) and text[idx + 1].isdigit():
        return False
    m = re.search(r"([A-Za-z.]+)$", text[: idx])
    if m:
        prev = m.group(1).lower().rstrip(".")
        if prev in _NON_TERMINAL or (len(prev) == 1 and prev.isalpha()):
            return False
    return True


def segment_sentences(text: str) -> list[Span]:
    """Sentence segmentation on the *original* text, returning offsets.

    Line breaks and bullet points are treated as boundaries, which handles answers
    written as lists. Abbreviations ("e.g.", "i.e.") and decimals do not split.
    """
    spans: list[Span] = []
    if not text or not text.strip():
        return spans

    line_start = 0
    for line in text.split("\n"):
        line_end = line_start + len(line)
        if line.strip():
            offset = line_start
            bullet = _BULLET_RE.match(line)
            seg_start = offset + (bullet.end() if bullet else 0)
            i = seg_start - offset
            while i < len(line):
                if line[i] in ".!?" and _is_sentence_end(line, i):
                    j = i
                    while j + 1 < len(line) and line[j + 1] in ".!?\"')":
                        j += 1
                    if j + 1 >= len(line) or line[j + 1].isspace():
                        _append_span(spans, text, seg_start, offset + j + 1)
                        seg_start = offset + j + 1
                        i = j
                i += 1
            _append_span(spans, text, seg_start, line_end)
        line_start = line_end + 1
    return spans


def _append_span(spans: list[Span], text: str, start: int, end: int) -> None:
    raw = text[start:end]
    stripped = raw.strip()
    if not stripped or not _WORD_RE.search(stripped):
        return
    lead = len(raw) - len(raw.lstrip())
    s = start + lead
    spans.append(Span(s, s + len(stripped), stripped))


def split_long_span(span: Span, max_words: int = 35) -> list[Span]:
    """Split very long sentences at clause separators (; :) so evidence stays focused."""
    if len(words(span.text)) <= max_words:
        return [span]
    parts: list[Span] = []
    start = 0
    for m in re.finditer(r"[;:]\s+", span.text):
        piece = span.text[start : m.start() + 1]
        if len(words(piece)) >= 4:
            parts.append(Span(span.start + start, span.start + m.start() + 1, piece.strip()))
            start = m.end()
    tail = span.text[start:]
    if tail.strip():
        if parts and len(words(tail)) < 4:
            last = parts.pop()
            parts.append(Span(last.start, span.end, span.text[last.start - span.start :].strip()))
        else:
            parts.append(Span(span.start + start, span.end, tail.strip()))
    return parts or [span]


_CLAUSE_SPLIT = re.compile(r",\s+(?:and\s+|but\s+|so\s+|while\s+|whereas\s+|which\s+)?|;\s+|\s+(?:and|but|while|whereas|because|so|since)\s+")


def split_clauses(span: Span, min_sentence_words: int = 12, min_clause_words: int = 3) -> list[Span]:
    """Clause-level pieces of a long sentence (in addition to the sentence itself).

    One long sentence often packs several rubric concepts; embedding the whole
    sentence dilutes each of them, so clauses are compared separately as well.
    Returns [] when the sentence is short or cannot be split meaningfully.
    """
    if len(words(span.text)) < min_sentence_words:
        return []
    pieces: list[Span] = []
    start = 0
    for m in _CLAUSE_SPLIT.finditer(span.text):
        chunk = span.text[start : m.start()]
        if len(words(chunk)) >= min_clause_words:
            pieces.append(Span(span.start + start, span.start + m.start(), chunk.strip()))
            start = m.end()
    tail = span.text[start:]
    if len(words(tail)) >= min_clause_words:
        pieces.append(Span(span.start + start, span.end, tail.strip()))
    elif pieces:
        last = pieces.pop()
        pieces.append(Span(last.start, span.end, span.text[last.start - span.start :].strip()))
    return pieces if len(pieces) >= 2 else []


_RELATION_SYMBOLS = re.compile(r"[=:()<>]|->|→")


# --- predicate cues (v4) --------------------------------------------------------------
# A statement relates its terms; a bare keyword list does not. These closed-class words
# and verb forms signal that terms are being related. Prepositions such as "of", "in",
# "for", "to", "with", "on", "and", "or" are NOT cues: they occur inside multi-word terms
# ("bag of words", "part of speech").
_GLUE = {
    "the", "a", "an", "this", "these", "those", "its", "their", "each", "every", "it", "they", "we", "you",
    "he", "she", "which", "that", "who", "whose", "what",
    "is", "are", "was", "were", "be", "been", "being", "am", "has", "have", "had", "do", "does", "did",
    "can", "could", "will", "would", "shall", "should", "may", "might", "must", "cannot",
    "while", "whereas", "because", "so", "since", "but", "although", "though", "unless", "until", "if",
    "when", "where", "than", "unlike", "therefore", "thus", "hence", "however", "instead", "through",
    "into", "from", "by", "via", "during", "without", "whether", "not",
}
_RELATIONAL_VERBS = (
    "use mean produce split ignore represent convert contain store return remove reduce give make take find learn "
    "predict assign compute calculate depend refer describe define identify classify capture compare allow require "
    "include avoid help ensure measure carry become cause prevent improve detect generate transform encode decode "
    "estimate assume guarantee offer provide follow cut strip apply treat place turn lead look keep lose rely consist "
    "involve divide translate execute run stop handle check create build extract match combine select solve show "
    "inherit override absorb release emit trap warm minimise minimize maximise maximize update move change increase "
    "decrease raise lower penalise penalize disable enable reuse map tag break chop look trains train"
).split()
# Ambiguous with plural nouns that appear in keyword lists - never used as cues.
_NOUN_LIKE = {"counts", "labels", "groups", "weights", "words", "orders", "lists", "maps", "trains", "tags", "breaks"}
_ADVERB_EXCEPTIONS = {"family", "supply", "apply", "reply", "assembly", "anomaly", "monopoly", "butterfly", "ally",
                      "rely", "italy", "july", "only", "early", "daily", "jelly", "belly", "fly", "poly"}


def _third_person(v: str) -> str:
    if v.endswith(("s", "x", "z", "ch", "sh")):
        return v + "es"
    if v.endswith("y") and v[-2:-1] not in "aeiou":
        return v[:-1] + "ies"
    return v + "s"


_VERB_FORMS = {_third_person(v) for v in _RELATIONAL_VERBS} - _NOUN_LIKE


def has_predicate_cue(text: str) -> bool:
    """True if the text relates its terms (article, pronoun, auxiliary, connective, -ly adverb
    or a 3rd-person relational verb after the first word)."""
    ws = words(text)
    for n, w in enumerate(ws):
        if w in _GLUE:
            return True
        if n > 0 and w in _VERB_FORMS:
            return True
        if len(w) >= 5 and w.endswith("ly") and w not in _ADVERB_EXCEPTIONS:
            return True
    return False


def is_keyword_list(text: str, min_words: int = 6, max_function_ratio: float = 0.12,
                    require_no_predicate: bool = True) -> bool:
    """True for "sentences" that are just strings of keywords with no explanation.

    Requires: enough words, no relation symbols (=, ->, :, brackets - so notes like
    "IDF = log(N/df)" are not lists), almost no function words, and (v4) no predicate cue.
    v3 used the function-word ratio alone, which misclassified dense but correct
    statements such as "Supervised learning uses labelled data, while unsupervised
    learning uses unlabelled data" (1 function word in 11).
    """
    ws = words(text)
    if len(ws) < min_words or _RELATION_SYMBOLS.search(text):
        return False
    function = sum(1 for w in ws if w in ENGLISH_STOP_WORDS)
    if function / len(ws) >= max_function_ratio:
        return False
    return not (require_no_predicate and has_predicate_cue(text))


def expand_abbreviations(text: str, extra: dict[str, str] | None = None) -> str:
    """Append long forms after known abbreviations: "NER" -> "NER (named entity recognition)"."""
    table = dict(DEFAULT_ABBREVIATIONS)
    if extra:
        table.update(extra)
    # Longest first so "TF-IDF" wins over "TF".
    keys = sorted(table, key=len, reverse=True)
    pattern = re.compile(r"(?<![\w-])(" + "|".join(re.escape(k) for k in keys) + r")(?![\w-])")
    lower_text = text.lower()

    def repl(m: re.Match[str]) -> str:
        abbr = m.group(1)
        long_form = table[abbr]
        # Skip if the long form is already written right next to it.
        window = lower_text[max(0, m.start() - 60) : m.end() + 60]
        if long_form.lower() in window:
            return abbr
        return f"{abbr} ({long_form})"

    return pattern.sub(repl, text)


def fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def build_vocabulary(*texts: str) -> set[str]:
    vocab: set[str] = set()
    for t in texts:
        vocab.update(w for w in words(t) if len(w) >= 3)
    return vocab


def correct_spelling(text: str, vocabulary: set[str], min_ratio: float = 0.84) -> tuple[str, list[tuple[str, str]]]:
    """Map likely misspellings onto the question's own vocabulary.

    Only words of length >= 5 that are absent from the vocabulary are considered,
    and they are replaced by a vocabulary word with the same first letter and a
    high character-level similarity. Returns the corrected text and the list of
    (original, corrected) pairs so the correction is transparent.
    """
    if not vocabulary:
        return text, []
    by_initial: dict[str, list[str]] = {}
    for v in vocabulary:
        by_initial.setdefault(v[0], []).append(v)
    corrections: list[tuple[str, str]] = []

    def repl(m: re.Match[str]) -> str:
        word = m.group(0)
        lw = word.lower()
        if len(lw) < 5 or lw in vocabulary or lw in STOP_WORDS:
            return word
        best, best_ratio = None, min_ratio
        for cand in by_initial.get(lw[0], ()):
            if abs(len(cand) - len(lw)) > 3:
                continue
            r = fuzzy_ratio(lw, cand)
            if r > best_ratio or (r == best_ratio and best is not None and cand < best):
                best, best_ratio = cand, r
        if best is None or stem(best) == stem(lw):
            return word
        corrections.append((word, best))
        return best

    corrected = re.sub(r"[A-Za-z]+", repl, text)
    return corrected, corrections


def prepare_for_embedding(text: str, vocabulary: set[str] | None = None,
                          abbreviations: dict[str, str] | None = None,
                          min_ratio: float = 0.84) -> tuple[str, list[tuple[str, str]]]:
    """Normalise -> spelling correction -> abbreviation expansion."""
    clean = normalize_text(text)
    corrections: list[tuple[str, str]] = []
    if vocabulary:
        clean, corrections = correct_spelling(clean, vocabulary, min_ratio)
    return expand_abbreviations(clean, abbreviations), corrections


def key_terms(text: str) -> list[str]:
    """Stemmed, de-duplicated content terms (order preserved)."""
    seen: dict[str, None] = {}
    for w in content_words(text):
        seen.setdefault(stem(w), None)
    return list(seen)


def normalize_concept(text: str) -> str:
    """Canonical form of a concept/keyphrase used for de-duplication and matching."""
    return " ".join(stem(w) for w in content_words(normalize_text(text)))


def term_coverage(terms: list[str], text_terms: set[str], min_ratio: float = 0.84) -> tuple[float, list[str]]:
    """Fraction of ``terms`` present in ``text_terms`` (exact stem or fuzzy match)."""
    if not terms:
        return 0.0, []
    hits: list[str] = []
    for t in terms:
        if t in text_terms or (len(t) >= 5 and any(fuzzy_ratio(t, x) >= min_ratio for x in text_terms if abs(len(x) - len(t)) <= 2)):
            hits.append(t)
    return len(hits) / len(terms), hits


def phrase_present(phrase: str, text_terms: set[str], min_ratio: float = 0.84) -> bool:
    """A keyword phrase is present if all of its content terms are present."""
    terms = key_terms(phrase) or [stem(w) for w in words(phrase)]
    if not terms:
        return False
    cov, _ = term_coverage(terms, text_terms, min_ratio)
    return cov >= 1.0
