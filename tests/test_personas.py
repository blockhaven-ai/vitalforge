"""Persona schema validation tests."""

from __future__ import annotations

import json

import pytest

from vitalforge.personas import PersonaError, load_persona, persona_from_dict

MINIMAL = {
    "schema_version": 1,
    "profile": {"name": "Test Person", "birth_date": "1990-01-01", "sex": "female"},
    "start_date": "2025-01-01",
    "baseline": {"steps": {"weekday_mean": 8000, "weekday_std": 1500, "weekend_mean": 10000, "weekend_std": 2000}},
}


def test_load_example_personas(alex_persona, jordan_persona):
    assert alex_persona.profile.name == "Alex Rivera"
    assert alex_persona.baseline.heart_rate is not None
    assert alex_persona.baseline.glucose is not None
    assert len(alex_persona.conditions) == 2
    assert len(alex_persona.medications) == 2
    assert alex_persona.trajectory is None

    assert jordan_persona.profile.name == "Jordan Kim"
    assert jordan_persona.trajectory is not None
    assert len(jordan_persona.trajectory.blood_pressure_phases) == 2
    assert "resting_hr" in jordan_persona.trajectory.metrics


def test_slug(alex_persona):
    assert alex_persona.slug == "alex_rivera"


def test_minimal_persona_parses():
    persona = persona_from_dict(MINIMAL)
    assert persona.baseline.steps is not None
    assert persona.baseline.heart_rate is None


def test_missing_profile_name_raises():
    bad = json.loads(json.dumps(MINIMAL))
    del bad["profile"]["name"]
    with pytest.raises(PersonaError, match="name"):
        persona_from_dict(bad)


def test_missing_start_date_raises():
    bad = json.loads(json.dumps(MINIMAL))
    del bad["start_date"]
    with pytest.raises(PersonaError, match="start_date"):
        persona_from_dict(bad)


def test_bad_schema_version_raises():
    bad = json.loads(json.dumps(MINIMAL))
    bad["schema_version"] = 99
    with pytest.raises(PersonaError, match="schema_version"):
        persona_from_dict(bad)


def test_invalid_sex_raises():
    bad = json.loads(json.dumps(MINIMAL))
    bad["profile"]["sex"] = "robot"
    with pytest.raises(PersonaError, match="sex"):
        persona_from_dict(bad)


def test_unknown_baseline_block_raises():
    bad = json.loads(json.dumps(MINIMAL))
    bad["baseline"]["unknown_signal"] = {}
    with pytest.raises(PersonaError, match="unknown"):
        persona_from_dict(bad)


def test_unknown_baseline_param_raises():
    bad = json.loads(json.dumps(MINIMAL))
    bad["baseline"]["steps"]["bogus_param"] = 1
    with pytest.raises(PersonaError, match="steps"):
        persona_from_dict(bad)


def test_trajectory_metric_without_value_raises():
    bad = json.loads(json.dumps(MINIMAL))
    bad["trajectory"] = {"metrics": {"weight_kg": [{"year": 0}]}}
    with pytest.raises(PersonaError, match="weight_kg"):
        persona_from_dict(bad)


def test_json_persona_load(tmp_path):
    path = tmp_path / "persona.json"
    path.write_text(json.dumps(MINIMAL), encoding="utf-8")
    persona = load_persona(path)
    assert persona.profile.name == "Test Person"


def test_unsupported_extension_raises(tmp_path):
    path = tmp_path / "persona.toml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(PersonaError, match="unsupported"):
        load_persona(path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(PersonaError, match="not found"):
        load_persona(tmp_path / "nope.yaml")
