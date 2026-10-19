"""Drafting aids for question authoring: a reference answer for a question, and a rubric for a question + reference.

Drafts are suggestions for the teacher. Nothing here is stored or used for scoring: the teacher edits the draft and
saves the question through the normal question endpoints, which apply the usual validation.

* Reference answers are drafted through Groq's chat-completions API (official ``groq`` SDK) with the model in
  ``Settings.generation_model`` (GENERATION_MODEL). The key comes from ``Settings.groq_api_key`` (GROQ_API_KEY, read from
  the environment or backend/.env); it is passed to the SDK explicitly, never logged and never returned. Without a key,
  :class:`GenerationUnavailable` is raised and the API answers 503 - no answer is ever invented locally.
* Rubrics are drafted by the same model when it is available. Otherwise (no key, or the classroom pilot, where no
  question content may leave the server) they are derived locally from the reference answer's sentences, the same
  derivation the engine already uses for questions without a rubric (``nlp.rubric``), and labelled as such.

Every rubric returned - model or derived - satisfies the question schema: 1-12 criteria, unique labels, descriptions of
3-600 characters, marks in steps of 0.5 adding up exactly to the question's maximum. A model rubric that does not is
reported as an error rather than silently repaired into a different rubric.
"""

from __future__ import annotations

import json
import logging
import re

from app.config import get_settings
from app.nlp import preprocessing as pp

log = logging.getLogger(__name__)

REFERENCE_MAX_CHARS = 5000  # QuestionIn.reference_answer
MAX_CRITERIA = 12  # QuestionIn.rubric
REQUEST_TIMEOUT_S = 45.0
MAX_RETRIES = 1  # the SDK retries connection errors, 408/409/429 and 5xx once - bounded, never indefinitely

# Error codes returned by the API (routers/generation.py). "generation_unavailable" is a configuration problem that
# retrying cannot fix; the frontend stops drafting automatically after it.
NOT_CONFIGURED = "generation_unavailable"
RATE_LIMITED = "generation_rate_limited"
TEMPORARY = "generation_temporarily_unavailable"

_NOT_SET_UP = "Drafting is not set up on this server (GROQ_API_KEY is not configured)."


class GenerationUnavailable(Exception):
    """Drafting cannot run: not configured, rejected configuration, or the provider is busy or unreachable."""

    def __init__(self, message: str, code: str = NOT_CONFIGURED):
        super().__init__(message)
        self.code = code


class GenerationFailed(Exception):
    """The model answered, but the draft cannot be used (empty, truncated, malformed or invalid)."""


def _client():
    key = get_settings().groq_api_key.get_secret_value().strip()
    if not key or key == "your_groq_api_key_here":  # empty, or the placeholder copied from .env.example
        raise GenerationUnavailable(_NOT_SET_UP)
    try:
        import groq
    except ImportError as exc:  # dependency missing from the environment
        raise GenerationUnavailable("Drafting is not set up on this server (the groq package is not installed).") from exc
    return groq, groq.Groq(api_key=key, timeout=REQUEST_TIMEOUT_S, max_retries=MAX_RETRIES)


def _error_code(exc) -> str:
    """Provider error code from the response body (e.g. "model_not_found"), without exposing the body itself."""
    body = getattr(exc, "body", None)
    err = body.get("error", body) if isinstance(body, dict) else None
    code = err.get("code") if isinstance(err, dict) else None
    return str(code or "")


