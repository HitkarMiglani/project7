"""
src/allocator.py
Stage 3.2 — 0/1 Knapsack Dynamic Programming Allocator (pure Python).

Per resume section, selects the optimal fact subset:

    Maximize sum v_i * x_i  subject to  sum w_i * x_i <= W,  x_i in {0, 1}

  - v_i: fact utility from src.scoring.score_facts ("utility" key).
  - w_i: integer weight — len(content) chars by default, overridable per
    item via an explicit "weight" key.
  - W: per-section capacity (chars). Mandatory structural facts
    (is_mandatory=True) are ALWAYS selected — they are pinned, never
    dropped, even if they alone exceed W. Only optional achievement bullets
    compete in the DP over the remaining budget (floored at 0).

Classic iterative 0/1 DP guarantees the global optimum for integer weights;
Stage 3.4 pins this with brute-force proof tests. Pure + deterministic:
no models, no DB access.
"""

from typing import Any, Dict, List, Optional

from src.logger import get_logger

logger = get_logger("allocator")

DEFAULT_SECTION_CAPACITY = {
    "experience": 1500,
    "projects": 1200,
    "skills": 500,
    "education": 800,
    "summary": 600,
    "contact": 500,
}
DEFAULT_CAPACITY = 1000


def item_weight(item: Dict[str, Any]) -> int:
    """Integer weight of one item: explicit override or content length."""
    if item.get("weight") is not None:
        return max(0, int(item["weight"]))
    return max(0, len(str(item.get("content", "") or "")))


def item_utility(item: Dict[str, Any]) -> float:
    return max(0.0, float(item.get("utility", 0.0)))


def _knapsack_dp(
    values: List[float], weights: List[int], capacity: int
) -> List[int]:
    """
    0/1 knapsack DP over `values`/`weights` with integer `capacity`.
    Returns the sorted indices of the optimal subset (global optimum).
    """
    n = len(values)
    if n == 0 or capacity <= 0:
        return []
    # dp[w] = best value achievable with budget w; keep[i][w] = item i taken.
    dp = [0.0] * (capacity + 1)
    keep = [[False] * (capacity + 1) for _ in range(n)]
    for i in range(n):
        v, w = values[i], weights[i]
        if w <= 0:
            # Zero-weight positive-value items are always taken.
            if v > 0:
                keep[i] = [True] * (capacity + 1)
                dp = [d + v for d in dp]
            continue
        if w > capacity:
            continue
        for c in range(capacity, w - 1, -1):
            if dp[c - w] + v > dp[c]:
                dp[c] = dp[c - w] + v
                keep[i][c] = True
    # Reconstruct.
    chosen: List[int] = []
    c = capacity
    for i in range(n - 1, -1, -1):
        if keep[i][c]:
            chosen.append(i)
            c -= weights[i] if weights[i] > 0 else 0
    return sorted(chosen)


def allocate_section(
    items: List[Dict[str, Any]], capacity: int
) -> Dict[str, Any]:
    """
    Allocate one section's items under `capacity` (chars, >= 0).
    Returns {selected, dropped, total_utility, total_weight, capacity,
    mandatory_weight}. Mandatory items are always in `selected`.
    """
    if capacity < 0:
        raise ValueError("capacity must be >= 0.")
    items = list(items or [])
    mandatory = [it for it in items if it.get("is_mandatory")]
    optional = [it for it in items if not it.get("is_mandatory")]
    mand_weight = sum(item_weight(it) for it in mandatory)
    mand_utility = sum(item_utility(it) for it in mandatory)
    remaining = max(0, capacity - mand_weight)
    opt_values = [item_utility(it) for it in optional]
    opt_weights = [item_weight(it) for it in optional]
    chosen = set(_knapsack_dp(opt_values, opt_weights, remaining))
    selected = list(mandatory) + [it for i, it in enumerate(optional) if i in chosen]
    dropped = [it for i, it in enumerate(optional) if i not in chosen]
    total_utility = mand_utility + sum(opt_values[i] for i in chosen)
    total_weight = mand_weight + sum(opt_weights[i] for i in chosen)
    logger.info("Allocated section: %d/%d kept (utility=%.3f, weight=%d/%d)",
                len(selected), len(items), total_utility, total_weight, capacity)
    return {
        "selected": selected,
        "dropped": dropped,
        "total_utility": total_utility,
        "total_weight": total_weight,
        "capacity": capacity,
        "mandatory_weight": mand_weight,
    }


def allocate_facts(
    items: List[Dict[str, Any]],
    capacities: Optional[Dict[str, int]] = None,
    default_capacity: int = DEFAULT_CAPACITY,
) -> Dict[str, Dict[str, Any]]:
    """
    Group items by "section" (missing -> "other") and allocate each group.
    `capacities` maps section -> W; sections absent use
    DEFAULT_SECTION_CAPACITY then `default_capacity`. Returns
    {section: allocate_section(...)}.
    """
    capacities = capacities or {}
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for it in items or []:
        section = str(it.get("section") or "other").strip() or "other"
        groups.setdefault(section, []).append(it)
    result: Dict[str, Dict[str, Any]] = {}
    for section, group in groups.items():
        cap = capacities.get(
            section, DEFAULT_SECTION_CAPACITY.get(section, default_capacity))
        result[section] = allocate_section(group, cap)
    return result
