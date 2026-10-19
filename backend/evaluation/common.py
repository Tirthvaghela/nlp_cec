"""Shared helpers for the calibration and evaluation scripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT.parent
RESULTS_DIR = ROOT / "results"
DATASET = ROOT / "dataset.json"
LEVEL_OF = {"M": "matched", "P": "partial", "X": "missing"}

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def load_dataset(path: Path = DATASET) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    scheme = data["label_scheme"]
    # Sanity check: every human score must equal the sum of its concept labels.
    for q in data["questions"]:
        marks = {c["id"]: c["marks"] for c in q["rubric"]}
        for a in q["answers"]:
            derived = sum(marks[c] * scheme[l] for c, l in a["labels"].items())
            if abs(derived - a["human_score"]) > 1e-9:
                raise ValueError(f"{a['id']}: human_score {a['human_score']} != concept-label sum {derived}")
            if set(a["labels"]) != set(marks):
                raise ValueError(f"{a['id']}: labels do not cover every rubric concept")
    return data


FINAL_SET = ROOT / "final_test.json"
FINAL_HASH = ROOT / "final_test.sha256"


V4_FRESH_SET = ROOT / "v4_fresh_test.json"
V4_FRESH_HASH = ROOT / "v4_fresh_test.sha256"


def _load_locked(path: Path, hash_path: Path) -> dict:
    import hashlib

    raw = path.read_bytes().replace(b"\r\n", b"\n")
    expected = hash_path.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise SystemExit(f"{path.name} was modified after it was locked (sha256 {actual} != {expected}).")
    data = json.loads(raw.decode("utf-8"))
    _check_labels(data)
    return data


def load_v4_fresh_set() -> dict:
    """The v4 fresh held-out set (R1-R8), written before any v4 change; hash-checked."""
    return _load_locked(V4_FRESH_SET, V4_FRESH_HASH)


def load_final_set() -> dict:
    """Load the v3 final held-out set after verifying it is byte-identical to the version
    whose SHA-256 was recorded before engine v3 development started."""
    import hashlib

    # Hash of the content with LF line endings, so the check is independent of CRLF conversion
    # (Windows text-mode writes, git autocrlf). The recorded hash was taken on LF text.
    raw = FINAL_SET.read_bytes().replace(b"\r\n", b"\n")
    expected = FINAL_HASH.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise SystemExit(f"final_test.json was modified after it was locked (sha256 {actual} != {expected}).")
    data = json.loads(raw.decode("utf-8"))
    _check_labels(data)
    return data


def _check_labels(data: dict) -> None:
    scheme = data["label_scheme"]
    for q in data["questions"]:
        marks = {c["id"]: c["marks"] for c in q["rubric"]}
        for a in q["answers"]:
            derived = sum(marks[c] * scheme[l] for c, l in a["labels"].items())
            if abs(derived - a["human_score"]) > 1e-9:
                raise ValueError(f"{a['id']}: human_score {a['human_score']} != concept-label sum {derived}")
            if set(a["labels"]) != set(marks):
                raise ValueError(f"{a['id']}: labels do not cover every rubric concept")


def iter_answers(data: dict, split: str | None = None):
    for q in data["questions"]:
        if split and split != "all" and q["split"] != split:
            continue
        for a in q["answers"]:
            yield q, a


# --- reproducibility of historical configurations ------------------------------------------------
# A recorded experiment stores only the *overrides* it was run with; everything else came from the
# defaults of that time. When a later engine version changes a default, re-running an old script
# silently runs a different configuration. These pins restore what the defaults were:
#   v2 / v3 experiments ran before correctness checks were on by default and before any v4 feature;
#   v4.0 ran before the v4.1 audit fixes.
PRE_V4_FEATURES_OFF = dict(keyword_list_predicate_cues=False, adaptive_debias=False, antonym_check=False,
                           echo_guard=False, echo_expanded_topic=False, attribute_swap_check=False,
                           antonym_contrast_exemption=False)
V41_FEATURES_OFF = dict(echo_expanded_topic=False, attribute_swap_check=False, antonym_contrast_exemption=False)
V2_PROFILE = dict(debias_weight=0.9, keyword_weight=0.15, use_sentence_pairs=False, correctness_checks=False,
                  token_recall_weight=0.0, **PRE_V4_FEATURES_OFF)
V3_PROFILE = dict(V2_PROFILE, correctness_checks=True)
V40_PROFILE = dict(V3_PROFILE, keyword_list_predicate_cues=True, antonym_check=True, echo_guard=True)

# Result files that are historical records. They are never overwritten: a script that would write one
# writes ``<name>_rerun.<ext>`` instead, so a reproduction is always labelled as a historical rerun.
HISTORICAL_RESULTS = frozenset({
    "calibration_tfidf.json",
    "evaluation_embedding_dev.json", "evaluation_embedding_dev.md",
    "evaluation_embedding_dev_v4.json", "evaluation_embedding_dev_v4.md",
    "evaluation_embedding_final.json", "evaluation_embedding_final.md",
    "evaluation_embedding_seen-test.json", "evaluation_embedding_seen-test.md",
    "evaluation_embedding_seen-test_v4.json", "evaluation_embedding_seen-test_v4.md",
    "evaluation_embedding_v4_fresh_v4.json", "evaluation_embedding_v4_fresh_v4.md",
    "evaluation_tfidf_dev.json", "evaluation_tfidf_dev.md",
    "evaluation_tfidf_dev_v4.json", "evaluation_tfidf_dev_v4.md",
    "v1_evaluation_embedding_first_test_run.json", "v1_evaluation_embedding_first_test_run.md",
    "v2_calibration_embedding.json", "v2_calibration_embedding_hybrid_grid.json",
    "v2_evaluation_embedding_preregistered_test.json", "v2_evaluation_embedding_preregistered_test.md",
    "v2_evaluation_embedding_rerun.json", "v2_evaluation_embedding_rerun.md",
    "v2_evaluation_tfidf.json", "v2_evaluation_tfidf.md",
    "v3_dev_experiments.json", "v3_final_comparison_with_v2.json", "v3_frozen_config.json",
    "v4_dev_experiments.json", "v4_fresh_comparison_with_v3.json", "v4_frozen_config.json",
    "v41_dev_experiments.json", "v4_fresh_uncertainty_posthoc.json",
})


def result_path(name: str) -> Path:
    """Where a result called ``name`` is written: never over a historical record."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if name in HISTORICAL_RESULTS and (RESULTS_DIR / name).exists():
        stem, ext = name.rsplit(".", 1)
        print(f"[historical record] results/{name} is kept unchanged; this run is written to {stem}_rerun.{ext}")
        name = f"{stem}_rerun.{ext}"
    return RESULTS_DIR / name


def write_json(name: str, payload: dict) -> Path:
    path = result_path(name)
    path.write_text(json.dumps(payload, indent=2, default=_default), encoding="utf-8")
    return path


def _default(o):
    try:
        import numpy as np

        if isinstance(o, (np.floating, np.integer)):
            return o.item()
    except ImportError:  # pragma: no cover
        pass
    raise TypeError(type(o))