def _call(messages: list[dict], max_tokens: int, json_mode: bool = False) -> tuple[str, str]:
    """One chat-completions request, with the SDK's typed errors mapped onto safe, provider-neutral outcomes.
    Only the error class, status and provider error code are logged - never the key, headers or request content."""
    groq, client = _client()
    model = get_settings().generation_model
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=max_tokens,
            temperature=0.3,
            **({"response_format": {"type": "json_object"}} if json_mode else {}),
        )
    except groq.AuthenticationError as exc:
        log.warning("Groq rejected the API key (401).")
        raise GenerationUnavailable("Drafting is not set up correctly on this server (the Groq API key was rejected).") from exc
    except groq.PermissionDeniedError as exc:
        log.warning("Groq denied access (403, code=%s).", _error_code(exc))
        raise GenerationUnavailable("Drafting is not set up correctly on this server (the Groq account cannot use this model).") from exc
    except groq.RateLimitError as exc:
        log.info("Groq rate limit or quota reached (429).")
        raise GenerationUnavailable("The drafting service's rate limit or quota has been reached. Try again in a minute.", RATE_LIMITED) from exc
    except groq.APITimeoutError as exc:
        log.info("Groq request timed out.")
        raise GenerationUnavailable("The drafting service did not answer in time. Try again.", TEMPORARY) from exc
    except groq.APIConnectionError as exc:
        log.info("Groq could not be reached (%s).", type(exc).__name__)
        raise GenerationUnavailable("The drafting service could not be reached. Check the server's internet connection.", TEMPORARY) from exc
    except groq.APIStatusError as exc:
        code = _error_code(exc)
        log.warning("Groq request failed: %s (status=%s, code=%s).", type(exc).__name__, exc.status_code, code)
        if exc.status_code >= 500:
            raise GenerationUnavailable("The drafting service had a temporary problem. Try again.", TEMPORARY) from exc
        if exc.status_code == 404 or "model" in code:
            raise GenerationUnavailable(
                f"Drafting is not set up correctly on this server (GENERATION_MODEL '{model}' is not available on Groq).") from exc
        if code == "json_validate_failed":
            raise GenerationFailed("The drafted rubric could not be read. Try again, or add criteria yourself.") from exc
        raise GenerationFailed("The drafting service rejected the request.") from exc
    try:
        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        finish = choice.finish_reason
        served_by = str(response.model or model)
    except (AttributeError, IndexError, TypeError) as exc:
        log.warning("Groq returned an unexpected response structure.")
        raise GenerationFailed("The drafting service returned an unexpected response. Try again.") from exc
    if finish == "length":
        raise GenerationFailed("The draft was too long and was cut off. Try again, or shorten the question.")
    if not text:
        raise GenerationFailed("The drafting service returned an empty draft. Try again.")
    return text, served_by


_FENCE = re.compile(r"^```[a-zA-Z]*\s*\n(.*?)\n?```\s*$", re.S)


def _unfence(text: str) -> str:
    """Some models wrap the whole reply in a code fence; the stored text must not contain one."""
    m = _FENCE.match(text.strip())
    return m.group(1).strip() if m else text.strip()


# --- reference answer ---------------------------------------------------------------------------------------------

_REFERENCE_SYSTEM = """You write model answers that teachers use as the reference answer when marking students' \
descriptive (written) exam answers.

Write the answer a strong student would give, scaled to the marks available: roughly one distinct, checkable point per \
mark, stated plainly and accurately. Cover what the question asks and nothing more. Do not address the teacher, do not \
restate the question, and do not add a title or any preamble.

Format the answer in this limited Markdown only: paragraphs separated by a blank line, "- " bullet lists, "1. " \
numbered lists, **bold**, *italic*, "### " subheadings, and simple pipe tables (header row, then a | --- | separator \
row) when the question asks for a comparison. No other Markdown, HTML, links, images or code blocks. Stay under 3500 \
characters."""


def draft_reference_answer(question: str, max_marks: float) -> tuple[str, str]:
    """Return (reference answer in the Margin Markdown subset, model id)."""
    text, model = _call(
        [{"role": "system", "content": _REFERENCE_SYSTEM},
         {"role": "user", "content": f"Question ({max_marks:g} marks):\n\n{question}"}],
        max_tokens=4000,
    )
    text = _unfence(text)
    if not text:
        raise GenerationFailed("The drafting service returned an empty draft. Try again.")
    if len(text) > REFERENCE_MAX_CHARS:
        raise GenerationFailed("The drafted answer is longer than a reference answer may be. Try again.")
    return text, model


# --- rubric -------------------------------------------------------------------------------------------------------

_RUBRIC_SYSTEM = """You turn an exam question and its reference answer into a marking rubric for descriptive answers.

Each criterion is one key point a good answer must contain. An automatic matcher compares each criterion's description \
with the sentences of a student's answer, so write every description as a plain, self-contained statement of the point \
(for example "Tokenization splits text into smaller units such as words or subwords"), not as an instruction to the \
marker. Labels are short names (2-6 words) and must be unique. Marks are multiples of 0.5, greater than zero, and must \
add up exactly to the question's maximum marks. Use between 1 and 6 criteria; never more criteria than half-marks \
available. Do not add criteria that the reference answer does not support.

Reply with JSON only, in exactly this shape:
{"criteria": [{"label": "...", "description": "...", "marks": 1.5}]}"""


