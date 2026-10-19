"""Token-level, concept-directed coverage ("BERTScore recall", Zhang et al. 2020).

Sentence cosine answers "are these two texts about the same thing?". For grading we
need "does the answer contain what this rubric concept says?". This module answers
the second question with contextual token embeddings from the same MiniLM model:

    recall(concept, unit) = sum_t w_t * max_u cos(e_t, e_u) / sum_t w_t

over the concept's tokens t and the unit's tokens u. Weights w_t:
  * 0    for special tokens, punctuation and stop words,
  * ``topic_weight`` (e.g. 0.3) for tokens of words that merely repeat the question's
    topic (so "tokenization" alone does not satisfy "tokenization splits text ..."),
  * 1    for concept-specific words.

Because the score is directed from the concept to the answer, a short answer that
states the concept's specific content scores well even when its sentence embedding
is dominated by the topic - the failure mode of v2's topic debiasing.
"""

from __future__ import annotations

import numpy as np

from app.nlp import preprocessing as pp


def _word_at(text: str, start: int, end: int) -> str:
    s, e = start, end
    while s > 0 and text[s - 1].isalnum():
        s -= 1
    while e < len(text) and text[e].isalnum():
        e += 1
    return text[s:e].lower()


def concept_token_weights(text: str, offsets: list[tuple[int, int]], topic_stems: set[str], topic_weight: float) -> np.ndarray:
    weights = np.zeros(len(offsets))
    for n, (a, b) in enumerate(offsets):
        if a == b:  # special token
            continue
        word = _word_at(text, a, b)
        if not word or not word[0].isalnum() or word in pp.STOP_WORDS:
            continue
        stems = {pp.stem(part) for part in word.split("-") if part}
        weights[n] = topic_weight if stems & topic_stems else 1.0
    return weights


def recall_matrix(backend, concepts: list[str], units: list[str], topic_stems: set[str], topic_weight: float) -> np.ndarray:
    """recall[i, j] = coverage of concept i's specific tokens by unit j (0..1)."""
    out = np.zeros((len(concepts), len(units)))
    unit_tok = [backend.token_embeddings(u) for u in units]
    unit_tok = [emb[[a != b for a, b in offs]] for offs, emb in unit_tok]  # drop special tokens
    for i, c in enumerate(concepts):
        offs, emb = backend.token_embeddings(c)
        w = concept_token_weights(c, offs, topic_stems, topic_weight)
        if w.sum() == 0:
            w = np.array([0.0 if a == b else 1.0 for a, b in offs])
        if w.sum() == 0:
            continue
        for j, ue in enumerate(unit_tok):
            if len(ue) == 0:
                continue
            best = (emb @ ue.T).max(axis=1)
            out[i, j] = float(np.clip((w * best).sum() / w.sum(), 0.0, 1.0))
    return out
