"""Rubric-aware, explainable answer scoring.

Pipeline for one (question, answer) pair::

    validate rubric  ->  segment answer into sentence units (original offsets kept)
    -> normalise / spelling-correct / expand abbreviations (copy used for NLP only)
    -> drop repeated sentences  ->  add adjacent-sentence windows
    -> for each rubric concept and each unit:
           semantic  s = max cosine(concept representations, unit)
           lexical   k = keyword / key-term coverage of the unit (fuzzy, stemmed)
           combined  c = s + w * k * (1 - s)        (keywords can only help)
    -> assign best evidence per concept, never letting one sentence earn two
       *similar* concepts
    -> level: matched (c >= match) | partial (c >= partial) | missing
    -> marks: item.marks * credit(level), rounded, total clamped to max_marks
    -> holistic similarity to the reference answer as an independent cross-check
    -> review flags + confidence + evidence-based feedback

Nothing here is random: identical inputs + config + model give identical output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from app.nlp import correctness as cx
from app.nlp import preprocessing as pp
from app.nlp.alignment import recall_matrix
from app.nlp.config import ENGINE_VERSION, EvaluationConfig
from app.nlp.feedback import build_feedback
from app.nlp.rubric import QuestionSpec, RubricWarning, prepare_question, round_to_step, rubric_fingerprint
from app.nlp.similarity import SimilarityBackend, TfidfBackend, get_backend

MATCHED, PARTIAL, MISSING = "matched", "partial", "missing"
_NEGATION_MIN_OVERLAP = 1 / 3
_SPARSE = TfidfBackend()
_STRONG_REVIEW_CODES = {"divergent_signals", "fallback_backend", "auto_derived_rubric", "off_topic",
                        "possible_swap", "possible_contradiction"}
_ISSUE_NOTES = {
    "misattributed": "The closest sentence seems to describe a different term than this concept, so it was not credited.",
    "reversed_comparison": "The closest sentence states this comparison the other way round, so it was not credited.",
    "negated": "The closest sentence appears to state the opposite of this concept (negation), so credit was reduced.",
    "echo": "The closest sentence only names or restates the question's topic without explaining it, so it was not credited.",
    "antonym": "The closest sentence uses the opposite of a key word in this concept (e.g. low/high), so credit was reduced.",
}
_SWAPPED_ATTRIBUTES_NOTE = ("The closest sentence seems to attach the opposite properties to the two things this concept "
                            "contrasts (e.g. high/low swapped), so credit was reduced.")


@dataclass
class Evidence:
    text: str
    start: int
    end: int


@dataclass
class ConceptResult:
    id: str
    label: str
    description: str
    marks: float
    level: str
    awarded: float
    combined_score: float
    semantic_score: float
    lexical_score: float
    evidence: Evidence | None
    matched_terms: list[str]
    ambiguous: bool
    reason: str
    note: str | None = None
    keyword_list_evidence: bool = False
    recall_score: float = 0.0
    # v3 correctness safeguard that affected this concept: misattributed | reversed_comparison | negated
    issue: str | None = None


@dataclass
class Flag:
    code: str
    severity: str  # "info" | "review"
    message: str


@dataclass
class EvaluationResult:
    question_id: str
    max_marks: float
    suggested_score: float
    raw_score: float
    concepts: list[ConceptResult]
    holistic_similarity: float | None
    relevance_ratio: float | None
    word_count: int
    flags: list[Flag]
    confidence: str  # "high" | "medium" | "low"
    needs_review: bool
    feedback: dict
    corrections: list[dict]
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _Unit:
    text: str  # original text (for display)
    prepared: str  # normalised text used by the models
    start: int
    end: int
    sentences: frozenset[int]
    is_list: bool = False  # a bare list of keywords, not an explanation


def evaluate_answer(
    question: QuestionSpec | dict,
    answer: str | None,
    config: EvaluationConfig | None = None,
    backend: SimilarityBackend | None = None,
) -> EvaluationResult:
    """Score ``answer`` against ``question``'s rubric. See module docstring."""
    spec = question if isinstance(question, QuestionSpec) else QuestionSpec.from_dict(question)
    backend = backend or get_backend()
    if config is None:
        config = EvaluationConfig.for_backend(backend.name)
    if spec.settings:
        config = config.with_overrides(**spec.settings)

    original_fp = rubric_fingerprint(spec)
    spec, rubric_warnings = prepare_question(spec, config.round_to)
    flags: list[Flag] = [_rubric_flag(w) for w in rubric_warnings]
    if backend.name != "embedding":
        flags.append(
            Flag("fallback_backend", "review",
                 "Scored with the TF-IDF fallback (no sentence-embedding model); synonyms may be missed.")
        )

    metadata = {
        "engine_version": ENGINE_VERSION,
        "backend": backend.name,
        "model_name": backend.model_name,
        "fallback_reason": backend.fallback_reason,
        "config": config.to_dict(),
        "config_fingerprint": config.fingerprint(),
        "rubric_fingerprint": original_fp,
    }

    answer = answer or ""
    vocabulary = pp.build_vocabulary(
        spec.text, spec.reference_answer,
        *(f"{i.label} {i.description} {' '.join(i.keywords)}" for i in spec.rubric),
    )

    units, sentence_units, n_repeated, corrections = _build_units(answer, vocabulary, config, backend)
    word_count = len(pp.words(answer))

    if not sentence_units:
        concepts = [
            ConceptResult(i.id, i.label, i.description, round(i.marks, 2), MISSING, 0.0, 0.0, 0.0, 0.0, None, [], False,
                          "No answer was written for this concept.")
            for i in spec.rubric
        ]
        flags.insert(0, Flag("empty_answer", "info", "No answer was submitted; no marks can be awarded."))
        confidence = _confidence(flags)
        return EvaluationResult(
            spec.id, spec.max_marks, 0.0, 0.0, concepts, None, None, word_count, flags, confidence,
            confidence != "high", build_feedback(concepts, flags, 0.0, spec.max_marks, empty=True), [], metadata,
        )

    items = spec.rubric
    unit_texts = [u.prepared for u in units]

    # --- semantic similarity: max over two representations of each concept ---------
    reps: list[str] = []
    rep_owner: list[int] = []
    for idx, item in enumerate(items):
        desc = pp.prepare_for_embedding(item.description, None, config.extra_abbreviations)[0]
        for r in {desc, f"{item.label}: {desc}"}:
            reps.append(r)
            rep_owner.append(idx)
    topic = [pp.normalize_text(spec.text)] if spec.text.strip() else None
    raw_rep = backend.similarity(reps, unit_texts)
    deb_rep = backend.similarity(reps, unit_texts, remove=topic) if (topic and config.debias_weight > 0) else raw_rep
    alpha = config.debias_weight
    if topic and config.debias_weight > 0 and config.adaptive_debias:
        q = np.clip(backend.similarity(reps, topic)[:, 0], 0.0, 1.0)
        alpha = (config.debias_weight * np.sqrt(1.0 - q ** 2))[:, None]
    rep_sim = (1.0 - alpha) * raw_rep + alpha * deb_rep
    if config.hybrid_weight > 0 and backend.name == "embedding":
        sparse = _SPARSE.similarity(reps, unit_texts)
        rep_sim = (1.0 - config.hybrid_weight) * rep_sim + config.hybrid_weight * sparse
    sem = np.full((len(items), len(units)), -1.0)
    raw_sem = np.full((len(items), len(units)), -1.0)
    for r_idx, owner in enumerate(rep_owner):
        sem[owner] = np.maximum(sem[owner], rep_sim[r_idx])
        raw_sem[owner] = np.maximum(raw_sem[owner], raw_rep[r_idx])
    sem = np.clip(sem, 0.0, 1.0)
    raw_sem = np.clip(raw_sem, 0.0, 1.0)

    # --- v3: token-level, concept-directed recall ---------------------------------
    recall = np.zeros_like(sem)
    if config.token_recall_weight > 0 and hasattr(backend, "token_embeddings"):
        concept_texts = [pp.prepare_for_embedding(i.description, None, config.extra_abbreviations)[0] for i in items]
        recall = recall_matrix(backend, concept_texts, unit_texts, set(pp.key_terms(spec.text)), config.topic_token_weight)
        sem = (1.0 - config.token_recall_weight) * sem + config.token_recall_weight * recall

    # --- lexical evidence ----------------------------------------------------------
    # Terms that only repeat the question's topic are not evidence for a specific
    # concept (consistent with the topic-debiased semantic signal).
    topic_terms = set(pp.key_terms(spec.text))
    unit_terms = [{pp.stem(w) for w in pp.content_words(u.prepared)} for u in units]
    lex = np.zeros_like(sem)
    lex_terms: list[list[list[str]]] = []
    for i, item in enumerate(items):
        all_terms = pp.key_terms(f"{item.label} {item.description}")
        terms = [t for t in all_terms if t not in topic_terms] or all_terms
        row_terms = []
        for j, ut in enumerate(unit_terms):
            cov, hits = pp.term_coverage(terms, ut, config.fuzzy_ratio)
            if item.keywords:
                kw_hits = [k for k in item.keywords if pp.phrase_present(k, ut, config.fuzzy_ratio)]
                cov = 0.5 * cov + 0.5 * (1.0 if kw_hits else 0.0)
                hits = hits + [f"keyword:{k}" for k in kw_hits]
            lex[i, j] = cov
            row_terms.append(hits)
        lex_terms.append(row_terms)

    combined = sem + config.keyword_weight * lex * (1.0 - sem)

    # --- v3: correctness safeguards (evidence that must not be credited) ------------
    bad: dict[tuple[int, int], str] = {}
    if config.echo_guard:
        for j, u in enumerate(units):
            if cx.echo_only(u.text, spec.text, expand_topic=config.echo_expanded_topic,
                            extra_abbreviations=config.extra_abbreviations):
                for i in range(len(items)):
                    bad[(i, j)] = "echo"
    if config.correctness_checks and len(items) > 1:
        ents = cx.concept_entities(spec.text, [i.description for i in items])
        entity_terms = set().union(*(e.own | e.foreign for e in ents))
        uterms = [cx.term_set(u.prepared) for u in units]
        for i, item in enumerate(items):
            for j, u in enumerate(units):
                if cx.misattributed(ents[i], uterms[j]):
                    bad[(i, j)] = "misattributed"
                elif entity_terms and cx.reversed_comparison(item.description, u.prepared, entity_terms):
                    bad[(i, j)] = "reversed_comparison"
        # Swapped statements: content of one entity's concept attributed to another entity.
        # The rejection also covers any larger unit containing the swapped one.
        masked = backend.similarity([cx.mask_entities(i.description, entity_terms) for i in items],
                                    [cx.mask_entities(u.prepared, entity_terms) for u in units]) if entity_terms else None
        swaps = cx.swapped_units(masked, ents, uterms) if masked is not None else [set() for _ in units]
        for j, concepts_blocked in enumerate(swaps):
            for k, u in enumerate(units):
                if u.start <= units[j].start and units[j].end <= u.end:
                    for i in concepts_blocked:
                        bad.setdefault((i, k), "misattributed")

    # --- similar concepts must not be credited twice from the same sentence --------
    desc_texts = [pp.normalize_text(i.description) for i in items]
    concept_sim = backend.similarity(desc_texts, desc_texts) if len(items) > 1 else np.ones((1, 1))
    similar = concept_sim >= config.similar_concept_threshold
    if len(items) > 1:
        pairs = [(items[a].label, items[b].label) for a in range(len(items)) for b in range(a + 1, len(items)) if similar[a, b]]
        if pairs:
            names = "; ".join(f"'{x}' / '{y}'" for x, y in pairs[:3])
            flags.append(Flag("similar_concepts", "info",
                              f"Some rubric concepts are very similar ({names}); one sentence cannot earn both."))

    order = sorted(range(len(items)), key=lambda i: -float(combined[i].max()))
    used_by: dict[int, list[int]] = {}  # sentence index -> concept indices using it as evidence
    chosen: dict[int, tuple[int | None, str | None]] = {}
    rejected: dict[int, tuple[str, float]] = {}  # concept -> (issue, score of the rejected evidence)
    for i in order:
        ranked = sorted(range(len(units)), key=lambda j: (-combined[i, j], len(units[j].sentences)))
        note = None
        pick = None
        for j in ranked:
            if (i, j) in bad:
                rejected.setdefault(i, (bad[(i, j)], float(combined[i, j])))
                continue
            blockers = {c for s in units[j].sentences for c in used_by.get(s, []) if similar[i, c] and c != i}
            if not blockers:
                pick = j
                break
            if note is None:
                note = (f"The best matching sentence was already credited to the similar concept "
                        f"'{items[next(iter(blockers))].label}', so it was not counted twice.")
        if pick is not None:
            for s in units[pick].sentences:
                used_by.setdefault(s, []).append(i)
        chosen[i] = (pick, note)

    # --- levels and marks ----------------------------------------------------------
    concepts: list[ConceptResult] = []
    for i, item in enumerate(items):
        j, note = chosen[i]
        c = float(combined[i, j]) if j is not None else 0.0
        s = float(sem[i, j]) if j is not None else 0.0
        k = float(lex[i, j]) if j is not None else 0.0
        if c >= config.match_threshold:
            level, credit = MATCHED, config.full_credit
        elif c >= config.partial_threshold:
            level, credit = PARTIAL, config.partial_credit
        else:
            level, credit = MISSING, 0.0
        issue = None
        if j is not None and level != MISSING and units[j].is_list:
            level, credit = (PARTIAL, config.partial_credit) if level == MATCHED else (MISSING, 0.0)
            note = "The supporting text is only a list of keywords without explanation, so credit was reduced."
        elif j is not None and level != MISSING and config.correctness_checks and _negated(item, units[j]):
            level, credit = (PARTIAL, config.partial_credit) if level == MATCHED else (MISSING, 0.0)
            issue, note = "negated", _ISSUE_NOTES["negated"]
        elif j is not None and level != MISSING and config.antonym_check and _antonym_flip_cfg(item, units[j], config):
            level, credit = (PARTIAL, config.partial_credit) if level == MATCHED else (MISSING, 0.0)
            issue, note = "antonym", _ISSUE_NOTES["antonym"]
        elif j is not None and level != MISSING and config.attribute_swap_check and _swapped_attributes(item, units[j]):
            level, credit = (PARTIAL, config.partial_credit) if level == MATCHED else (MISSING, 0.0)
            issue, note = "antonym", _SWAPPED_ATTRIBUTES_NOTE
        if issue is None and i in rejected and rejected[i][1] >= config.partial_threshold and rejected[i][1] > c:
            issue, note = rejected[i][0], _ISSUE_NOTES[rejected[i][0]]
            if level != MISSING:  # the concept was still earned from another sentence; say so (v4.1 wording fix)
                note += " Another sentence was credited for this concept instead."
        awarded = round_to_step(item.marks * credit, config.round_to) if credit else 0.0
        awarded = min(awarded, item.marks)
        ambiguous = min(abs(c - config.match_threshold), abs(c - config.partial_threshold)) < config.ambiguity_margin
        evidence = Evidence(units[j].text, units[j].start, units[j].end) if (j is not None and level != MISSING) else None
        terms = [t for t in lex_terms[i][j] if not t.startswith("keyword:")] if j is not None else []
        kws = [t.split(":", 1)[1] for t in lex_terms[i][j] if t.startswith("keyword:")] if j is not None else []
        concepts.append(
            ConceptResult(
                id=item.id, label=item.label, description=item.description, marks=round(item.marks, 2),
                level=level, awarded=awarded, combined_score=round(c, 4), semantic_score=round(s, 4),
                lexical_score=round(k, 4), evidence=evidence, matched_terms=kws + terms, ambiguous=ambiguous,
                reason=_reason(level, awarded, item.marks, s, k, config), note=note,
                keyword_list_evidence=bool(j is not None and units[j].is_list),
                recall_score=round(float(recall[i, j]), 4) if j is not None else 0.0, issue=issue,
            )
        )

    raw = sum(c.awarded for c in concepts)
    suggested = max(0.0, min(spec.max_marks, round_to_step(raw, config.round_to)))

    # --- holistic cross-check and relevance -----------------------------------------
    reference = spec.reference_answer.strip() or " ".join(i.description for i in items)
    ref_prepared = pp.prepare_for_embedding(reference, None, config.extra_abbreviations)[0]
    full_prepared = " ".join(u.prepared for u in sentence_units)
    holistic = float(np.clip(backend.similarity([full_prepared], [ref_prepared])[0, 0], 0.0, 1.0))

    ref_sents = [pp.prepare_for_embedding(s.text, None, config.extra_abbreviations)[0]
                 for s in pp.segment_sentences(pp.normalize_text(reference))] or [ref_prepared]
    sent_idx = [k for k, u in enumerate(units) if len(u.sentences) == 1]
    ref_sim = backend.similarity([units[k].prepared for k in sent_idx], ref_sents).max(axis=1)
    # A sentence is "relevant" when it is topically close to the reference or to a concept.
    rel_scores = np.maximum(raw_sem[:, sent_idx].max(axis=0), ref_sim)
    relevance_ratio = float((rel_scores >= config.relevance_threshold).mean()) if sent_idx else 0.0

    flags.extend(_answer_flags(concepts, suggested, spec.max_marks, holistic, relevance_ratio, word_count,
                               n_repeated, corrections, answer, config))
    confidence = _confidence(flags)
    feedback = build_feedback(concepts, flags, suggested, spec.max_marks)
    return EvaluationResult(
        question_id=spec.id, max_marks=spec.max_marks, suggested_score=suggested, raw_score=round(raw, 4),
        concepts=concepts, holistic_similarity=round(holistic, 4), relevance_ratio=round(relevance_ratio, 4),
        word_count=word_count, flags=flags, confidence=confidence, needs_review=confidence != "high",
        feedback=feedback, corrections=[{"original": a, "interpreted_as": b} for a, b in corrections],
        metadata=metadata,
    )


