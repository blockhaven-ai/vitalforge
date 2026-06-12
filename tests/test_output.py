"""Output format tests: JSON, JSONL, CSV, FHIR R4 Bundle."""

from __future__ import annotations

import csv
import json

import pytest

from vitalforge.dataset import build_dataset, build_trajectory_dataset
from vitalforge.output import to_fhir_bundle, write_dataset


@pytest.fixture
def daily_dataset(alex_persona):
    return build_dataset(alex_persona, days=10, seed=42)


@pytest.fixture
def trajectory_dataset(jordan_persona):
    return build_trajectory_dataset(jordan_persona, years=10, seed=42)


def test_json_roundtrip(daily_dataset, tmp_path):
    (path,) = write_dataset(daily_dataset, tmp_path, "json")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == daily_dataset


def test_jsonl_lines_parse(daily_dataset, tmp_path):
    (path,) = write_dataset(daily_dataset, tmp_path, "jsonl")
    lines = path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert records[0]["record_type"] == "metadata"
    assert records[0]["generator"]["seed"] == 42
    body = records[1:]
    assert len(body) == len(daily_dataset["signals"]) + len(daily_dataset["clinical"])
    assert all("record_type" in r for r in body)


def test_csv_outputs(daily_dataset, tmp_path):
    paths = write_dataset(daily_dataset, tmp_path, "csv")
    names = sorted(p.name for p in paths)
    assert names == ["alex_rivera_clinical.csv", "alex_rivera_signals.csv"]
    with (tmp_path / "alex_rivera_signals.csv").open() as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["signal", "timestamp", "component", "value", "unit", "context"]
    assert len(rows) > 1
    signals_seen = {row[0] for row in rows[1:]}
    assert {"heart_rate", "blood_pressure", "sleep", "glucose"} <= signals_seen
    with (tmp_path / "alex_rivera_clinical.csv").open() as f:
        crows = list(csv.reader(f))
    assert crows[0] == ["record_type", "date", "text", "code_system", "code", "display", "detail"]
    types_seen = {row[0] for row in crows[1:]}
    assert {"condition", "medication", "lab", "encounter"} <= types_seen


def test_trajectory_csv(trajectory_dataset, tmp_path):
    paths = write_dataset(trajectory_dataset, tmp_path, "csv")
    assert [p.name for p in paths] == ["jordan_kim_trajectory.csv"]
    with paths[0].open() as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["record_type", "year", "date", "name", "value", "text"]
    assert any(row[0] == "year_summary" for row in rows[1:])
    assert any(row[0] == "milestone" for row in rows[1:])


def test_fhir_bundle_structure(daily_dataset):
    bundle = to_fhir_bundle(daily_dataset)
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    resources = [e["resource"] for e in bundle["entry"]]
    by_type: dict = {}
    for r in resources:
        by_type.setdefault(r["resourceType"], []).append(r)
    assert len(by_type["Patient"]) == 1
    assert by_type["Patient"][0]["birthDate"] == "1989-04-12"
    assert len(by_type["Condition"]) == 2
    assert len(by_type["MedicationStatement"]) == 2
    assert len(by_type["AllergyIntolerance"]) == 1
    assert len(by_type["Immunization"]) == 1
    assert len(by_type["Encounter"]) == 3
    assert len(by_type["Observation"]) > 10


def test_fhir_code_system_uris(daily_dataset):
    bundle = to_fhir_bundle(daily_dataset)
    conditions = [
        e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Condition"
    ]
    systems = {c["system"] for cond in conditions for c in cond["code"]["coding"]}
    assert "http://snomed.info/sct" in systems
    assert "http://hl7.org/fhir/sid/icd-10-cm" in systems
    meds = [
        e["resource"]
        for e in bundle["entry"]
        if e["resource"]["resourceType"] == "MedicationStatement"
    ]
    med_systems = {
        c["system"] for m in meds for c in m["medicationCodeableConcept"]["coding"]
    }
    assert med_systems == {"http://www.nlm.nih.gov/research/umls/rxnorm"}


def test_fhir_bp_components(daily_dataset):
    bundle = to_fhir_bundle(daily_dataset)
    bp_obs = [
        e["resource"]
        for e in bundle["entry"]
        if e["resource"]["resourceType"] == "Observation"
        and any(c.get("code") == "85354-9" for c in e["resource"]["code"].get("coding", []))
    ]
    assert bp_obs
    for obs in bp_obs:
        codes = {c["code"]["coding"][0]["code"] for c in obs["component"]}
        assert codes == {"8480-6", "8462-4"}


def test_fhir_rejected_for_trajectory(trajectory_dataset, tmp_path):
    with pytest.raises(ValueError, match="FHIR"):
        write_dataset(trajectory_dataset, tmp_path, "fhir")


def test_unknown_format_rejected(daily_dataset, tmp_path):
    with pytest.raises(ValueError, match="unknown format"):
        write_dataset(daily_dataset, tmp_path, "parquet")
