"""Tests for Phase 6 batch CLI helper logic in main.py."""

from pathlib import Path

from main import (
    _collect_jd_pdfs,
    _compute_linear_sleep,
    _diagnose_bottleneck,
)


def test_collect_jd_pdfs_non_recursive(tmp_path: Path):
    (tmp_path / "a.pdf").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "c.pdf").write_text("x", encoding="utf-8")

    files = _collect_jd_pdfs(tmp_path, recursive=False)
    assert [p.name for p in files] == ["a.pdf"]


def test_collect_jd_pdfs_recursive(tmp_path: Path):
    (tmp_path / "a.pdf").write_text("x", encoding="utf-8")
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "c.pdf").write_text("x", encoding="utf-8")

    files = _collect_jd_pdfs(tmp_path, recursive=True)
    assert [p.name for p in files] == ["a.pdf", "c.pdf"]


def test_compute_linear_sleep():
    assert _compute_linear_sleep(0, 1.0, 0.25) == 1.0
    assert _compute_linear_sleep(2, 1.0, 0.25) == 1.5
    assert _compute_linear_sleep(-3, 1.0, 0.25) == 1.0


def test_diagnose_profile_facts_low_priority():
    out = _diagnose_bottleneck(
        profile_fact_count=5,
        selected_count=3,
        required_skills_count=10,
        total_utility=3.0,
        weakest_coverage=0.8,
        unsupported_ratio=0.0,
        timings_ms={"cover_ms": 1200},
        pdf_failed=False,
    )
    assert out["category"] == "profile_facts_low"


def test_diagnose_scoring_alignment_priority():
    out = _diagnose_bottleneck(
        profile_fact_count=30,
        selected_count=12,
        required_skills_count=8,
        total_utility=0.7,
        weakest_coverage=0.3,
        unsupported_ratio=0.0,
        timings_ms={"cover_ms": 1200},
        pdf_failed=False,
    )
    assert out["category"] == "scoring_alignment"


def test_diagnose_pdf_generation_failure_priority():
    out = _diagnose_bottleneck(
        profile_fact_count=30,
        selected_count=12,
        required_skills_count=8,
        total_utility=2.0,
        weakest_coverage=0.9,
        unsupported_ratio=0.0,
        timings_ms={"cover_ms": 1200},
        pdf_failed=True,
    )
    assert out["category"] == "pdf_generation"


def test_diagnose_slowest_stage_when_healthy():
    out = _diagnose_bottleneck(
        profile_fact_count=30,
        selected_count=15,
        required_skills_count=4,
        total_utility=2.4,
        weakest_coverage=0.95,
        unsupported_ratio=0.05,
        timings_ms={"verify_ms": 300, "cover_ms": 1900, "resume_pdf_ms": 100},
        pdf_failed=False,
    )
    assert out["category"] == "llm_latency"
