"""Determinism guarantees: same persona + parameters + seed -> identical output."""

from __future__ import annotations

import json

from vitalforge.dataset import build_dataset, build_trajectory_dataset
from vitalforge.output import write_dataset


def test_daily_dataset_identical_for_same_seed(alex_persona):
    a = build_dataset(alex_persona, days=30, seed=42)
    b = build_dataset(alex_persona, days=30, seed=42)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_daily_dataset_differs_for_different_seed(alex_persona):
    a = build_dataset(alex_persona, days=30, seed=42)
    b = build_dataset(alex_persona, days=30, seed=43)
    assert json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True)


def test_trajectory_identical_for_same_seed(jordan_persona):
    a = build_trajectory_dataset(jordan_persona, years=10, seed=42)
    b = build_trajectory_dataset(jordan_persona, years=10, seed=42)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_trajectory_differs_for_different_seed(jordan_persona):
    a = build_trajectory_dataset(jordan_persona, years=10, seed=42)
    b = build_trajectory_dataset(jordan_persona, years=10, seed=99)
    assert json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True)


def test_written_files_byte_identical(alex_persona, tmp_path):
    run1 = tmp_path / "run1"
    run2 = tmp_path / "run2"
    for fmt in ("json", "jsonl", "csv", "fhir"):
        dataset1 = build_dataset(alex_persona, days=10, seed=7)
        dataset2 = build_dataset(alex_persona, days=10, seed=7)
        paths1 = write_dataset(dataset1, run1, fmt)
        paths2 = write_dataset(dataset2, run2, fmt)
        assert [p.name for p in paths1] == [p.name for p in paths2]
        for p1, p2 in zip(paths1, paths2):
            assert p1.read_bytes() == p2.read_bytes(), f"{fmt}: {p1.name} differs"


def test_record_ids_stable_across_runs(alex_persona):
    a = build_dataset(alex_persona, days=5, seed=1)
    b = build_dataset(alex_persona, days=5, seed=1)
    assert [r["id"] for r in a["signals"]] == [r["id"] for r in b["signals"]]
    assert [r["id"] for r in a["clinical"]] == [r["id"] for r in b["clinical"]]