def rubric_problem(criteria: list[dict], max_marks: float) -> str | None:
    """Why ``criteria`` cannot be saved as this question's rubric (None = valid), mirroring QuestionIn validation."""
    if not 1 <= len(criteria) <= MAX_CRITERIA:
        return f"The rubric must have between 1 and {MAX_CRITERIA} criteria."
    labels = []
    for n, c in enumerate(criteria, 1):
        label, desc, marks = c.get("label", ""), c.get("description", ""), c.get("marks")
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 120:
            return f"Criterion {n} needs a label of 1-120 characters."
        if not isinstance(desc, str) or not 3 <= len(desc.strip()) <= 600:
            return f"Criterion {n} needs a description of 3-600 characters."
        if not isinstance(marks, (int, float)) or marks <= 0 or abs(marks * 2 - round(marks * 2)) > 1e-9:
            return f"Criterion {n} must be worth a positive number of marks in steps of 0.5."
        labels.append(label.strip().lower())
    if len(set(labels)) != len(labels):
        return "Criterion labels must be unique."
    total = sum(float(c["marks"]) for c in criteria)
    if abs(total - max_marks) > 1e-6:
        return f"The criteria add up to {total:g} marks, but the question is worth {max_marks:g}."
    return None


def draft_rubric_with_model(question: str, max_marks: float, reference: str) -> tuple[list[dict], str]:
    text, model = _call(
        [{"role": "system", "content": _RUBRIC_SYSTEM},
         {"role": "user", "content": f"Question ({max_marks:g} marks):\n\n{question}\n\nReference answer:\n\n{reference}"}],
        max_tokens=4000,
        json_mode=True,
    )
    try:
        criteria = [{"label": str(c["label"]).strip(), "description": str(c["description"]).strip(), "marks": c["marks"]}
                    for c in json.loads(_unfence(text))["criteria"]]
    except (ValueError, KeyError, TypeError) as exc:
        raise GenerationFailed("The drafted rubric could not be read. Try again.") from exc
    problem = rubric_problem(criteria, max_marks)
    if problem:
        raise GenerationFailed(f"The drafted rubric is not valid: {problem} Try again, or add criteria yourself.")
    return criteria, model


_MD_MARKS = re.compile(r"(\*\*|__|(?<!\w)[*_](?=\S)|(?<=\S)[*_](?!\w)|^#{1,6}\s+|^\s*\|?\s*:?-{3,}.*$)", re.M)


def plain_text(markdown: str) -> str:
    """The Margin Markdown subset as plain text: emphasis markers, heading hashes, table rules and pipes removed."""
    text = _MD_MARKS.sub("", markdown)
    text = re.sub(r"\s*\|\s*", " ", text)
    return re.sub(r"\\([\\*_#|\-.])", r"\1", text)


def _split_half_marks(max_marks: float, n: int) -> list[float]:
    """n positive multiples of 0.5 adding up to max_marks, as equal as possible (largest first)."""
    units = int(round(max_marks * 2))
    base, extra = divmod(units, n)
    return [(base + (1 if k < extra else 0)) / 2 for k in range(n)]


def _label_for(n: int, description: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9][\w'-]*", description)][:5]
    return f"Key point {n}: {' '.join(words)}"[:120] if words else f"Key point {n}"


def derive_rubric(max_marks: float, reference: str) -> list[dict]:
    """Deterministic rubric from the reference answer's sentences (no model involved)."""
    sentences = [s.text for s in pp.segment_sentences(pp.normalize_text(plain_text(reference)))]
    units = int(round(max_marks * 2))
    if not sentences or units < 1:
        raise GenerationFailed("The reference answer has no sentences to build a rubric from.")
    n = max(1, min(len(sentences), units, 6))
    groups: list[list[str]] = [[] for _ in range(n)]
    for idx, s in enumerate(sentences):
        groups[min(n - 1, idx * n // len(sentences))].append(s)
    criteria = []
    for k, (group, marks) in enumerate(zip(groups, _split_half_marks(max_marks, n)), 1):
        desc = " ".join(group)
        if len(desc) > 600:  # keep whole sentences within the schema limit
            kept = []
            for s in group:
                if len(" ".join(kept + [s])) > 600:
                    break
                kept.append(s)
            desc = " ".join(kept) or desc[:600].rsplit(" ", 1)[0]
        criteria.append({"label": _label_for(k, desc), "description": desc, "marks": marks})
    problem = rubric_problem(criteria, max_marks)
    if problem:  # e.g. sentences too short to describe a point
        raise GenerationFailed(f"A rubric could not be derived from this reference answer: {problem}")
    return criteria
