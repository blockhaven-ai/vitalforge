"""Output writers: JSON, JSONL, CSV, and FHIR R4 Bundle.

All writers are deterministic: given the same dataset they produce
byte-identical files.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, List

from vitalforge.clinical import code_system_uri
from vitalforge.ids import stable_id

FORMATS = ("json", "jsonl", "csv", "fhir")

_LOINC = "http://loinc.org"
_UCUM = "http://unitsofmeasure.org"
_VITAL_SIGNS_CATEGORY = [
    {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "vital-signs",
            }
        ]
    }
]
_LAB_CATEGORY = [
    {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "laboratory",
            }
        ]
    }
]


def _record_lists(dataset: dict) -> List[tuple]:
    """Return (section_name, records) pairs present in the dataset."""
    return [(key, dataset[key]) for key in ("signals", "clinical", "trajectory") if key in dataset]


# ---------------------------------------------------------------------------
# JSON / JSONL
# ---------------------------------------------------------------------------


def write_json(dataset: dict, path: Path) -> Path:
    """Write the whole dataset as a single indented JSON document."""
    path.write_text(json.dumps(dataset, indent=2) + "\n", encoding="utf-8")
    return path


def write_jsonl(dataset: dict, path: Path) -> Path:
    """Write one JSON record per line, preceded by a metadata record."""
    lines = [
        json.dumps(
            {
                "record_type": "metadata",
                "generator": dataset["generator"],
                "persona": dataset["persona"],
            }
        )
    ]
    for _, records in _record_lists(dataset):
        lines.extend(json.dumps(record) for record in records)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def _signal_rows(records: Iterable[dict]) -> Iterable[list]:
    for rec in records:
        signal = rec["signal"]
        unit = rec["unit"]
        if signal == "sleep":
            for ep in rec["episodes"]:
                yield [signal, ep["start"], ep["stage"], ep["duration_min"], "min", ""]
        elif signal == "blood_pressure":
            for s in rec["samples"]:
                yield [signal, s["t"], "systolic", s["systolic"], unit, ""]
                yield [signal, s["t"], "diastolic", s["diastolic"], unit, ""]
        else:
            for s in rec["samples"]:
                yield [signal, s["t"], "", s["value"], unit, s.get("context", "")]


def _clinical_rows(records: Iterable[dict]) -> Iterable[list]:
    for rec in records:
        rtype = rec["record_type"]
        date = rec.get("onset_date") or rec.get("start_date") or rec.get("date") or rec.get("time") or ""
        text = rec.get("text") or rec.get("service") or ""
        detail = ""
        if rtype == "medication" and rec.get("dose"):
            dose = rec["dose"]
            detail = f"{dose.get('quantity', '')} {dose.get('unit', '')} {dose.get('frequency', '')}".strip()
        elif rtype == "lab" and rec.get("value") is not None:
            detail = f"{rec['value']} {rec.get('unit') or ''}".strip()
        elif rtype == "encounter":
            detail = rec.get("summary") or ""
        codes = rec.get("codes") or [{}]
        for code in codes:
            yield [
                rtype,
                date,
                text,
                code.get("system", ""),
                code.get("code", ""),
                code.get("display", ""),
                detail,
            ]


def _trajectory_rows(records: Iterable[dict]) -> Iterable[list]:
    for rec in records:
        rtype = rec["record_type"]
        if rtype == "year_summary":
            for name, value in rec["vitals"].items():
                yield [rtype, rec["year"], "", name, value, ""]
            yield [rtype, rec["year"], "", "encounter_count", rec["encounter_count"], ""]
            yield [
                rtype,
                rec["year"],
                "",
                "active_medications",
                "",
                "; ".join(rec["active_medications"]),
            ]
        elif rtype == "milestone":
            yield [rtype, rec["year"], rec["date"], rec.get("kind") or "", "", rec["event"]]
        elif rtype == "encounter":
            text = f"{rec['service']} — {rec.get('outcome') or ''}".strip(" —")
            yield [rtype, rec["year"], rec["date"], rec.get("kind") or "", "", text]
        elif rtype == "medication_period":
            yield [
                rtype,
                rec["start_year"],
                f"{rec['start_calendar_year']}-{rec['end_calendar_year']}",
                rec["name"],
                "",
                rec.get("detail") or "",
            ]


def write_csv(dataset: dict, out_dir: Path, slug: str) -> List[Path]:
    """Write CSV files, one per record section present in the dataset."""
    written: List[Path] = []
    if "signals" in dataset:
        path = out_dir / f"{slug}_signals.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["signal", "timestamp", "component", "value", "unit", "context"])
            writer.writerows(_signal_rows(dataset["signals"]))
        written.append(path)
    if "clinical" in dataset:
        path = out_dir / f"{slug}_clinical.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["record_type", "date", "text", "code_system", "code", "display", "detail"])
            writer.writerows(_clinical_rows(dataset["clinical"]))
        written.append(path)
    if "trajectory" in dataset:
        path = out_dir / f"{slug}_trajectory.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["record_type", "year", "date", "name", "value", "text"])
            writer.writerows(_trajectory_rows(dataset["trajectory"]))
        written.append(path)
    return written


# ---------------------------------------------------------------------------
# FHIR R4
# ---------------------------------------------------------------------------


def _codeable_concept(text: str, codes: Iterable[dict]) -> dict:
    concept: dict = {"text": text}
    coding = [
        {
            "system": code_system_uri(c["system"]),
            "code": c["code"],
            **({"display": c["display"]} if c.get("display") else {}),
        }
        for c in codes
    ]
    if coding:
        concept["coding"] = coding
    return concept


def _observation(obs_id: str, patient_id: str, code: dict, category: list) -> dict:
    return {
        "resourceType": "Observation",
        "id": obs_id,
        "status": "final",
        "category": category,
        "code": code,
        "subject": {"reference": f"urn:uuid:{patient_id}"},
    }


def _quantity(value: float, unit: str, ucum: str) -> dict:
    return {"value": value, "unit": unit, "system": _UCUM, "code": ucum}


def _mean(values: List[float]) -> float:
    return sum(values) / len(values)


def _signal_observations(records: Iterable[dict], patient_id: str, slug: str) -> List[dict]:
    """Map signal records to FHIR Observations.

    Instant signals (blood pressure, glucose, weight) become one Observation
    per reading. Sampled/aggregate signals (heart rate, steps, activity
    energy, sleep) become one daily-summary Observation per record.
    """
    out: List[dict] = []
    for rec in records:
        signal = rec["signal"]
        period = {"start": rec["start"], "end": rec["end"]}
        if signal == "heart_rate":
            values = [s["value"] for s in rec["samples"]]
            obs = _observation(
                stable_id(slug, "fhir", rec["id"]),
                patient_id,
                {
                    "text": "Heart rate (daily mean)",
                    "coding": [{"system": _LOINC, "code": "8867-4", "display": "Heart rate"}],
                },
                _VITAL_SIGNS_CATEGORY,
            )
            obs["effectivePeriod"] = period
            obs["valueQuantity"] = _quantity(round(_mean(values), 1), "beats/minute", "/min")
            out.append(obs)
        elif signal == "blood_pressure":
            for i, s in enumerate(rec["samples"]):
                obs = _observation(
                    stable_id(slug, "fhir", rec["id"], str(i)),
                    patient_id,
                    {
                        "text": "Blood pressure panel",
                        "coding": [
                            {
                                "system": _LOINC,
                                "code": "85354-9",
                                "display": "Blood pressure panel with all children optional",
                            }
                        ],
                    },
                    _VITAL_SIGNS_CATEGORY,
                )
                obs["effectiveDateTime"] = s["t"]
                obs["component"] = [
                    {
                        "code": {
                            "coding": [
                                {"system": _LOINC, "code": "8480-6", "display": "Systolic blood pressure"}
                            ]
                        },
                        "valueQuantity": _quantity(s["systolic"], "mmHg", "mm[Hg]"),
                    },
                    {
                        "code": {
                            "coding": [
                                {"system": _LOINC, "code": "8462-4", "display": "Diastolic blood pressure"}
                            ]
                        },
                        "valueQuantity": _quantity(s["diastolic"], "mmHg", "mm[Hg]"),
                    },
                ]
                out.append(obs)
        elif signal == "steps":
            obs = _observation(
                stable_id(slug, "fhir", rec["id"]),
                patient_id,
                {
                    "text": "Steps in 24 hours",
                    "coding": [
                        {"system": _LOINC, "code": "41950-7", "display": "Number of steps in 24 hour Measured"}
                    ],
                },
                _VITAL_SIGNS_CATEGORY,
            )
            obs["effectivePeriod"] = period
            obs["valueQuantity"] = _quantity(rec["samples"][0]["value"], "steps", "{steps}")
            out.append(obs)
        elif signal == "sleep":
            obs = _observation(
                stable_id(slug, "fhir", rec["id"]),
                patient_id,
                {
                    "text": "Sleep duration",
                    "coding": [{"system": _LOINC, "code": "93832-4", "display": "Sleep duration"}],
                },
                _VITAL_SIGNS_CATEGORY,
            )
            obs["effectivePeriod"] = period
            obs["valueQuantity"] = _quantity(rec["total_sleep_min"], "min", "min")
            out.append(obs)
        elif signal == "glucose":
            for i, s in enumerate(rec["samples"]):
                obs = _observation(
                    stable_id(slug, "fhir", rec["id"], str(i)),
                    patient_id,
                    {
                        "text": f"Glucose ({s['context']})",
                        "coding": [
                            {"system": _LOINC, "code": "2339-0", "display": "Glucose [Mass/volume] in Blood"}
                        ],
                    },
                    _LAB_CATEGORY,
                )
                obs["effectiveDateTime"] = s["t"]
                obs["valueQuantity"] = _quantity(s["value"], "mg/dL", "mg/dL")
                out.append(obs)
        elif signal == "weight":
            s = rec["samples"][0]
            obs = _observation(
                stable_id(slug, "fhir", rec["id"]),
                patient_id,
                {
                    "text": "Body weight",
                    "coding": [{"system": _LOINC, "code": "29463-7", "display": "Body weight"}],
                },
                _VITAL_SIGNS_CATEGORY,
            )
            obs["effectiveDateTime"] = s["t"]
            obs["valueQuantity"] = _quantity(s["value"], "kg", "kg")
            out.append(obs)
        elif signal == "activity_energy":
            obs = _observation(
                stable_id(slug, "fhir", rec["id"]),
                patient_id,
                {
                    "text": "Active energy (daily total)",
                    "coding": [
                        {"system": _LOINC, "code": "41981-2", "display": "Calories burned"}
                    ],
                },
                _VITAL_SIGNS_CATEGORY,
            )
            obs["effectivePeriod"] = period
            obs["valueQuantity"] = _quantity(rec["samples"][0]["value"], "kcal", "kcal")
            out.append(obs)
    return out


def _clinical_resources(records: Iterable[dict], patient_id: str) -> List[dict]:
    out: List[dict] = []
    subject = {"reference": f"urn:uuid:{patient_id}"}
    for rec in records:
        rtype = rec["record_type"]
        if rtype == "condition":
            resource = {
                "resourceType": "Condition",
                "id": rec["id"],
                "clinicalStatus": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                            "code": "active",
                        }
                    ]
                },
                "code": _codeable_concept(rec["text"], rec["codes"]),
                "subject": subject,
            }
            if rec.get("onset_date"):
                resource["onsetDateTime"] = rec["onset_date"]
            out.append(resource)
        elif rtype == "medication":
            resource = {
                "resourceType": "MedicationStatement",
                "id": rec["id"],
                "status": "active" if not rec.get("end_date") else "completed",
                "medicationCodeableConcept": _codeable_concept(rec["text"], rec["codes"]),
                "subject": subject,
            }
            if rec.get("start_date"):
                period = {"start": rec["start_date"]}
                if rec.get("end_date"):
                    period["end"] = rec["end_date"]
                resource["effectivePeriod"] = period
            if rec.get("dose"):
                dose = rec["dose"]
                text = f"{dose.get('quantity', '')} {dose.get('unit', '')} {dose.get('frequency', '')}".strip()
                resource["dosage"] = [{"text": text}]
            out.append(resource)
        elif rtype == "allergy":
            resource = {
                "resourceType": "AllergyIntolerance",
                "id": rec["id"],
                "code": _codeable_concept(rec["text"], rec["codes"]),
                "patient": subject,
            }
            if rec.get("onset_date"):
                resource["onsetDateTime"] = rec["onset_date"]
            out.append(resource)
        elif rtype == "immunization":
            resource = {
                "resourceType": "Immunization",
                "id": rec["id"],
                "status": "completed",
                "vaccineCode": _codeable_concept(rec["text"], rec["codes"]),
                "patient": subject,
            }
            if rec.get("date"):
                resource["occurrenceDateTime"] = rec["date"]
            out.append(resource)
        elif rtype == "lab":
            resource = {
                "resourceType": "Observation",
                "id": rec["id"],
                "status": "final",
                "category": _LAB_CATEGORY,
                "code": _codeable_concept(rec["text"], rec["codes"]),
                "subject": subject,
            }
            if rec.get("date"):
                resource["effectiveDateTime"] = rec["date"]
            if rec.get("value") is not None:
                quantity = {"value": rec["value"]}
                if rec.get("unit"):
                    quantity["unit"] = rec["unit"]
                resource["valueQuantity"] = quantity
            else:
                resource["valueString"] = rec["text"]
            if rec.get("reference_range"):
                resource["referenceRange"] = [{"text": rec["reference_range"]}]
            out.append(resource)
        elif rtype == "encounter":
            resource = {
                "resourceType": "Encounter",
                "id": rec["id"],
                "status": "finished",
                "class": {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    "code": "VR" if rec.get("modality") == "video" else "AMB",
                },
                "type": [{"text": rec["service"]}],
                "subject": subject,
                "period": {"start": rec["time"]},
            }
            if rec.get("reason"):
                resource["reasonCode"] = [{"text": rec["reason"]}]
            participants = [
                {"individual": {"display": p.get("name", "")}}
                for p in rec.get("providers", [])
                if p.get("name")
            ]
            if participants:
                resource["participant"] = participants
            out.append(resource)
    return out


def to_fhir_bundle(dataset: dict) -> dict:
    """Convert a daily dataset to a FHIR R4 ``Bundle`` of type ``collection``.

    Includes a Patient resource, Observations for signals and labs, and
    Condition / MedicationStatement / AllergyIntolerance / Immunization /
    Encounter resources for the clinical history.
    """
    persona = dataset["persona"]
    patient_id = stable_id(persona["slug"], "fhir", "patient")
    patient = {
        "resourceType": "Patient",
        "id": patient_id,
        "name": [{"text": persona["name"]}],
        "birthDate": persona["birth_date"],
        "gender": persona["sex"],
    }
    resources = [patient]
    resources.extend(
        _signal_observations(dataset.get("signals", []), patient_id, persona["slug"])
    )
    resources.extend(_clinical_resources(dataset.get("clinical", []), patient_id))
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"fullUrl": f"urn:uuid:{r['id']}", "resource": r} for r in resources
        ],
    }


def write_fhir(dataset: dict, path: Path) -> Path:
    """Write the dataset as a FHIR R4 Bundle JSON document."""
    bundle = to_fhir_bundle(dataset)
    path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def write_dataset(dataset: dict, out_dir: Path, fmt: str) -> List[Path]:
    """Write the dataset to ``out_dir`` in the requested format.

    Returns the list of files written. ``fhir`` is only valid for daily
    datasets (those containing ``signals``).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = dataset["persona"]["slug"]
    suffix = "" if dataset["generator"]["mode"] == "generate" else "_trajectory"
    if fmt == "json":
        return [write_json(dataset, out_dir / f"{slug}{suffix}.json")]
    if fmt == "jsonl":
        return [write_jsonl(dataset, out_dir / f"{slug}{suffix}.jsonl")]
    if fmt == "csv":
        return write_csv(dataset, out_dir, slug)
    if fmt == "fhir":
        if "signals" not in dataset:
            raise ValueError("FHIR export is only supported for daily datasets")
        return [write_fhir(dataset, out_dir / f"{slug}_fhir.json")]
    raise ValueError(f"unknown format {fmt!r} (expected one of {FORMATS})")