def _build_units(answer: str, vocabulary: set[str], config: EvaluationConfig, backend: SimilarityBackend):
    """Sentence units (deduplicated) plus adjacent two-sentence windows."""
    spans = [part for s in pp.segment_sentences(answer) for part in pp.split_long_span(s)]
    corrections: list[tuple[str, str]] = []
    prepared: list[str] = []
    for sp in spans:
        text, corr = pp.prepare_for_embedding(sp.text, vocabulary, config.extra_abbreviations, config.fuzzy_ratio)
        prepared.append(text)
        corrections.extend(corr)

    # Repetition: exact (after normalisation) and near-duplicate sentences.
    keep: list[int] = []
    seen_norm: set[str] = set()
    for idx, text in enumerate(prepared):
        norm = " ".join(pp.words(text))
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        keep.append(idx)
    if len(keep) > 1:
        sims = backend.similarity([prepared[k] for k in keep], [prepared[k] for k in keep])
        unique: list[int] = []
        for a, k in enumerate(keep):
            if any(sims[a, keep.index(u)] >= config.duplicate_sentence_threshold for u in unique):
                continue
            unique.append(k)
        keep = unique
    n_repeated = len(spans) - len(keep)

    sentence_units = [
        _Unit(spans[k].text, prepared[k], spans[k].start, spans[k].end, frozenset({n}), pp.is_keyword_list(spans[k].text, require_no_predicate=config.keyword_list_predicate_cues))
        for n, k in enumerate(keep)
    ]
    units = list(sentence_units)
    # Clauses of long sentences: one sentence often packs several concepts.
    for n, su in enumerate(sentence_units):
        for cl in pp.split_clauses(pp.Span(su.start, su.end, su.text)):
            text, _ = pp.prepare_for_embedding(cl.text, vocabulary, config.extra_abbreviations, config.fuzzy_ratio)
            units.append(_Unit(cl.text, text, cl.start, cl.end, frozenset({n}), su.is_list))
    for n in range(len(sentence_units) - 1 if config.use_sentence_pairs else 0):
        a, b = sentence_units[n], sentence_units[n + 1]
        units.append(_Unit(answer[a.start : b.end], f"{a.prepared} {b.prepared}", a.start, b.end,
                           frozenset({n, n + 1}), a.is_list and b.is_list))
    uniq_corr = list(dict.fromkeys(corrections))
    return units, sentence_units, n_repeated, uniq_corr


