"""Clinical record builders: conditions, medications, allergies,
immunizations, labs, and encounters.

Records carry terminology codings (SNOMED, ICD-10, RxNorm, LOINC, CVX) as
declared in the persona document. Builders are deterministic: record ids
derive from the persona slug and record index.
"""

from __future__ import annotations

from typing import List

from vitalforge.ids import stable_id
from vitalforge.personas import Coding, Persona

#: Shorthand terminology names accepted in persona files, mapped to canonical URIs.
CODE_SYSTEM_URIS = {
    "SNOMED": "http://snomed.info/sct",
    "ICD-10": "http://hl7.org/fhir/sid/icd-10-cm",
    "RXNORM": "http://www.nlm.nih.gov/research/umls/rxnorm",
    "LOINC": "http://loinc.org",
    "CVX": "http://hl7.org/fhir/sid/cvx",
}


def code_system_uri(system: str) -> str:
    """Resolve a shorthand system name to its canonical URI.

    Full URIs and unknown system names pass through unchanged.
    """
    return CODE_SYSTEM_URIS.get(system.upper(), system)


def _coding_dicts(codes: tuple) -> List[dict]:
    out = []
    for c in codes:
        assert isinstance(c, Coding)
        entry = {"system": c.system, "code": c.code}
        if c.display:
            entry["display"] = c.display
        out.append(entry)
    return out


def build_clinical_records(persona: Persona) -> List[dict]:
    """Build all clinical records for a persona, in a fixed order."""
    slug = persona.slug
    records: List[dict] = []

    for i, cond in enumerate(persona.conditions):
        records.append(
            {
                "record_type": "condition",
                "id": stable_id(slug, "condition", str(i)),
                "text": cond.text,
                "codes": _coding_dicts(cond.codes),
                "onset_date": cond.onset_date,
            }
        )

    for i, med in enumerate(persona.medications):
        records.append(
            {
                "record_type": "medication",
                "id": stable_id(slug, "medication", str(i)),
                "text": med.text,
                "codes": _coding_dicts(med.codes),
                "dose": dict(med.dose) if med.dose else None,
                "start_date": med.start_date,
                "end_date": med.end_date,
            }
        )

    for i, allergy in enumerate(persona.allergies):
        records.append(
            {
                "record_type": "allergy",
                "id": stable_id(slug, "allergy", str(i)),
                "text": allergy.text,
                "codes": _coding_dicts(allergy.codes),
                "onset_date": allergy.onset_date,
            }
        )

    for i, imm in enumerate(persona.immunizations):
        records.append(
            {
                "record_type": "immunization",
                "id": stable_id(slug, "immunization", str(i)),
                "text": imm.text,
                "codes": _coding_dicts(imm.codes),
                "date": imm.date,
            }
        )

    for i, lab in enumerate(persona.labs):
        records.append(
            {
                "record_type": "lab",
                "id": stable_id(slug, "lab", str(i)),
                "text": lab.text,
                "codes": _coding_dicts(lab.codes),
                "value": lab.value,
                "unit": lab.unit,
                "reference_range": lab.reference_range,
                "date": lab.date,
            }
        )

    for i, enc in enumerate(persona.encounters):
        records.append(
            {
                "record_type": "encounter",
                "id": stable_id(slug, "encounter", str(i)),
                "kind": enc.kind,
                "modality": enc.modality,
                "service": enc.service,
                "reason": enc.reason,
                "providers": [dict(p) for p in enc.providers],
                "location": enc.location,
                "time": enc.time,
                "summary": enc.summary,
            }
        )

    return records
