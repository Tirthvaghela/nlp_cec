"""Structured rubric model and validation.

A question is represented by a :class:`QuestionSpec` containing rubric items.
Each rubric item is one required concept / key point with its own marks.
``prepare_question`` validates and repairs common problems (missing rubric,
marks that do not add up, empty descriptions) and reports what it changed as
warnings, so the evaluation can be flagged for teacher review instead of
silently producing a misleading score.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field

from app.nlp import preprocessing as pp


class RubricError(ValueError):
    """The question cannot be evaluated automatically (no rubric and no reference)."""


@dataclass
class RubricItem:
    id: str
    label: str
    description: str
    marks: float
    keywords: list[str] = field(default_factory=list)


@dataclass
class QuestionSpec:
    id: str
    text: str
    max_marks: float
    reference_answer: str = ""
    rubric: list[RubricItem] = field(default_factory=list)
    # Optional per-question overrides of EvaluationConfig (e.g. match_threshold).
    settings: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "QuestionSpec":
        items = [
            RubricItem(
                id=str(i.get("id") or f"c{n + 1}"),
                label=str(i.get("label") or "").strip(),
                description=str(i.get("description") or "").strip(),
                marks=float(i.get("marks") or 0),
                keywords=[str(k).strip() for k in (i.get("keywords") or []) if str(k).strip()],
            )
            for n, i in enumerate(d.get("rubric") or [])
        ]
        return cls(
            id=str(d.get("id") or ""),
            text=str(d.get("text") or ""),
            max_marks=float(d.get("max_marks") or 0),
            reference_answer=str(d.get("reference_answer") or ""),
            rubric=items,
            settings=dict(d.get("settings") or {}),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RubricWarning:
    code: str
    message: str


def round_to_step(value: float, step: float) -> float:
    return math.floor(value / step + 0.5 + 1e-9) * step


def rubric_fingerprint(spec: QuestionSpec) -> str:
    payload = json.dumps(
        {
            "text": spec.text,
            "max_marks": spec.max_marks,
            "reference_answer": spec.reference_answer,
            "rubric": [asdict(i) for i in spec.rubric],
            "settings": spec.settings,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def prepare_question(spec: QuestionSpec, round_step: float = 0.5) -> tuple[QuestionSpec, list[RubricWarning]]:
    """Validate a question and return a usable copy plus warnings."""
    warnings: list[RubricWarning] = []
    if spec.max_marks <= 0:
        raise RubricError("Question maximum marks must be greater than zero.")

    items: list[RubricItem] = []
    for item in spec.rubric:
        label = item.label or item.description[:60]
        desc = item.description or item.label
        if not desc.strip():
            warnings.append(RubricWarning("rubric_item_empty", f"Rubric item '{item.id}' has no text and was ignored."))
            continue
        if item.marks <= 0:
            warnings.append(RubricWarning("rubric_item_no_marks", f"Rubric item '{label}' has no marks and was ignored."))
            continue
        items.append(RubricItem(item.id, label.strip(), desc.strip(), float(item.marks), list(item.keywords)))

    # Normalised duplicate concepts (same stemmed content words) are merged.
    seen: dict[str, RubricItem] = {}
    unique: list[RubricItem] = []
    for item in items:
        key = pp.normalize_concept(item.description)
        if key and key in seen:
            warnings.append(
                RubricWarning("duplicate_rubric_item", f"Rubric item '{item.label}' duplicates '{seen[key].label}'; it was merged.")
            )
            seen[key].marks += item.marks
            continue
        seen[key] = item
        unique.append(item)
    items = unique

    if not items:
        if not spec.reference_answer.strip():
            raise RubricError("This question has neither a rubric nor a reference answer, so it cannot be evaluated automatically.")
        items = _derive_rubric_from_reference(spec.reference_answer, spec.max_marks, round_step)
        warnings.append(
            RubricWarning(
                "auto_derived_rubric",
                "No valid rubric was defined; key points were derived from the reference answer. Review carefully.",
            )
        )

    total = sum(i.marks for i in items)
    if abs(total - spec.max_marks) > 1e-6:
        factor = spec.max_marks / total
        for i in items:
            i.marks = round(i.marks * factor, 4)
        warnings.append(
            RubricWarning(
                "rubric_marks_scaled",
                f"Rubric marks ({total:g}) did not add up to the maximum ({spec.max_marks:g}); they were scaled proportionally.",
            )
        )

    return QuestionSpec(spec.id, spec.text, spec.max_marks, spec.reference_answer, items, dict(spec.settings)), warnings


def _derive_rubric_from_reference(reference: str, max_marks: float, step: float) -> list[RubricItem]:
    sentences = [s.text for s in pp.segment_sentences(pp.normalize_text(reference))]
    n = max(1, min(len(sentences), int(max_marks / step) if max_marks >= step else 1, 6))
    # Merge sentences into n roughly equal groups.
    groups: list[list[str]] = [[] for _ in range(n)]
    for idx, s in enumerate(sentences):
        groups[min(n - 1, idx * n // max(1, len(sentences)))].append(s)
    per = max_marks / n
    return [
        RubricItem(id=f"auto{k + 1}", label=f"Key point {k + 1}", description=" ".join(g), marks=per)
        for k, g in enumerate(groups)
        if g
    ]
