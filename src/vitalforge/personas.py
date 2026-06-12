"""Persona configuration schema and loader.

A persona is a YAML or JSON document that describes a synthetic individual:
profile, per-signal baseline parameters, clinical history (conditions,
medications, allergies, immunizations, labs, encounters), and an optional
multi-year trajectory.  See ``examples/personas/`` and the README for the
documented schema.
"""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import yaml

SCHEMA_VERSION = 1
_VALID_SEX = ("female", "male", "other", "unknown")


class PersonaError(ValueError):
    """Raised when a persona document is missing or invalid."""


def _require(data: Mapping[str, Any], key: str, ctx: str) -> Any:
    if key not in data:
        raise PersonaError(f"{ctx}: missing required key '{key}'")
    return data[key]


def _number(value: Any, ctx: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PersonaError(f"{ctx}: expected a number, got {value!r}")
    return float(value)


def _date(value: Any, ctx: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError as exc:
        raise PersonaError(f"{ctx}: invalid ISO date {value!r}") from exc


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Profile:
    """Demographic profile of the synthetic individual."""

    name: str
    birth_date: datetime.date
    sex: str
    height_cm: Optional[float] = None

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "Profile":
        name = str(_require(data, "name", "profile"))
        birth = _date(_require(data, "birth_date", "profile"), "profile.birth_date")
        sex = str(_require(data, "sex", "profile"))
        if sex not in _VALID_SEX:
            raise PersonaError(f"profile.sex must be one of {_VALID_SEX}, got {sex!r}")
        height = data.get("height_cm")
        return Profile(
            name=name,
            birth_date=birth,
            sex=sex,
            height_cm=_number(height, "profile.height_cm") if height is not None else None,
        )


# ---------------------------------------------------------------------------
# Signal baseline configs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HeartRateConfig:
    """Parameters for circadian-aware heart rate sampling."""

    resting_mean: float
    resting_std: float
    active_mean: float
    active_std: float
    sleep_mean: float
    sleep_std: float
    samples_per_day: int = 72
    exercise_probability: float = 0.08


@dataclass(frozen=True)
class BloodPressureConfig:
    """Parameters for blood pressure with a linear start-to-end trend."""

    systolic_start: float
    systolic_end: float
    diastolic_start: float
    diastolic_end: float
    std: float
    readings_per_day: int = 2


@dataclass(frozen=True)
class StepsConfig:
    """Parameters for daily step counts with weekday/weekend variance."""

    weekday_mean: float
    weekday_std: float
    weekend_mean: float
    weekend_std: float


@dataclass(frozen=True)
class SleepConfig:
    """Parameters for nightly sleep episodes with ~90-minute stage cycles."""

    bedtime_hour: float
    bedtime_std: float
    duration_mean_hours: float
    duration_std_hours: float


@dataclass(frozen=True)
class GlucoseConfig:
    """Parameters for fasting and postprandial blood glucose readings."""

    fasting_mean: float
    fasting_std: float
    postprandial_mean: float
    postprandial_std: float
    trend_mg_dl: float = 0.0


@dataclass(frozen=True)
class WeightConfig:
    """Parameters for a linearly interpolated weight trajectory."""

    start_kg: float
    end_kg: float
    std: float
    readings_per_week: int = 2


@dataclass(frozen=True)
class EnergyConfig:
    """Parameters for daily active energy with weekday/weekend variance."""

    weekday_mean_kcal: float
    weekday_std: float
    weekend_mean_kcal: float
    weekend_std: float


_CONFIG_TYPES = {
    "heart_rate": HeartRateConfig,
    "blood_pressure": BloodPressureConfig,
    "steps": StepsConfig,
    "sleep": SleepConfig,
    "glucose": GlucoseConfig,
    "weight": WeightConfig,
    "activity_energy": EnergyConfig,
}


@dataclass(frozen=True)
class Baseline:
    """Per-signal baseline parameter blocks. Absent signals are not generated."""

    heart_rate: Optional[HeartRateConfig] = None
    blood_pressure: Optional[BloodPressureConfig] = None
    steps: Optional[StepsConfig] = None
    sleep: Optional[SleepConfig] = None
    glucose: Optional[GlucoseConfig] = None
    weight: Optional[WeightConfig] = None
    activity_energy: Optional[EnergyConfig] = None

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "Baseline":
        kwargs: dict[str, Any] = {}
        for key, cfg_type in _CONFIG_TYPES.items():
            block = data.get(key)
            if block is None:
                continue
            if not isinstance(block, Mapping):
                raise PersonaError(f"baseline.{key}: expected a mapping")
            try:
                kwargs[key] = cfg_type(**dict(block))
            except TypeError as exc:
                raise PersonaError(f"baseline.{key}: {exc}") from exc
        unknown = set(data) - set(_CONFIG_TYPES)
        if unknown:
            raise PersonaError(f"baseline: unknown signal blocks {sorted(unknown)}")
        return Baseline(**kwargs)


# ---------------------------------------------------------------------------
# Clinical definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Coding:
    """A code from a terminology system (e.g. SNOMED, ICD-10, RxNorm, LOINC, CVX)."""

    system: str
    code: str
    display: Optional[str] = None

    @staticmethod
    def from_dict(data: Mapping[str, Any], ctx: str) -> "Coding":
        return Coding(
            system=str(_require(data, "system", ctx)),
            code=str(_require(data, "code", ctx)),
            display=data.get("display"),
        )


def _codes(data: Mapping[str, Any], ctx: str) -> tuple:
    raw = data.get("codes", [])
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise PersonaError(f"{ctx}.codes: expected a list")
    return tuple(Coding.from_dict(c, f"{ctx}.codes") for c in raw)


@dataclass(frozen=True)
class ConditionDef:
    text: str
    codes: tuple = ()
    onset_date: Optional[str] = None

    @staticmethod
    def from_dict(data: Mapping[str, Any], idx: int) -> "ConditionDef":
        ctx = f"conditions[{idx}]"
        return ConditionDef(
            text=str(_require(data, "text", ctx)),
            codes=_codes(data, ctx),
            onset_date=data.get("onset_date"),
        )


@dataclass(frozen=True)
class MedicationDef:
    text: str
    codes: tuple = ()
    dose: Optional[Mapping[str, Any]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    @staticmethod
    def from_dict(data: Mapping[str, Any], idx: int) -> "MedicationDef":
        ctx = f"medications[{idx}]"
        return MedicationDef(
            text=str(_require(data, "text", ctx)),
            codes=_codes(data, ctx),
            dose=data.get("dose"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
        )


@dataclass(frozen=True)
class AllergyDef:
    text: str
    codes: tuple = ()
    onset_date: Optional[str] = None

    @staticmethod
    def from_dict(data: Mapping[str, Any], idx: int) -> "AllergyDef":
        ctx = f"allergies[{idx}]"
        return AllergyDef(
            text=str(_require(data, "text", ctx)),
            codes=_codes(data, ctx),
            onset_date=data.get("onset_date"),
        )


@dataclass(frozen=True)
class ImmunizationDef:
    text: str
    codes: tuple = ()
    date: Optional[str] = None

    @staticmethod
    def from_dict(data: Mapping[str, Any], idx: int) -> "ImmunizationDef":
        ctx = f"immunizations[{idx}]"
        return ImmunizationDef(
            text=str(_require(data, "text", ctx)),
            codes=_codes(data, ctx),
            date=data.get("date"),
        )


@dataclass(frozen=True)
class LabDef:
    text: str
    codes: tuple = ()
    value: Optional[float] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    date: Optional[str] = None

    @staticmethod
    def from_dict(data: Mapping[str, Any], idx: int) -> "LabDef":
        ctx = f"labs[{idx}]"
        value = data.get("value")
        return LabDef(
            text=str(_require(data, "text", ctx)),
            codes=_codes(data, ctx),
            value=_number(value, f"{ctx}.value") if value is not None else None,
            unit=data.get("unit"),
            reference_range=data.get("reference_range"),
            date=data.get("date"),
        )


@dataclass(frozen=True)
class EncounterDef:
    kind: str
    service: str
    time: str
    modality: str = "in_person"
    reason: Optional[str] = None
    providers: tuple = ()
    location: Optional[str] = None
    summary: Optional[str] = None

    @staticmethod
    def from_dict(data: Mapping[str, Any], idx: int) -> "EncounterDef":
        ctx = f"encounters[{idx}]"
        providers = data.get("providers", [])
        if not isinstance(providers, Sequence) or isinstance(providers, str):
            raise PersonaError(f"{ctx}.providers: expected a list")
        return EncounterDef(
            kind=str(_require(data, "kind", ctx)),
            service=str(_require(data, "service", ctx)),
            time=str(_require(data, "time", ctx)),
            modality=str(data.get("modality", "in_person")),
            reason=data.get("reason"),
            providers=tuple(dict(p) for p in providers),
            location=data.get("location"),
            summary=data.get("summary"),
        )


# ---------------------------------------------------------------------------
# Trajectory definition (multi-year)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrajectoryDef:
    """Multi-year trajectory: BP phases, named metric series, and events.

    ``metrics`` maps a metric name to a list of anchor points. Each point has
    a ``year`` plus either ``value`` (point estimate) or ``mean``/``std``
    (sampled with noise). Values between anchor years are linearly
    interpolated.
    """

    blood_pressure_phases: tuple = ()
    metrics: Mapping[str, tuple] = field(default_factory=dict)
    milestones: tuple = ()
    encounters: tuple = ()
    medications: tuple = ()

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "TrajectoryDef":
        ctx = "trajectory"
        bp = data.get("blood_pressure", {})
        phases = tuple(dict(p) for p in bp.get("phases", []))
        for i, phase in enumerate(phases):
            for key in ("year_start", "year_end", "systolic", "diastolic"):
                _require(phase, key, f"{ctx}.blood_pressure.phases[{i}]")

        metrics_raw = data.get("metrics", {})
        if not isinstance(metrics_raw, Mapping):
            raise PersonaError(f"{ctx}.metrics: expected a mapping")
        metrics: dict[str, tuple] = {}
        for name, points in metrics_raw.items():
            if not isinstance(points, Sequence) or not points:
                raise PersonaError(f"{ctx}.metrics.{name}: expected a non-empty list")
            for j, point in enumerate(points):
                _require(point, "year", f"{ctx}.metrics.{name}[{j}]")
                if "value" not in point and "mean" not in point:
                    raise PersonaError(
                        f"{ctx}.metrics.{name}[{j}]: needs 'value' or 'mean'"
                    )
            metrics[name] = tuple(dict(p) for p in points)

        milestones = tuple(dict(m) for m in data.get("milestones", []))
        for i, m in enumerate(milestones):
            _require(m, "year", f"{ctx}.milestones[{i}]")
            _require(m, "event", f"{ctx}.milestones[{i}]")

        encounters = tuple(dict(e) for e in data.get("encounters", []))
        for i, e in enumerate(encounters):
            _require(e, "year", f"{ctx}.encounters[{i}]")
            _require(e, "service", f"{ctx}.encounters[{i}]")

        medications = tuple(dict(m) for m in data.get("medications", []))
        for i, m in enumerate(medications):
            _require(m, "name", f"{ctx}.medications[{i}]")
            _require(m, "start_year", f"{ctx}.medications[{i}]")
            _require(m, "end_year", f"{ctx}.medications[{i}]")

        return TrajectoryDef(
            blood_pressure_phases=phases,
            metrics=metrics,
            milestones=milestones,
            encounters=encounters,
            medications=medications,
        )


# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Persona:
    """A fully parsed persona document."""

    profile: Profile
    start_date: datetime.date
    baseline: Baseline
    conditions: tuple = ()
    medications: tuple = ()
    allergies: tuple = ()
    immunizations: tuple = ()
    labs: tuple = ()
    encounters: tuple = ()
    trajectory: Optional[TrajectoryDef] = None
    schema_version: int = SCHEMA_VERSION

    @property
    def slug(self) -> str:
        """Filesystem-safe identifier derived from the persona name."""
        return re.sub(r"[^a-z0-9]+", "_", self.profile.name.lower()).strip("_")


def persona_from_dict(data: Mapping[str, Any]) -> Persona:
    """Build and validate a :class:`Persona` from a parsed document."""
    if not isinstance(data, Mapping):
        raise PersonaError("persona document must be a mapping")

    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise PersonaError(f"unsupported schema_version {version!r} (expected {SCHEMA_VERSION})")

    profile = Profile.from_dict(_require(data, "profile", "persona"))
    start = _date(_require(data, "start_date", "persona"), "start_date")
    baseline = Baseline.from_dict(data.get("baseline", {}) or {})

    def _seq(key: str, builder: Any) -> tuple:
        raw = data.get(key, []) or []
        if not isinstance(raw, Sequence) or isinstance(raw, str):
            raise PersonaError(f"{key}: expected a list")
        return tuple(builder(item, i) for i, item in enumerate(raw))

    trajectory_raw = data.get("trajectory")
    return Persona(
        profile=profile,
        start_date=start,
        baseline=baseline,
        conditions=_seq("conditions", ConditionDef.from_dict),
        medications=_seq("medications", MedicationDef.from_dict),
        allergies=_seq("allergies", AllergyDef.from_dict),
        immunizations=_seq("immunizations", ImmunizationDef.from_dict),
        labs=_seq("labs", LabDef.from_dict),
        encounters=_seq("encounters", EncounterDef.from_dict),
        trajectory=TrajectoryDef.from_dict(trajectory_raw) if trajectory_raw else None,
        schema_version=version,
    )


def load_persona(path: "str | Path") -> Persona:
    """Load a persona from a YAML (``.yaml``/``.yml``) or JSON (``.json``) file."""
    path = Path(path)
    if not path.exists():
        raise PersonaError(f"persona file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    elif path.suffix.lower() in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    else:
        raise PersonaError(f"unsupported persona file type: {path.suffix}")
    return persona_from_dict(data)
