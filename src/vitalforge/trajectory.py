"""Multi-year trajectory generation.

Builds yearly health snapshots from a persona's ``trajectory`` section by
linearly interpolating metric anchor points and blood-pressure phases, then
emitting milestone, encounter, and medication-period records.

Interpolated yearly vitals are sampled with mild gaussian measurement noise
(a quarter of the declared ``std``) so different seeds produce different but
distributionally consistent snapshots.
"""

from __future__ import annotations

import random
from typing import List, Sequence, Tuple

from vitalforge.ids import stable_id
from vitalforge.personas import Persona, PersonaError, TrajectoryDef

#: Fraction of a metric's declared std used as yearly measurement noise.
NOISE_FRACTION = 0.25


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between ``a`` and ``b`` at parameter ``t`` in [0, 1]."""
    return a + (b - a) * t


def interpolate_series(points: Sequence[dict], year: float, key: str = "value") -> float:
    """Interpolate ``key`` for ``year`` from a list of ``{"year": n, key: v}`` anchors.

    Years before the first anchor clamp to the first value; years after the
    last anchor clamp to the last value.
    """
    pts = sorted(points, key=lambda p: p["year"])
    if year <= pts[0]["year"]:
        return float(pts[0][key])
    if year >= pts[-1]["year"]:
        return float(pts[-1][key])
    for a, b in zip(pts, pts[1:]):
        if a["year"] <= year <= b["year"]:
            t = (year - a["year"]) / (b["year"] - a["year"])
            return lerp(float(a[key]), float(b[key]), t)
    return float(pts[-1][key])


def bp_for_year(phases: Sequence[dict], year: float) -> Tuple[int, int]:
    """Return (systolic, diastolic) for ``year`` from phase definitions.

    Each phase declares ``year_start``, ``year_end``, and two-element
    ``systolic``/``diastolic`` ranges that interpolate linearly across the
    phase.
    """
    for phase in phases:
        if phase["year_start"] <= year <= phase["year_end"]:
            span = max(1, phase["year_end"] - phase["year_start"])
            t = (year - phase["year_start"]) / span
            systolic = lerp(phase["systolic"][0], phase["systolic"][1], t)
            diastolic = lerp(phase["diastolic"][0], phase["diastolic"][1], t)
            return round(systolic), round(diastolic)
    last = phases[-1]
    return round(last["systolic"][1]), round(last["diastolic"][1])


def _metric_key(points: Sequence[dict]) -> str:
    return "mean" if "mean" in points[0] else "value"


def _metric_std(points: Sequence[dict], year: float) -> float:
    if any("std" in p for p in points):
        stds = [{"year": p["year"], "std": p.get("std", 0.0)} for p in points]
        return interpolate_series(stds, year, key="std")
    return 0.0


def build_trajectory_records(
    persona: Persona, years: int, rng: random.Random
) -> List[dict]:
    """Build year summaries, milestones, encounters, and medication periods.

    Produces ``years + 1`` year-summary records (year 0 through ``years``
    inclusive), one record per milestone and encounter whose year falls in
    range, and one record per medication period.
    """
    traj = persona.trajectory
    if traj is None:
        raise PersonaError(
            f"persona '{persona.profile.name}' has no trajectory section"
        )
    slug = persona.slug
    base_year = persona.start_date.year
    birth_year = persona.profile.birth_date.year
    records: List[dict] = []

    for year in range(years + 1):
        vitals: dict = {}
        if traj.blood_pressure_phases:
            systolic, diastolic = bp_for_year(traj.blood_pressure_phases, year)
            vitals["systolic_mmhg"] = int(round(systolic + rng.gauss(0, 1.0)))
            vitals["diastolic_mmhg"] = int(round(diastolic + rng.gauss(0, 1.0)))
        for name, points in traj.metrics.items():
            key = _metric_key(points)
            mean = interpolate_series(points, year, key=key)
            std = _metric_std(points, year)
            value = rng.gauss(mean, std * NOISE_FRACTION) if std else mean
            vitals[name] = round(value, 1)

        active_meds = [
            m["name"]
            for m in traj.medications
            if m["start_year"] <= year < m["end_year"]
        ]
        milestones = [m["event"] for m in traj.milestones if m["year"] == year]
        encounter_count = sum(1 for e in traj.encounters if e["year"] == year)

        records.append(
            {
                "record_type": "year_summary",
                "id": stable_id(slug, "year_summary", str(year)),
                "year": year,
                "calendar_year": base_year + year,
                "age": base_year + year - birth_year,
                "vitals": vitals,
                "active_medications": active_meds,
                "milestones": milestones,
                "encounter_count": encounter_count,
            }
        )

    for i, m in enumerate(traj.milestones):
        if m["year"] > years:
            continue
        month = int(m.get("month", 6))
        records.append(
            {
                "record_type": "milestone",
                "id": stable_id(slug, "milestone", str(i)),
                "year": m["year"],
                "date": f"{base_year + m['year']}-{month:02d}-01",
                "event": m["event"],
                "kind": m.get("kind"),
            }
        )

    for i, e in enumerate(traj.encounters):
        if e["year"] > years:
            continue
        quarter = int(e.get("quarter", 1))
        month = (quarter - 1) * 3 + 2
        records.append(
            {
                "record_type": "encounter",
                "id": stable_id(slug, "trajectory_encounter", str(i)),
                "year": e["year"],
                "date": f"{base_year + e['year']}-{month:02d}-15",
                "kind": e.get("kind", "outpatient"),
                "service": e["service"],
                "provider": e.get("provider"),
                "specialty": e.get("specialty"),
                "location": e.get("location"),
                "outcome": e.get("outcome"),
            }
        )

    for i, m in enumerate(traj.medications):
        records.append(
            {
                "record_type": "medication_period",
                "id": stable_id(slug, "medication_period", str(i)),
                "name": m["name"],
                "start_year": m["start_year"],
                "end_year": m["end_year"],
                "start_calendar_year": base_year + m["start_year"],
                "end_calendar_year": base_year + m["end_year"],
                "detail": m.get("detail"),
            }
        )

    return records
