"""Multi-year trajectory generation tests."""

from __future__ import annotations

import random

import pytest

from vitalforge.dataset import build_trajectory_dataset
from vitalforge.personas import PersonaError
from vitalforge.trajectory import (
    bp_for_year,
    build_trajectory_records,
    interpolate_series,
    lerp,
)


def test_lerp():
    assert lerp(0, 10, 0.5) == 5
    assert lerp(10, 0, 1.0) == 0


def test_interpolate_series_midpoint_and_clamping():
    points = [{"year": 0, "value": 100.0}, {"year": 10, "value": 50.0}]
    assert interpolate_series(points, 5) == pytest.approx(75.0)
    assert interpolate_series(points, -1) == 100.0
    assert interpolate_series(points, 12) == 50.0


def test_interpolate_series_mean_key():
    points = [{"year": 0, "mean": 60, "std": 3}, {"year": 4, "mean": 56, "std": 3}]
    assert interpolate_series(points, 2, key="mean") == pytest.approx(58.0)


def test_bp_for_year_phases():
    phases = [
        {"year_start": 0, "year_end": 2, "systolic": [140, 130], "diastolic": [90, 84]},
        {"year_start": 2, "year_end": 10, "systolic": [130, 120], "diastolic": [84, 76]},
    ]
    s0, d0 = bp_for_year(phases, 0)
    assert (s0, d0) == (140, 90)
    s1, _ = bp_for_year(phases, 1)
    assert s1 == 135
    s99, d99 = bp_for_year(phases, 99)
    assert (s99, d99) == (120, 76)


def test_year_summaries_count_and_fields(jordan_persona):
    rng = random.Random(42)
    records = build_trajectory_records(jordan_persona, 10, rng)
    summaries = [r for r in records if r["record_type"] == "year_summary"]
    assert len(summaries) == 11
    first = summaries[0]
    assert first["calendar_year"] == 2026
    assert first["age"] == 2026 - 1992
    assert "systolic_mmhg" in first["vitals"]
    assert "resting_hr" in first["vitals"]


def test_trajectory_vitals_track_anchors(jordan_persona):
    rng = random.Random(42)
    records = build_trajectory_records(jordan_persona, 10, rng)
    summaries = {r["year"]: r for r in records if r["record_type"] == "year_summary"}
    # resting_hr declines from ~62 to ~55 per the persona anchors
    assert summaries[0]["vitals"]["resting_hr"] > summaries[10]["vitals"]["resting_hr"]
    # systolic stays within the configured narrow band (plus small noise)
    for s in summaries.values():
        assert 110 <= s["vitals"]["systolic_mmhg"] <= 125


def test_milestones_and_encounters_in_range(jordan_persona):
    rng = random.Random(42)
    records = build_trajectory_records(jordan_persona, 5, rng)
    milestones = [r for r in records if r["record_type"] == "milestone"]
    assert all(m["year"] <= 5 for m in milestones)
    # year-8 milestone excluded at years=5
    assert len(milestones) == 2
    encounters = [r for r in records if r["record_type"] == "encounter"]
    assert all(e["year"] <= 5 for e in encounters)


def test_trajectory_requires_trajectory_section(alex_persona):
    with pytest.raises(PersonaError, match="trajectory"):
        build_trajectory_dataset(alex_persona, years=10, seed=42)
