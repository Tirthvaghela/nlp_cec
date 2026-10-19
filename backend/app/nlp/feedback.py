"""Evidence-based feedback generation.

Feedback is assembled only from the evaluation evidence: the rubric concepts,
their coverage level, and quotes taken verbatim from the student's answer. It
never claims the student wrote something that is not in the answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.nlp.scorer import ConceptResult, Flag


def _quote(text: str, limit: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _lower_first(text: str) -> str:
    text = text.strip().rstrip(".")
    first = text.split(" ", 1)[0]
    # Keep acronyms such as "TF-IDF" or "NER" as written.
    if len(first) > 1 and first.isupper():
        return text
    return text[:1].lower() + text[1:]


def build_feedback(concepts: list["ConceptResult"], flags: list["Flag"], score: float, max_marks: float,
                   empty: bool = False) -> dict:
    matched = [c for c in concepts if c.level == "matched"]
    partial = [c for c in concepts if c.level == "partial"]
    missing = [c for c in concepts if c.level == "missing"]

    if empty:
        summary = f"No answer was submitted, so 0/{max_marks:g} marks were suggested."
    else:
        summary = (
            f"Suggested score {score:g}/{max_marks:g}. "
            f"{len(matched)} of {len(concepts)} key concept(s) fully addressed"
            + (f", {len(partial)} partly addressed" if partial else "")
            + (f", {len(missing)} missing." if missing else ".")
        )

    strengths = [
        f"{c.label}: addressed - “{_quote(c.evidence.text)}”" for c in matched if c.evidence
    ]
    partly = [
        f"{c.label}: touched on in “{_quote(c.evidence.text)}”, but the explanation is incomplete."
        for c in partial
        if c.evidence
    ]
    gaps = [f"{c.label} ({c.marks:g} mark{'s' if c.marks != 1 else ''}): not found in your answer." for c in missing]

    suggestions: list[str] = []
    for c in sorted(missing + partial, key=lambda c: -c.marks):
        verb = "Explain" if c.level == "missing" else "Develop further"
        suggestions.append(f"{verb}: {_lower_first(c.description)}.")
    for c in concepts:
        if getattr(c, "issue", None) in ("misattributed", "reversed_comparison"):
            suggestions.insert(0, f"Check {c.label}: make sure you have not mixed up the terms being compared.")
        elif getattr(c, "issue", None) in ("negated", "antonym"):
            suggestions.insert(0, f"Check {c.label}: your answer seems to state the opposite of the expected point.")
    codes = {f.code for f in flags}
    if "very_short_answer" in codes and not empty:
        suggestions.append("Write a fuller answer: define the idea, explain how it works and give an example.")
    if "repeated_content" in codes:
        suggestions.append("Avoid repeating the same sentence; each sentence should add a new point.")
    if "low_relevance" in codes or "off_topic" in codes:
        suggestions.append("Stay focused on what the question asks; unrelated material does not earn marks.")
    if empty:
        suggestions.append("Attempt every question - even a short definition can earn partial marks.")
    if not suggestions and not empty:
        suggestions.append("Well done. To strengthen the answer further, add a concrete example for each point.")

    text_parts = [summary]
    if strengths:
        text_parts.append("Strengths: " + " ".join(f"{c.label} is addressed." for c in matched))
    if partial:
        text_parts.append("Needs more detail: " + ", ".join(c.label for c in partial) + ".")
    if missing:
        text_parts.append("Missing: " + ", ".join(c.label for c in missing) + ".")
    text_parts.append("Next time: " + " ".join(suggestions[:3]))

    return {
        "summary": summary,
        "strengths": strengths,
        "partial": partly,
        "missing": gaps,
        "suggestions": suggestions,
        "text": "\n".join(text_parts),
    }
