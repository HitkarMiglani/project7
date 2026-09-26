"""
tests/test_allocator.py
Stage 3.2 — 0/1 Knapsack DP Allocator (Stage 3.4 will extend with further
proofs; this file pins optimality via brute force plus edge cases).

Covers global-optimality vs exhaustive search, mandatory pinning (even
over capacity), explicit weights, empty/zero-capacity/oversize edges,
determinism, and allocate_facts section grouping.
"""

import itertools
import random

import pytest

from src.allocator import (
    allocate_facts,
    allocate_section,
    item_utility,
    item_weight,
)


def _opt(content, utility, mandatory=False, weight=None):
    item = {"section": "experience", "content": content,
            "utility": utility, "is_mandatory": mandatory}
    if weight is not None:
        item["weight"] = weight
    return item


def _brute_force(values, weights, capacity):
    best, best_set = 0.0, set()
    for r in range(len(values) + 1):
        for combo in itertools.combinations(range(len(values)), r):
            if sum(weights[i] for i in combo) <= capacity:
                total = sum(values[i] for i in combo)
                if total > best:
                    best, best_set = total, set(combo)
    return best, best_set


# ── Optimality ───────────────────────────────────────────────────────────────

def test_dp_matches_brute_force_fixed_case():
    # Textbook greedy-by-ratio failure (capacity 6): greedy picks A
    # (ratio 2.25) then nothing fits -> 9; optimum is B + C = 12.
    items = [_opt("a" * 4, 9.0, weight=4),
             _opt("b" * 3, 6.0, weight=3),
             _opt("c" * 3, 6.0, weight=3)]
    result = allocate_section(items, 6)
    assert result["total_utility"] == pytest.approx(12.0)
    assert result["total_weight"] <= 6
    best, _ = _brute_force([9.0, 6.0, 6.0], [4, 3, 3], 6)
    assert result["total_utility"] == pytest.approx(best)


def test_dp_matches_brute_force_fuzz():
    rng = random.Random(42)
    for trial in range(30):
        n = rng.randint(1, 10)
        values = [round(rng.uniform(0, 10), 2) for _ in range(n)]
        weights = [rng.randint(1, 12) for _ in range(n)]
        capacity = rng.randint(0, 25)
        items = [_opt("x" * w, v, weight=w)
                 for v, w in zip(values, weights)]
        result = allocate_section(items, capacity)
        best, _ = _brute_force(values, weights, capacity)
        assert result["total_utility"] == pytest.approx(best), f"trial {trial}"
        assert result["total_weight"] <= capacity


# ── Mandatory pinning ────────────────────────────────────────────────────────

def test_mandatory_always_selected():
    items = [_opt("Staff Engineer | Acme", 0.1, mandatory=True),
             _opt("Did great things " * 20, 0.9),
             _opt("Did more things " * 20, 0.8)]
    result = allocate_section(items, 100)
    assert result["selected"][0]["is_mandatory"] is True
    assert all(f["is_mandatory"] is False for f in result["dropped"])


def test_mandatory_kept_even_over_capacity():
    items = [_opt("Long mandatory heading " * 10, 0.1, mandatory=True),
             _opt("bullet", 0.9)]
    result = allocate_section(items, 5)
    assert any(f["is_mandatory"] for f in result["selected"])
    assert result["dropped"] == [items[1]] or result["selected"] == [items[0]]


# ── Weights & edges ──────────────────────────────────────────────────────────

def test_explicit_weight_overrides_content_length():
    item = _opt("short", 1.0, weight=1000)
    assert item_weight(item) == 1000
    assert item_weight({"content": "abcde"}) == 5
    assert item_utility({"utility": -3.0}) == 0.0


def test_empty_items():
    result = allocate_section([], 100)
    assert result["selected"] == [] and result["dropped"] == []
    assert result["total_utility"] == 0.0


def test_zero_capacity_keeps_only_mandatory():
    items = [_opt("Head", 0.5, mandatory=True), _opt("bullet", 0.9)]
    result = allocate_section(items, 0)
    assert [f["content"] for f in result["selected"]] == ["Head"]
    assert [f["content"] for f in result["dropped"]] == ["bullet"]


def test_oversize_optional_fact_dropped():
    items = [_opt("huge bullet " * 100, 0.99)]
    result = allocate_section(items, 10)
    assert result["selected"] == [] and len(result["dropped"]) == 1


def test_negative_capacity_raises():
    with pytest.raises(ValueError):
        allocate_section([_opt("x", 1.0)], -1)


def test_deterministic_repeated_runs():
    items = [_opt(f"bullet {i} " * 5, float(i % 7)) for i in range(15)]
    first = allocate_section(items, 200)
    second = allocate_section(items, 200)
    assert ([f["content"] for f in first["selected"]]
            == [f["content"] for f in second["selected"]])


# ── allocate_facts grouping ──────────────────────────────────────────────────

def test_allocate_facts_groups_and_applies_capacities():
    items = [
        {"section": "experience", "content": "E" * 100, "utility": 0.9},
        {"section": "experience", "content": "e" * 100, "utility": 0.1},
        {"section": "skills", "content": "Python, Docker", "utility": 0.8},
        {"content": "orphan fact", "utility": 0.5},
    ]
    result = allocate_facts(items, capacities={"experience": 100})
    assert set(result.keys()) == {"experience", "skills", "other"}
    exp = result["experience"]
    assert len(exp["selected"]) == 1
    assert exp["selected"][0]["utility"] == 0.9
    assert result["skills"]["selected"][0]["content"] == "Python, Docker"


def test_allocate_facts_empty():
    assert allocate_facts([]) == {}


# ── Stage 3.4 — remaining edges ──────────────────────────────────────────────

def test_all_mandatory_section_skips_dp():
    items = [_opt("Name", 0.1, mandatory=True),
             _opt("Degree | MIT", 0.2, mandatory=True)]
    result = allocate_section(items, 10)
    assert len(result["selected"]) == 2 and result["dropped"] == []


def test_exact_capacity_boundary_selects_all():
    items = [_opt("a" * 10, 1.0, weight=10), _opt("b" * 10, 2.0, weight=10)]
    result = allocate_section(items, 20)
    assert len(result["selected"]) == 2
    assert result["total_weight"] == 20


def test_multiple_oversize_facts_all_dropped():
    items = [_opt("x" * 50, 0.9), _opt("y" * 60, 0.8)]
    result = allocate_section(items, 10)
    assert result["selected"] == [] and len(result["dropped"]) == 2


def test_allocate_facts_absent_section_capacity_ignored():
    items = [{"section": "skills", "content": "Python", "utility": 0.9}]
    result = allocate_facts(items, capacities={"experience": 5})
    assert list(result.keys()) == ["skills"]
    assert len(result["skills"]["selected"]) == 1


def test_mandatory_weight_reported():
    items = [_opt("Head", 0.3, mandatory=True), _opt("bullet", 0.9)]
    result = allocate_section(items, 1000)
    assert result["mandatory_weight"] == len("Head")
    assert result["capacity"] == 1000
