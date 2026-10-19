"""Integrity of the evaluation history (final quality audit). No engine runs, no held-out scoring."""

import json
import sys

import numpy as np
import pytest

from app.nlp import EvaluationConfig
from evaluation import common
from evaluation.stats import bootstrap_ci, paired_difference_ci


def test_locked_sets_still_match_their_recorded_hashes():
    assert len(list(common.iter_answers(common.load_final_set(), "final"))) == 48
    assert len(list(common.iter_answers(common.load_v4_fresh_set(), "v4_fresh"))) == 64


def test_every_historical_result_file_exists():
    missing = [n for n in common.HISTORICAL_RESULTS if not (common.RESULTS_DIR / n).exists()]
    assert not missing, f"historical result files missing: {missing}"


def test_historical_results_are_never_overwritten():
    for name in ("v4_dev_experiments.json", "evaluation_embedding_v4_fresh_v4.md"):
        path = common.result_path(name)
        assert path.name != name and path.name.endswith(("_rerun.json", "_rerun.md"))
    assert common.result_path("brand_new_report.json").name == "brand_new_report.json"


@pytest.mark.parametrize("flag", ["--v4-fresh", "--final"])
def test_spent_held_out_sets_need_historical_rerun(monkeypatch, flag):
    from evaluation import evaluate

    monkeypatch.setattr(sys, "argv", ["evaluate", flag])
    with pytest.raises(SystemExit) as exc:
        evaluate.main()
    assert "historical-rerun" in str(exc.value)


def test_held_out_answers_never_appear_in_dev_data():
    dev = {" ".join(a["text"].lower().split()) for _, a in common.iter_answers(common.load_dataset(), "all")}
    for loader, split in ((common.load_final_set, "final"), (common.load_v4_fresh_set, "v4_fresh")):
        held = {" ".join(a["text"].lower().split()) for _, a in common.iter_answers(loader(), split)}
        assert not (dev & held) - {""}  # every set has an intentional empty answer


def test_historical_profiles_pin_later_features_off():
    v3 = EvaluationConfig.for_backend("embedding", **common.V3_PROFILE)
    assert v3.correctness_checks and not (v3.echo_guard or v3.antonym_check or v3.keyword_list_predicate_cues
                                          or v3.echo_expanded_topic or v3.attribute_swap_check)
    v40 = EvaluationConfig.for_backend("embedding", **common.V40_PROFILE)
    assert v40.echo_guard and v40.antonym_check and v40.keyword_list_predicate_cues
    assert not (v40.echo_expanded_topic or v40.attribute_swap_check or v40.antonym_contrast_exemption)
    v2 = EvaluationConfig.for_backend("embedding", **common.V2_PROFILE)
    assert not v2.correctness_checks


def test_archived_v4_fresh_numbers_are_what_the_readme_reports():
    rep = json.loads((common.RESULTS_DIR / "evaluation_embedding_v4_fresh_v4.json").read_text(encoding="utf-8"))
    cmp_ = json.loads((common.RESULTS_DIR / "v4_fresh_comparison_with_v3.json").read_text(encoding="utf-8"))["systems"]
    assert rep["engine_version"] == "4.0.0" and rep["n_answers"] == 64
    assert round(rep["engine"]["scores"]["mae"], 3) == 0.547 and rep["engine"]["scores"]["within_1_0"] == 0.875
    assert round(cmp_["v3 configuration"]["mae"], 3) == 0.562 and cmp_["v3 configuration"]["within_1_0"] == 0.875
    assert round(rep["baselines"]["keyword_overlap"]["mae"], 3) == 0.961


def test_bootstrap_statistics():
    gold = np.array([2, 3, 1, 4, 2, 0, 3, 1.5])
    clusters = ["a", "a", "b", "b", "c", "c", "d", "d"]
    perfect = bootstrap_ci(gold, gold, [4] * 8, clusters, n_boot=200)
    assert perfect["mae"]["estimate"] == 0 and perfect["mae"]["ci"] == [0.0, 0.0] and perfect["within_1"]["estimate"] == 1
    off = bootstrap_ci(gold + 1, gold, [4] * 8, clusters, n_boot=200)
    assert off["mae"]["estimate"] == pytest.approx(1.0) and off["normalised_mae"]["estimate"] == pytest.approx(0.25)
    d = paired_difference_ci(gold, gold + 1, gold, clusters, n_boot=200)
    assert d["mae_difference"] == pytest.approx(-1.0) and d["ci_excludes_zero"]
    same = paired_difference_ci(gold + 0.5, gold + 0.5, gold, clusters, n_boot=200)
    assert same["mae_difference"] == 0 and not same["ci_excludes_zero"]
