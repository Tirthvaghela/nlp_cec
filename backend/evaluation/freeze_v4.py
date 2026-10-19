"""Fit the final thresholds of the selected v4 candidate on ALL dev questions (no test/final data).

Usage (from backend/):  python -m evaluation.freeze_v4
Selected candidate (see results/v4_dev_experiments.json): E5 = v3 + keyword-list predicate cues + antonym check + echo guard.
"""

import numpy as np

from evaluation.calibrate import collect, pick, sweep
from evaluation.common import iter_answers, load_dataset, write_json
from evaluation.experiments import MATCH, PARTIAL, V2

from app.nlp.similarity import EmbeddingBackend

SELECTED = dict(V2, correctness_checks=True, token_recall_weight=0.0, keyword_list_predicate_cues=True,
                adaptive_debias=False, antonym_check=True, echo_guard=True)


def main():
    dev = list(iter_answers(load_dataset(), "dev"))
    d = collect(EmbeddingBackend(), dev, **SELECTED)
    totals, level = sweep(d, MATCH, PARTIAL)
    i, j, mae, sm, acc = pick(totals, level, d, np.ones(len(d["gold"]), dtype=bool), MATCH, PARTIAL)
    folds = {}
    for q in sorted(set(d["qid"])):
        fi, fj, *_ = pick(totals, level, d, d["qid"] != q, MATCH, PARTIAL)
        folds[str(q)] = [float(MATCH[fi]), float(PARTIAL[fj])]
    out = {"selected": SELECTED, "match_threshold": float(MATCH[i]), "partial_threshold": float(PARTIAL[j]),
           "dev_in_sample_mae": mae, "dev_smoothed_mae": sm, "dev_concept_accuracy": acc, "loqo_fold_thresholds": folds}
    write_json("v4_frozen_config.json", out)
    print(out)


if __name__ == "__main__":
    main()
