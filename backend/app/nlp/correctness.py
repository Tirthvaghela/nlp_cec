"""Lightweight correctness safeguards (rule-based, no extra model).

Embedding similarity measures *topic*, not *truth*. These checks catch three
specific, common ways a similar-looking sentence can be wrong. They are derived
automatically from the question and rubric wording - nothing is hard-coded per
question - and they are deliberately conservative: when a check fires, the
evaluation is flagged for teacher review.

1. Misattribution (swapped definitions). For "compare X and Y" questions the
   rubric concepts are about different *entities* (stemming vs lemmatization,
   TCP vs UDP). A concept's entity is a question term among the first three
   content words of its description. A sentence that names another concept's
   entity but not this concept's own entity is not evidence for this concept
   ("Stemming uses a dictionary ..." cannot prove "Lemmatization uses a dictionary").

2. Reversed comparison. A concept such as "Lemmatization is more accurate than
   stemming" is a claim (entity, attribute, direction). A sentence claiming the
   same attribute for the other entity, or the opposite direction for the same
   entity, contradicts it ("stemming is more accurate").

3. Added negation. If the concept is a positive statement and the evidence
   sentence states it with a negation ("Tokenization is not the first step") while
   sharing the concept's wording, the evidence is downgraded one level and flagged.
   Only this direction is checked: a negated concept is often paraphrased without
   a negation ("should not be removed" -> "must be kept").

Limitations: no parsing or real inference - pronouns, double negatives, sarcasm or
factual errors that keep the right entities and polarity are not detected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.nlp import preprocessing as pp

_NEGATIONS = {"not", "never", "cannot", "without", "neither", "nor", "none", "nothing", "no"}
_QUOTED = re.compile(r"'[^']{1,40}'|\"[^\"]{1,40}\"|‘[^’]{1,40}’|“[^”]{1,40}”")
# comparative word -> (attribute, direction). Antonyms share an attribute with opposite direction.
_COMPARATIVES = {
    "faster": ("fast", 1), "quicker": ("fast", 1), "slower": ("fast", -1),
    "better": ("good", 1), "worse": ("good", -1),
    "higher": ("high", 1), "lower": ("high", -1),
    "larger": ("large", 1), "bigger": ("large", 1), "smaller": ("large", -1),
    "cheaper": ("cheap", 1), "simpler": ("simple", 1),
}
_SCOPE_BREAK = {"than", "to", "from", "over"}


def term_set(text: str) -> set[str]:
    """Stems of content words, also splitting hyphenated words ("one-hot" -> "hot")."""
    out: set[str] = set()
    for w in pp.content_words(text):
        out.add(pp.stem(w))
        for part in w.split("-"):
            if part and part not in pp.STOP_WORDS and len(part) > 2:
                out.add(pp.stem(part))
    return out


def has_negation(text: str) -> bool:
    """Negation cue outside quotes ('the word "not"' is a mention, not a negation)."""
    t = _QUOTED.sub(" ", text.lower())
    t = re.sub(r"\bno\.", " ", t)  # "no. of times"
    for w in re.findall(r"[a-z]+(?:'[a-z]+)?", t):
        if w in _NEGATIONS or w.endswith("n't"):
            return True
    return False


@dataclass
class ConceptEntities:
    own: set[str]
    foreign: set[str]


def concept_entities(question_text: str, descriptions: list[str]) -> list[ConceptEntities]:
    q_terms = term_set(question_text)
    subjects = []
    for d in descriptions:
        first = []
        for w in pp.content_words(d):
            first.append(w)
            if len(first) == 3:
                break
        subjects.append(term_set(" ".join(first)) & q_terms)
    everyone = set.intersection(*subjects) if subjects else set()
    subjects = [s - everyone for s in subjects]
    # Concepts whose subjects overlap describe the same entity ("one-hot encoding" /
    # "one-hot vectors"): merge them into one entity group.
    groups: list[set[str]] = []
    for s in subjects:
        if not s:
            continue
        merged = [g for g in groups if g & s]
        new = set(s).union(*merged) if merged else set(s)
        groups = [g for g in groups if not (g & s)] + [new]
    out = []
    for i, d in enumerate(descriptions):
        own = next((g for g in groups if g & subjects[i]), set())
        others = set().union(*(g for g in groups if g is not own)) if len(groups) > 1 else set()
        out.append(ConceptEntities(own=set(own), foreign=others - own - term_set(d)))
    return out


def misattributed(ent: ConceptEntities, unit_terms: set[str]) -> bool:
    return bool(ent.own) and bool(ent.foreign & unit_terms) and not (ent.own & unit_terms)


def _claims(text: str, entities: set[str]) -> list[tuple[str, str, int]]:
    """(entity, attribute, direction) triples for comparatives in ``text``."""
    toks = [w.lower() for w in re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)*", text)]
    stems = [pp.stem(t) for t in toks]
    claims = []
    for k, tok in enumerate(toks):
        if tok in ("more", "less") and k + 1 < len(toks):
            attr, direction = pp.stem(toks[k + 1]), (1 if tok == "more" else -1)
        elif tok in _COMPARATIVES:
            attr, direction = _COMPARATIVES[tok]
        else:
            continue
        subject = None
        for b in range(k - 1, -1, -1):  # nearest entity before the comparative, skipping "than X"
            if stems[b] in entities and not (b > 0 and toks[b - 1] in _SCOPE_BREAK):
                subject = stems[b]
                break
        if subject:
            claims.append((subject, attr, direction))
    return claims


def reversed_comparison(concept: str, unit: str, entities: set[str]) -> bool:
    c_claims = _claims(concept, entities)
    if not c_claims:
        return False
    for ue, ua, ud in _claims(unit, entities):
        for ce, ca, cd in c_claims:
            if ua != ca:
                continue
            same_entity = ue == ce
            if (same_entity and ud != cd) or (not same_entity and ud == cd):
                return True
    return False


# Words that already carry a negation inside the concept ("light-independent", "connectionless",
# "unlabelled"): their correct paraphrases often use "not"/"no", so the check is skipped.
_IMPLICIT_NEGATIVE = re.compile(
    r"\b(?:non-?\w+|\w+less|independent|invalid|incorrect|impossible|"
    r"un(?:labell?ed|supervised|seen|known|related|ordered|reliable|able|structured))\b", re.I)


def added_negation(concept: str, unit: str, overlap: float, min_overlap: float = 0.25) -> bool:
    if has_negation(concept) or _IMPLICIT_NEGATIVE.search(concept):
        return False
    return has_negation(unit) and overlap >= min_overlap


def mask_entities(text: str, entity_terms: set[str]) -> str:
    """Replace entity names with "this" so similarity reflects what is *said*, not *who* it is about."""
    return re.sub(r"[A-Za-z]+(?:-[A-Za-z]+)*",
                  lambda m: "this" if term_set(m.group(0)) & entity_terms else m.group(0), text)


# General-purpose antonym pairs (not domain-specific). Stems are compared.
_ANTONYM_PAIRS = [
    # Comparatives (faster/slower, higher/lower, ...) are deliberately absent: whether "X is faster" contradicts
    # "Y is slower" depends on the subject, which reversed_comparison() checks with entities.
    ("high", "low"), ("highest", "lowest"), ("increase", "decrease"), ("rare", "common"),
    ("many", "few"), ("fast", "slow"), ("dense", "sparse"), ("before", "after"),
    ("first", "last"), ("minimise", "maximise"), ("minimize", "maximize"), ("absorb", "release"), ("add", "remove"),
    ("identical", "different"), ("same", "different"), ("correct", "incorrect"), ("true", "false"),
    ("strong", "weak"), ("large", "small"), ("long", "short"), ("start", "end"),
    ("input", "output"), ("accurate", "inaccurate"), ("reliable", "unreliable"), ("always", "never"),
    ("labelled", "unlabelled"), ("labeled", "unlabeled"), ("supervised", "unsupervised"), ("connection-oriented", "connectionless"),
    ("cheap", "expensive"), ("simple", "complex"), ("easy", "hard"), ("all", "none"),
]
_ANTONYM = {}
for _a, _b in _ANTONYM_PAIRS:
    _ANTONYM.setdefault(pp.stem(_a), set()).add(pp.stem(_b))
    _ANTONYM.setdefault(pp.stem(_b), set()).add(pp.stem(_a))


def _stems(text: str) -> set[str]:
    return {pp.stem(w) for w in pp.words(text)}


def is_contrast(concept: str) -> bool:
    """The concept itself contains both members of an antonym pair ("common words get a LOW weight while
    distinctive words get a HIGH weight"): it contrasts two things."""
    c = _stems(concept)
    return any(anti in c for w in c for anti in _ANTONYM.get(w, ()))


def antonym_flip(concept: str, unit: str, overlap: float, min_overlap: float = 1 / 3,
                 exempt_contrast: bool = False) -> bool:
    """The unit replaces a word of the concept with its antonym ("low weight" -> "highest weight")
    while sharing the rest of the concept's wording. Pairs where the concept itself already
    contains both members ("low ... while ... high") are ignored.

    v4.1 (``exempt_contrast``): in a contrast concept a correct answer describes both sides, so an antonym of
    one side's word may describe the other side ("frequent words ... whereas RARE distinctive words" for
    "COMMON words ... while distinctive words"). Such concepts are left to swapped_attributes()."""
    if overlap < min_overlap or (exempt_contrast and is_contrast(concept)):
        return False
    c, u = _stems(concept), _stems(unit)
    for w in c:
        for anti in _ANTONYM.get(w, ()):
            if anti in u and w not in u and anti not in c:
                return True
    return False


def _content_stems(text: str) -> list[str]:
    return [pp.stem(w) for w in pp.words(_QUOTED.sub(" ", text)) if w not in pp.STOP_WORDS]


def _attribute_anchors(stems: list[str], a: str, b: str) -> dict[str, set[str]]:
    """For a text containing antonyms ``a`` and ``b`` once each: the content words that belong to
    each one - the words before the first member, and the words between the two members, each
    minus the words the other segment also contains (so a word next to both is not an anchor)."""
    pa, pb = stems.index(a), stems.index(b)
    first, second = (a, b) if pa < pb else (b, a)
    lo, hi = min(pa, pb), max(pa, pb)
    seg1, seg2 = set(stems[:lo]), set(stems[lo + 1 : hi])
    return {first: seg1 - seg2, second: seg2 - seg1}


def swapped_attributes(concept: str, unit: str, overlap: float, min_overlap: float = 1 / 3) -> bool:
    """v4.1: a concept that contains *both* members of an antonym pair ("common words get a LOW
    weight while distinctive words get a HIGH weight") and a unit that attaches each member to the
    other member's words ("common words get a high weight ... distinctive words a low weight").

    Conservative: each antonym must occur exactly once in both texts, each member must have anchor
    words in both texts, and the exchange must be mutual (each member's unit anchors overlap the
    other member's concept anchors and not its own). Attribute-first wording ("a high weight goes
    to ...") has no anchors before the first member and is therefore never flagged."""
    if overlap < min_overlap:
        return False
    cs, us = _content_stems(concept), _content_stems(unit)
    shared = set(cs) & set(us)
    for a, antis in _ANTONYM.items():
        for b in antis:
            if a > b or any(s.count(x) != 1 for s in (cs, us) for x in (a, b)):
                continue
            ca = {k: v & shared for k, v in _attribute_anchors(cs, a, b).items()}
            ua = {k: v & shared for k, v in _attribute_anchors(us, a, b).items()}
            if all(ua[x] & ca[y] and not ua[x] & ca[x] for x, y in ((a, b), (b, a))):
                return True
    return False


# Words that add no explanatory content of their own (stems are compared).
_GENERIC = {pp.stem(w) for w in (
    "concept thing things way important process type kind part example method technique idea topic field "
    "give gives make makes use uses used help helps get gets").split()}


_RELATION = re.compile(r"[=\u00d7*<>]|->|\u2192|\b[a-z0-9]+\s+x\s+[a-z0-9]+\b", re.I)
_EXAMPLE_MARKER = re.compile(r"\b(?:like|such as|e\.g\.?|for example|including)\s+([^.;:!?]+)")


def echo_only(original_text: str, question_text: str, min_new_terms: int = 2, expand_topic: bool = False,
              extra_abbreviations: dict[str, str] | None = None) -> bool:
    """True if a sentence adds fewer than ``min_new_terms`` content words beyond the question's own
    topic words - it names or restates the topic ("Tokenization is important in NLP", "TF-IDF gives
    weights to words") without explaining anything. Uses the student's original wording, so
    abbreviation expansions inserted by preprocessing do not count as the student's content.

    v4.1 (``expand_topic``): the long forms of abbreviations in the question also count as topic
    words, so spelling out the name ("TF-IDF stands for term frequency inverse document frequency")
    is a restatement, not an explanation."""
    if _RELATION.search(original_text):  # "TF-IDF = TF x IDF" states a relation between the terms
        return False
    topic = pp.expand_abbreviations(question_text, extra_abbreviations) if expand_topic else question_text
    new = term_set(original_text) - term_set(topic) - _GENERIC
    # Words given as examples are the student's content even when they are function words
    # ("stop words are words like the, a, an, is").
    q_words = set(pp.words(question_text))
    for m in _EXAMPLE_MARKER.finditer(original_text.lower()):
        new |= {w for w in pp.words(m.group(1)) if w not in q_words}
    return len(new) < min_new_terms


def swapped_units(combined, ents: list[ConceptEntities], unit_terms: list[set[str]], margin: float = 0.03) -> list[set[int]]:
    """Units whose *content* best matches a concept of one entity while they *name* another.

    ``combined`` must be computed on entity-masked texts (``mask_entities``); otherwise the
    entity name itself dominates the embedding and every sentence looks like its own entity.

    Returns, for each unit j, the set of concept indices that must not use unit j: all
    concepts of the entity the unit names (and the content-matched concept itself is
    already excluded by ``misattributed``). Threshold-independent: only the ranking of
    concept scores inside the unit is used.
    """
    n_concepts, n_units = combined.shape
    out: list[set[int]] = [set() for _ in range(n_units)]
    candidates: list[tuple[int, int, set[int], float]] = []  # (unit, content concept, named concepts, margin)
    for j in range(n_units):
        best = int(combined[:, j].argmax())
        if not misattributed(ents[best], unit_terms[j]):
            continue
        named = {i for i in range(n_concepts) if ents[i].own & unit_terms[j]}
        if not named:
            continue
        gap = float(combined[best, j] - max(combined[i, j] for i in named))
        if gap > margin:
            candidates.append((j, best, named, gap))
    # Embeddings confuse antonymous descriptions ("dense vector" vs "sparse vector"), so a single
    # misattributed clause is not trusted on its own. Only a *mutual* exchange of properties
    # between two entities (the typical swapped-definition answer) counts as a swap.
    for j, best, named, _gap in candidates:
        if any(b2 in named and best in n2 for j2, b2, n2, _ in candidates if j2 != j):
            out[j].update(named)
    return out
