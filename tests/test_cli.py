"""CLI smoke tests (in-process, offline)."""

from __future__ import annotations

import json

from vitalforge.cli import main

from conftest import ALEX, JORDAN


def test_generate_smoke(tmp_path, capsys):
    rc = main(
        [
            "generate",
            "--persona", str(ALEX),
            "--days", "10",
            "--seed", "42",
            "--out", str(tmp_path),
            "--format", "jsonl",
        ]
    )
    assert rc == 0
    out_file = tmp_path / "alex_rivera.jsonl"
    assert out_file.exists()
    captured = capsys.readouterr()
    assert "alex_rivera.jsonl" in captured.out


def test_generate_byte_identical_runs(tmp_path):
    args = ["generate", "--persona", str(ALEX), "--days", "10", "--seed", "42", "--format", "json"]
    assert main(args + ["--out", str(tmp_path / "a")]) == 0
    assert main(args + ["--out", str(tmp_path / "b")]) == 0
    a = (tmp_path / "a" / "alex_rivera.json").read_bytes()
    b = (tmp_path / "b" / "alex_rivera.json").read_bytes()
    assert a == b


def test_generate_start_date_override(tmp_path):
    rc = main(
        [
            "generate",
            "--persona", str(ALEX),
            "--days", "3",
            "--seed", "1",
            "--start-date", "2030-06-01",
            "--out", str(tmp_path),
            "--format", "json",
        ]
    )
    assert rc == 0
    data = json.loads((tmp_path / "alex_rivera.json").read_text(encoding="utf-8"))
    assert data["generator"]["start_date"] == "2030-06-01"
    assert data["signals"][0]["start"].startswith("2030-06-01")


def test_trajectory_smoke(tmp_path):
    rc = main(
        [
            "trajectory",
            "--persona", str(JORDAN),
            "--years", "10",
            "--seed", "42",
            "--out", str(tmp_path),
            "--format", "json",
        ]
    )
    assert rc == 0
    data = json.loads((tmp_path / "jordan_kim_trajectory.json").read_text(encoding="utf-8"))
    assert data["generator"]["mode"] == "trajectory"
    assert len([r for r in data["trajectory"] if r["record_type"] == "year_summary"]) == 11


def test_fhir_format(tmp_path):
    rc = main(
        [
            "generate",
            "--persona", str(ALEX),
            "--days", "5",
            "--seed", "42",
            "--out", str(tmp_path),
            "--format", "fhir",
        ]
    )
    assert rc == 0
    bundle = json.loads((tmp_path / "alex_rivera_fhir.json").read_text(encoding="utf-8"))
    assert bundle["resourceType"] == "Bundle"


def test_missing_persona_errors(tmp_path, capsys):
    rc = main(
        ["generate", "--persona", str(tmp_path / "missing.yaml"), "--out", str(tmp_path)]
    )
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_trajectory_without_section_errors(tmp_path, capsys):
    rc = main(["trajectory", "--persona", str(ALEX), "--out", str(tmp_path)])
    assert rc == 2
    assert "trajectory" in capsys.readouterr().err


def test_invalid_days_errors(tmp_path, capsys):
    rc = main(
        ["generate", "--persona", str(ALEX), "--days", "0", "--out", str(tmp_path)]
    )
    assert rc == 2
