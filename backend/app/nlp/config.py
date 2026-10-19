"""Evaluation configuration.

Every number that influences a score lives here so that a saved evaluation can
be reproduced exactly from (rubric snapshot + config snapshot + engine version).

Threshold values are *backend specific*: cosine similarities from a sentence
embedding model and from TF-IDF vectors live on different scales. The defaults
below were chosen by ``backend/evaluation/calibrate.py`` on the DEV split of the
synthetic evaluation dataset and then checked on the held-out TEST split with
``backend/evaluation/evaluate.py`` (see README, "Dataset and evaluation").
Teachers can override thresholds per question when a question needs stricter or
more lenient matching.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace

ENGINE_VERSION = "4.1.0"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass(frozen=True)
class Thresholds:
    match: float  # concept score (blended semantic + keyword) for "matched"
    partial: float  # concept score for "partially matched"
    off_topic: float  # raw answer-vs-reference cosine below which an answer is off-topic
    relevance: float  # raw cosine for a sentence to count as related to the question
    holistic_high: float  # raw answer-vs-reference cosine considered "very similar"


# Chosen by evaluation/calibrate.py on the DEV split (Q1-Q8) with leave-one-question-out
# cross-validation (see results/calibration_<backend>.json):
#   embedding: debias 0.9, keyword weight 0.15, no sentence pairs -> LOQO-CV MAE 0.605
#   tfidf:     keyword weight 0.0, sentence pairs on              -> LOQO-CV MAE 0.772
# v3 (evaluation/experiments.py + freeze_v3.py, 74 dev answers incl. targeted v3 additions):
#   + correctness safeguards (correctness.py) -> LOQO-CV MAE 0.574 (v2 0.764, keyword baseline 0.797);
#   re-fitted thresholds unchanged (0.57 / 0.52). Token recall (alignment.py) was tested and NOT
#   adopted (0.689 with safeguards), so DEFAULT_TOKEN_RECALL_WEIGHT stays 0.
# v4 (evaluation/experiments_v4.py + freeze_v4.py, 85 dev answers incl. targeted v4 additions):
#   keyword-list predicate cues (bug fix) + antonym check + echo guard -> LOQO-CV MAE 0.594 (v3 0.712,
#   keyword baseline 0.818); thresholds unchanged (0.57 / 0.52). Adaptive debias was tested and REJECTED
#   (0.835), so DEFAULT_ADAPTIVE_DEBIAS stays False.
# v4.1 (final audit; evaluation/experiments_v41.py, DEV only - both held-out sets are already spent):
#   expanded-topic echo -> LOQO-CV MAE 0.582 (v4.0 0.594; 2 concept-level changes, both agree with the human label);
#   attribute-swap check -> fires on no dev answer (no measurable effect; targets a documented silent failure).
#   antonym contrast exemption -> fires on no dev answer; REJECTED: it removes a flagged false positive on correct
#   contrast paraphrases but would let real contradictions pass unflagged, so DEFAULT_ANTONYM_CONTRAST_EXEMPTION = False.
#   Thresholds unchanged. No held-out accuracy claim is made for 4.1.
DEFAULT_THRESHOLDS: dict[str, Thresholds] = {
    "embedding": Thresholds(match=0.57, partial=0.52, off_topic=0.20, relevance=0.40, holistic_high=0.75),
    "tfidf": Thresholds(match=0.29, partial=0.24, off_topic=0.08, relevance=0.15, holistic_high=0.45),
}
DEFAULT_KEYWORD_WEIGHT: dict[str, float] = {"embedding": 0.15, "tfidf": 0.0}
DEFAULT_DEBIAS_WEIGHT = 0.9
DEFAULT_HYBRID_WEIGHT = 0.0
DEFAULT_TOKEN_RECALL_WEIGHT = 0.0
DEFAULT_CORRECTNESS_CHECKS = True
DEFAULT_KEYWORD_LIST_PREDICATE_CUES = True  # v4 detector fix (always on; switch exists only for measurement)
DEFAULT_ADAPTIVE_DEBIAS = False
DEFAULT_ANTONYM_CHECK = True
DEFAULT_ECHO_GUARD = True
DEFAULT_ECHO_EXPANDED_TOPIC = True
DEFAULT_ATTRIBUTE_SWAP_CHECK = True
DEFAULT_ANTONYM_CONTRAST_EXEMPTION = False
DEFAULT_USE_PAIRS: dict[str, bool] = {"embedding": False, "tfidf": True}


@dataclass(frozen=True)
class EvaluationConfig:
    backend: str = "embedding"  # resolved backend: "embedding" | "tfidf"
    model_name: str = DEFAULT_MODEL
    match_threshold: float = DEFAULT_THRESHOLDS["embedding"].match
    partial_threshold: float = DEFAULT_THRESHOLDS["embedding"].partial
    off_topic_threshold: float = DEFAULT_THRESHOLDS["embedding"].off_topic
    relevance_threshold: float = DEFAULT_THRESHOLDS["embedding"].relevance
    holistic_high_threshold: float = DEFAULT_THRESHOLDS["embedding"].holistic_high
    # Weight of lexical (keyword) evidence. Keywords can only *raise* a concept
    # score: combined = s + w * k * (1 - s), so synonyms are never penalised.
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT["embedding"]
    # Semantic signal = (1 - a) * raw cosine + a * topic-debiased cosine, where the
    # debiased cosine projects the question's own embedding out of both texts.
    debias_weight: float = DEFAULT_DEBIAS_WEIGHT
    # Hybrid dense + sparse similarity: weight of TF-IDF character n-gram cosine
    # mixed into the embedding cosine (0 = embeddings only). Ignored by the tfidf backend.
    hybrid_weight: float = DEFAULT_HYBRID_WEIGHT
    # v3: weight of token-level concept recall (alignment.py) in the semantic signal:
    #   s = (1 - b) * s_sentence + b * recall. 0 disables it. Embedding backend only.
    token_recall_weight: float = DEFAULT_TOKEN_RECALL_WEIGHT
    # Weight of question-topic words inside a concept when computing token recall.
    topic_token_weight: float = 0.3
    # v3: rule-based correctness safeguards (correctness.py): misattributed / swapped
    # definitions, reversed comparisons, added negation.
    correctness_checks: bool = DEFAULT_CORRECTNESS_CHECKS
    # v4: keyword-list detector also requires the absence of predicate cues (preprocessing.py).
    keyword_list_predicate_cues: bool = DEFAULT_KEYWORD_LIST_PREDICATE_CUES
    # v4 candidate: per-concept debias weight = debias_weight * sqrt(1 - q^2), q = cos(concept, question),
    # i.e. trust the topic-debiased cosine in proportion to the concept's content beyond the question topic.
    adaptive_debias: bool = DEFAULT_ADAPTIVE_DEBIAS
    # v4 candidate: downgrade a concept whose evidence swaps a concept word for its antonym (correctness.py).
    antonym_check: bool = DEFAULT_ANTONYM_CHECK
    # v4 candidate: a sentence that adds fewer than two content words beyond the question's own
    # topic words (and abbreviation expansions) only names or restates the topic; it is not evidence.
    echo_guard: bool = DEFAULT_ECHO_GUARD
    # v4.1: the echo guard also treats the long forms of the question's abbreviations as topic words.
    echo_expanded_topic: bool = DEFAULT_ECHO_EXPANDED_TOPIC
    # v4.1: downgrade a concept whose evidence swaps the two members of an antonym pair that the
    # concept itself contains ("common -> low, distinctive -> high" written the other way round).
    attribute_swap_check: bool = DEFAULT_ATTRIBUTE_SWAP_CHECK
    # v4.1 candidate (REJECTED, kept for measurement only): the antonym check skips concepts that contrast two
    # things (both members of a pair present) and leaves them to the attribute-swap check.
    antonym_contrast_exemption: bool = DEFAULT_ANTONYM_CONTRAST_EXEMPTION
    # Also compare concepts with windows of two adjacent sentences.
    use_sentence_pairs: bool = DEFAULT_USE_PAIRS["embedding"]
    # Fraction of an item's marks awarded for each coverage level.
    full_credit: float = 1.0
    partial_credit: float = 0.5
    # Scores are rounded to this step (0.5 marks).
    round_to: float = 0.5
    # Two rubric items whose descriptions are this similar are treated as
    # "similar concepts": one sentence cannot earn both.
    similar_concept_threshold: float = 0.80
    # Two answer sentences this similar are treated as repetition.
    duplicate_sentence_threshold: float = 0.92
    # Concept scores within this distance of a threshold are "ambiguous".
    ambiguity_margin: float = 0.04
    # Answers with fewer content words are flagged as very short.
    short_answer_words: int = 8
    fuzzy_ratio: float = 0.84
    extra_abbreviations: dict[str, str] = field(default_factory=dict)

    @classmethod
    def for_backend(cls, backend: str, model_name: str = DEFAULT_MODEL, **overrides) -> "EvaluationConfig":
        th = DEFAULT_THRESHOLDS.get(backend, DEFAULT_THRESHOLDS["embedding"])
        base = cls(
            backend=backend,
            model_name=model_name if backend == "embedding" else "tfidf-char-ngrams",
            match_threshold=th.match,
            partial_threshold=th.partial,
            off_topic_threshold=th.off_topic,
            relevance_threshold=th.relevance,
            holistic_high_threshold=th.holistic_high,
            keyword_weight=DEFAULT_KEYWORD_WEIGHT.get(backend, 0.3),
            debias_weight=DEFAULT_DEBIAS_WEIGHT if backend == "embedding" else 0.0,
            hybrid_weight=DEFAULT_HYBRID_WEIGHT if backend == "embedding" else 0.0,
            token_recall_weight=DEFAULT_TOKEN_RECALL_WEIGHT if backend == "embedding" else 0.0,
            correctness_checks=DEFAULT_CORRECTNESS_CHECKS,
            keyword_list_predicate_cues=DEFAULT_KEYWORD_LIST_PREDICATE_CUES,
            adaptive_debias=DEFAULT_ADAPTIVE_DEBIAS if backend == "embedding" else False,
            antonym_check=DEFAULT_ANTONYM_CHECK,
            echo_guard=DEFAULT_ECHO_GUARD,
            echo_expanded_topic=DEFAULT_ECHO_EXPANDED_TOPIC,
            attribute_swap_check=DEFAULT_ATTRIBUTE_SWAP_CHECK,
            antonym_contrast_exemption=DEFAULT_ANTONYM_CONTRAST_EXEMPTION,
            use_sentence_pairs=DEFAULT_USE_PAIRS.get(backend, True),
        )
        return base.with_overrides(**overrides)

    def with_overrides(self, **overrides) -> "EvaluationConfig":
        clean = {k: v for k, v in overrides.items() if v is not None and k in self.__dataclass_fields__}
        cfg = replace(self, **clean)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not (0.0 <= self.partial_threshold <= self.match_threshold <= 1.0):
            raise ValueError("Thresholds must satisfy 0 <= partial <= match <= 1")
        if not (0.0 <= self.partial_credit <= self.full_credit <= 1.0):
            raise ValueError("Credits must satisfy 0 <= partial_credit <= full_credit <= 1")
        if self.round_to <= 0:
            raise ValueError("round_to must be positive")

    def to_dict(self) -> dict:
        return asdict(self)

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
