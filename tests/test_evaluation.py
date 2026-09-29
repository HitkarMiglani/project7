"""Tests for Phase 6 evaluation harness (Stages 6.2-6.4). Offline only."""

from src.evaluation import (
    compare_metrics,
    compute_ats_density,
    compute_fabrication_rate,
    compute_keyword_match_rate,
    compute_knapsack_utilization,
    compute_metrics,
    evaluate_texts,
    results_frame,
    save_report,
)


def _reqs():
    return [
        {"skill": "Python", "category": "required", "importance": 1.0},
        {"skill": "Docker", "category": "required", "importance": 0.8},
        {"skill": "GraphQL", "category": "nice_to_have", "importance": 0.5},
    ]


def _feedback():
    return {
        "weakest_section": "experience",
        "reasoning": "x",
        "sections": {
            "experience": {
                "matched": 1, "total": 2, "missing": ["Docker"],
                "coverage": 0.5, "reasoning": "r", "utility": 1.0,
            },
            "skills": {
                "matched": 2, "total": 2, "missing": [],
                "coverage": 1.0, "reasoning": "r", "utility": 2.0,
            },
        },
    }


def test_keyword_match_rate_union_across_sections():
    # Docker missing in experience but covered in skills -> matched anywhere.
    assert compute_keyword_match_rate(_feedback(), _reqs()) == 1.0
    fb = {"sections": {"experience": {
        "matched": 0, "total": 2, "missing": ["Python", "Docker"],
        "coverage": 0.0, "reasoning": "r", "utility": 0.0}}}
    assert compute_keyword_match_rate(fb, _reqs()) == 0.0


def test_ats_density_mentions_and_bounds():
    text = "Python developer with Docker experience. " + "filler " * 180
    d = compute_ats_density(text, _reqs())
    assert 0.0 < d <= 1.0
    assert compute_ats_density("", _reqs()) == 0.0
    assert compute_ats_density(text, []) == 0.0


def test_fabrication_rate():
    assert compute_fabrication_rate(claim_counts={"verified": 2, "inferred": 1, "unsupported": 1}) == 0.25
    assert compute_fabrication_rate(claim_counts={"verified": 0, "inferred": 0, "unsupported": 0}) == 0.0
    assert compute_fabrication_rate([{"state": "unsupported"}]) == 1.0


def test_knapsack_utilization():
    alloc = {"sections": {
        "experience": {"total_weight": 750, "capacity": 1500},
        "skills": {"total_weight": 250, "capacity": 500},
    }}
    assert compute_knapsack_utilization(alloc) == 0.5
    assert compute_knapsack_utilization({"sections": {}}) == 0.0


def test_evaluate_texts_knap_wins_on_fabrication():
    alloc = {"sections": {"experience": {"total_weight": 750, "capacity": 1500}}}
    fb, reqs = _feedback(), _reqs()
    base_text = "I invented 10x Kubernetes magic with zero evidence."
    knap_text = "Built Python services with Docker packaging."
    out = evaluate_texts(
        base_text, knap_text, alloc, fb, reqs,
        baseline_verified=[{"state": "unsupported"}, {"state": "unsupported"}],
        knap_verified=[{"state": "verified"}, {"state": "verified"}],
    )
    assert out["baseline"]["fabrication_rate"] == 1.0
    assert out["knapresume"]["fabrication_rate"] == 0.0
    assert out["wins"]["fabrication_rate"] is True
    assert out["baseline"]["knapsack_utilization"] == 0.0
    assert out["knapresume"]["knapsack_utilization"] == 0.5


def test_compare_metrics_directions():
    cmp = compare_metrics(
        {"keyword_match_rate": 0.5, "ats_density": 0.5, "fabrication_rate": 0.8, "knapsack_utilization": 0.0},
        {"keyword_match_rate": 0.7, "ats_density": 0.4, "fabrication_rate": 0.2, "knapsack_utilization": 0.6},
    )
    assert cmp["wins"]["keyword_match_rate"] is True
    assert cmp["wins"]["ats_density"] is False
    assert cmp["wins"]["fabrication_rate"] is True
    assert cmp["knap_wins"] == 3


def test_save_report_artifacts(tmp_path):
    alloc = {"sections": {"experience": {"total_weight": 750, "capacity": 1500}}}
    fb, reqs = _feedback(), _reqs()
    res = evaluate_texts(
        "baseline words here", "Python Docker tailoring here",
        alloc, fb, reqs,
        baseline_claim_counts={"verified": 1, "inferred": 0, "unsupported": 1},
        knap_claim_counts={"verified": 2, "inferred": 0, "unsupported": 0},
    )
    res = {"label": "pair-1", "profile_id": 1, "jd_id": 1, **res}
    paths = save_report([res], tmp_path)
    import os

    assert os.path.exists(paths["report_md"])
    assert os.path.exists(paths["results_csv"])
    assert os.path.exists(paths["chart_png"])
    frame = results_frame([res])
    assert len(frame) == 2  # baseline + knapresume rows
    assert set(frame["arm"]) == {"baseline", "knapresume"}