def _negated(item, unit: _Unit) -> bool:
    """Concept stated positively, evidence sentence negated and sharing the concept's wording."""
    concept_terms = cx.term_set(f"{item.label} {item.description}")
    uterms = cx.term_set(unit.prepared)
    if not concept_terms or not uterms:
        return False
    common = len(concept_terms & uterms)
    overlap = max(common / len(concept_terms), common / len(uterms))
    return cx.added_negation(item.description, unit.prepared, overlap, _NEGATION_MIN_OVERLAP)


def _overlap(item, unit: _Unit) -> float:
    concept_terms = cx.term_set(f"{item.label} {item.description}")
    uterms = cx.term_set(unit.prepared)
    if not concept_terms or not uterms:
        return 0.0
    common = len(concept_terms & uterms)
    return max(common / len(concept_terms), common / len(uterms))


def _antonym_flip_cfg(item, unit: _Unit, config: EvaluationConfig) -> bool:
    return cx.antonym_flip(item.description, unit.prepared, _overlap(item, unit), _NEGATION_MIN_OVERLAP,
                           exempt_contrast=config.antonym_contrast_exemption)


def _swapped_attributes(item, unit: _Unit) -> bool:
    return cx.swapped_attributes(item.description, unit.prepared, _overlap(item, unit), _NEGATION_MIN_OVERLAP)


def _reason(level: str, awarded: float, marks: float, s: float, k: float, config: EvaluationConfig) -> str:
    strength = f"semantic match {s:.2f}" + (f", key-term coverage {k:.0%}" if k > 0 else "")
    if level == MATCHED:
        return f"Awarded {awarded:g}/{marks:g}: concept clearly addressed ({strength})."
    if level == PARTIAL:
        return f"Awarded {awarded:g}/{marks:g}: concept only partly addressed ({strength}); full marks need a clearer explanation."
    return f"Awarded 0/{marks:g}: no sentence addressed this concept closely enough (best {strength})."


def _rubric_flag(w: RubricWarning) -> Flag:
    severity = "review" if w.code in {"auto_derived_rubric", "rubric_marks_scaled"} else "info"
    return Flag(w.code, severity, w.message)


def _answer_flags(concepts, suggested, max_marks, holistic, relevance_ratio, word_count, n_repeated,
                  corrections, answer, config) -> list[Flag]:
    flags: list[Flag] = []
    content = len(pp.content_words(answer))
    ratio = suggested / max_marks if max_marks else 0.0
    if content < config.short_answer_words:
        flags.append(Flag("very_short_answer", "review" if suggested > 0 else "info",
                          f"The answer is very short ({word_count} words); automatic matching is less reliable."))
    if holistic < config.off_topic_threshold:
        flags.append(Flag("off_topic", "review" if suggested > 0 else "info",
                          "The answer as a whole has very low similarity to the reference answer."))
    if word_count >= 60 and relevance_ratio < 0.35:
        flags.append(Flag("low_relevance", "info",
                          f"Only {relevance_ratio:.0%} of the sentences relate to the question; unrelated text earns no marks."))
    if n_repeated:
        flags.append(Flag("repeated_content", "info",
                          f"{n_repeated} repeated sentence(s) were ignored; repetition earns no extra marks."))
    ambiguous = [c.label for c in concepts if c.ambiguous]
    if any(c.note and "list of keywords" in c.note for c in concepts):
        flags.append(Flag("keyword_list", "review",
                          "Part of the answer is a bare list of keywords; credit for it was reduced. Please check."))
    swaps = [c.label for c in concepts if c.issue in ("misattributed", "reversed_comparison")]
    if swaps:
        flags.append(Flag("possible_swap", "review",
                          "A sentence may describe a different term or reverse a comparison (possible mix-up) for: "
                          + ", ".join(swaps) + ". Please check."))
    echoes = [c.label for c in concepts if c.issue == "echo"]
    if echoes:
        # v4.1: the echo guard is a heuristic. When it is the reason a concept earned nothing (the rejected sentence
        # would otherwise have earned credit), a teacher must check it - it can reject a short but valid definition.
        withheld = [c.label for c in concepts if c.issue == "echo" and c.level == MISSING]
        flags.append(Flag("restates_question", "review" if withheld else "info",
                          "A sentence only names or restates the question's topic without explaining it; it was not "
                          "used as evidence for: " + ", ".join(echoes) + "."
                          + (" Please check: this rule can also reject a short but valid definition." if withheld else "")))
    negated = [c.label for c in concepts if c.issue in ("negated", "antonym")]
    if negated:
        flags.append(Flag("possible_contradiction", "review",
                          "The answer seems to negate the expected statement for: " + ", ".join(negated) + ". Please check."))
    if ambiguous:
        flags.append(Flag("borderline_concepts", "review",
                          "Close to a threshold, please verify: " + ", ".join(ambiguous) + "."))
    if (ratio >= 0.75 and holistic < config.off_topic_threshold + 0.15) or (
        ratio <= 0.25 and holistic >= config.holistic_high_threshold
    ):
        flags.append(Flag("divergent_signals", "review",
                          f"Rubric score ({ratio:.0%}) and overall similarity to the reference ({holistic:.2f}) disagree."))
    if corrections:
        shown = ", ".join(f"'{a}'->'{b}'" for a, b in corrections[:5])
        flags.append(Flag("spelling_normalised", "info", f"Possible misspellings were interpreted: {shown}."))
    return flags


def _confidence(flags: list[Flag]) -> str:
    review = [f for f in flags if f.severity == "review"]
    if any(f.code in _STRONG_REVIEW_CODES for f in review) or len(review) >= 2:
        return "low"
    if review:
        return "medium"
    return "high"
