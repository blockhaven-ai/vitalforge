"""Daily signal generators.

Each generator is a pure function of its config, day count, start datetime,
and a ``random.Random`` instance, returning a list of plain-dict signal
records. Generation order and RNG consumption are fixed, so the same seed
always produces identical output.

Signal record shape::

    {
        "record_type": "signal",
        "signal": "<heart_rate|blood_pressure|steps|sleep|glucose|weight|activity_energy>",
        "start": "<ISO 8601 UTC>",
        "end": "<ISO 8601 UTC>",
        "unit": "<unit>",
        "samples": [...],          # all signals except sleep
        "episodes": [...],         # sleep only
    }
"""

from __future__ import annotations

import datetime
import math
import random
from typing import List, Optional

from vitalforge.ids import stable_id
from vitalforge.personas import (
    BloodPressureConfig,
    EnergyConfig,
    GlucoseConfig,
    HeartRateConfig,
    Persona,
    SleepConfig,
    StepsConfig,
    WeightConfig,
)

HR_CLAMP = (45.0, 190.0)
SYSTOLIC_CLAMP = (90, 200)
DIASTOLIC_CLAMP = (50, 130)
GLUCOSE_CLAMP = (70.0, 250.0)

#: Stage fractions within each ~90-minute sleep cycle (simplified fixed split).
SLEEP_STAGE_FRACTIONS = (("light", 0.50), ("deep", 0.25), ("rem", 0.25))
SLEEP_CYCLE_MINUTES = 90.0


def iso_utc(dt: datetime.datetime) -> str:
    """Format a naive datetime as an ISO 8601 UTC timestamp."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def circadian_factor(hour: float) -> float:
    """Return a 0..1 circadian factor: lowest near 03:00, highest near 15:00."""
    return 0.5 + 0.5 * math.sin((hour - 3) * math.pi / 12)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def generate_heart_rate(
    cfg: HeartRateConfig, days: int, start: datetime.datetime, rng: random.Random
) -> List[dict]:
    """Sample heart rate through each day with sleep, circadian, and exercise regimes.

    Hours 22:00-06:00 draw from the sleep distribution; otherwise samples draw
    from the resting distribution shifted by a circadian factor, with an
    ``exercise_probability`` chance per sample of an exercise burst.
    """
    records = []
    interval_min = 1440 // cfg.samples_per_day
    for day in range(days):
        day_start = start + datetime.timedelta(days=day)
        samples = []
        for s in range(cfg.samples_per_day):
            t = day_start + datetime.timedelta(minutes=s * interval_min)
            hour = t.hour + t.minute / 60.0
            if hour >= 22 or hour < 6:
                value = rng.gauss(cfg.sleep_mean, cfg.sleep_std)
            elif rng.random() < cfg.exercise_probability:
                value = rng.gauss(cfg.active_mean, cfg.active_std)
            else:
                base = cfg.resting_mean + 10 * circadian_factor(hour)
                value = rng.gauss(base, cfg.resting_std)
            samples.append({"t": iso_utc(t), "value": round(_clamp(value, *HR_CLAMP), 1)})
        records.append(
            {
                "record_type": "signal",
                "signal": "heart_rate",
                "start": iso_utc(day_start),
                "end": iso_utc(day_start + datetime.timedelta(days=1)),
                "unit": "bpm",
                "samples": samples,
            }
        )
    return records


def generate_blood_pressure(
    cfg: BloodPressureConfig, days: int, start: datetime.datetime, rng: random.Random
) -> List[dict]:
    """Generate BP readings following a linear trend from start to end values.

    Readings are spread across the day (first at 07:00, last at 19:00) with
    gaussian noise around the day's interpolated baseline.
    """
    records = []
    for day in range(days):
        day_start = start + datetime.timedelta(days=day)
        progress = day / max(days - 1, 1)
        sys_base = cfg.systolic_start + (cfg.systolic_end - cfg.systolic_start) * progress
        dia_base = cfg.diastolic_start + (cfg.diastolic_end - cfg.diastolic_start) * progress
        samples = []
        for r in range(cfg.readings_per_day):
            hour = 7 if r == 0 else 19
            t = day_start + datetime.timedelta(hours=hour, minutes=rng.randint(0, 30))
            systolic = int(_clamp(round(rng.gauss(sys_base, cfg.std)), *SYSTOLIC_CLAMP))
            diastolic = int(_clamp(round(rng.gauss(dia_base, cfg.std * 0.7)), *DIASTOLIC_CLAMP))
            samples.append({"t": iso_utc(t), "systolic": systolic, "diastolic": diastolic})
        records.append(
            {
                "record_type": "signal",
                "signal": "blood_pressure",
                "start": iso_utc(day_start),
                "end": iso_utc(day_start + datetime.timedelta(days=1)),
                "unit": "mmHg",
                "samples": samples,
            }
        )
    return records


def generate_steps(
    cfg: StepsConfig, days: int, start: datetime.datetime, rng: random.Random
) -> List[dict]:
    """Generate one daily step total with separate weekday/weekend distributions."""
    records = []
    for day in range(days):
        day_start = start + datetime.timedelta(days=day)
        is_weekend = day_start.weekday() >= 5
        mean = cfg.weekend_mean if is_weekend else cfg.weekday_mean
        std = cfg.weekend_std if is_weekend else cfg.weekday_std
        steps = max(0, round(rng.gauss(mean, std)))
        records.append(
            {
                "record_type": "signal",
                "signal": "steps",
                "start": iso_utc(day_start),
                "end": iso_utc(day_start + datetime.timedelta(days=1)),
                "unit": "steps",
                "samples": [{"t": iso_utc(day_start), "value": steps}],
            }
        )
    return records


def generate_sleep(
    cfg: SleepConfig, days: int, start: datetime.datetime, rng: random.Random
) -> List[dict]:
    """Generate nightly sleep episodes built from ~90-minute stage cycles.

    Each night: bedtime and total duration are sampled, a 5-20 minute latency
    precedes sleep onset, then full cycles of light/deep/REM stages partition
    the sleep window exactly (the final cycle is truncated to fit). Episode
    durations therefore sum to ``total_sleep_min``.
    """
    records = []
    for day in range(days):
        bedtime_hour = rng.gauss(cfg.bedtime_hour, cfg.bedtime_std)
        duration_hours = max(4.0, rng.gauss(cfg.duration_mean_hours, cfg.duration_std_hours))
        latency_min = rng.uniform(5.0, 20.0)

        bed = start + datetime.timedelta(days=day, hours=bedtime_hour)
        onset = bed + datetime.timedelta(minutes=latency_min)
        total_sleep_min = duration_hours * 60.0
        wake = onset + datetime.timedelta(minutes=total_sleep_min)

        episodes = []
        t = onset
        remaining = total_sleep_min
        while remaining > 1e-9:
            cycle = min(SLEEP_CYCLE_MINUTES, remaining)
            for stage, fraction in SLEEP_STAGE_FRACTIONS:
                duration = cycle * fraction
                end = t + datetime.timedelta(minutes=duration)
                episodes.append(
                    {
                        "stage": stage,
                        "start": iso_utc(t),
                        "end": iso_utc(end),
                        "duration_min": round(duration, 2),
                    }
                )
                t = end
            remaining -= cycle

        records.append(
            {
                "record_type": "signal",
                "signal": "sleep",
                "start": iso_utc(bed),
                "end": iso_utc(wake),
                "unit": "min",
                "sleep_onset": iso_utc(onset),
                "latency_min": round(latency_min, 2),
                "total_sleep_min": round(total_sleep_min, 2),
                "episodes": episodes,
            }
        )
    return records


def generate_glucose(
    cfg: GlucoseConfig, days: int, start: datetime.datetime, rng: random.Random
) -> List[dict]:
    """Generate fasting (07:00) and postprandial (13:00, 19:00) glucose readings.

    ``trend_mg_dl`` shifts both baselines linearly over the full period
    (negative values model improvement).
    """
    records = []
    schedule = (
        (7, "fasting", cfg.fasting_mean, cfg.fasting_std),
        (13, "postprandial", cfg.postprandial_mean, cfg.postprandial_std),
        (19, "postprandial", cfg.postprandial_mean, cfg.postprandial_std),
    )
    for day in range(days):
        day_start = start + datetime.timedelta(days=day)
        progress = day / max(days - 1, 1)
        samples = []
        for hour, context, mean, std in schedule:
            adjusted = mean + cfg.trend_mg_dl * progress
            t = day_start + datetime.timedelta(hours=hour, minutes=rng.randint(0, 30))
            value = round(_clamp(rng.gauss(adjusted, std), *GLUCOSE_CLAMP), 1)
            samples.append({"t": iso_utc(t), "value": value, "context": context})
        records.append(
            {
                "record_type": "signal",
                "signal": "glucose",
                "start": iso_utc(day_start),
                "end": iso_utc(day_start + datetime.timedelta(days=1)),
                "unit": "mg/dL",
                "samples": samples,
            }
        )
    return records


def generate_weight(
    cfg: WeightConfig, days: int, start: datetime.datetime, rng: random.Random
) -> List[dict]:
    """Generate weight readings interpolated linearly from start to end weight."""
    records = []
    interval_days = max(1, 7 // cfg.readings_per_week)
    for day in range(0, days, interval_days):
        day_start = start + datetime.timedelta(days=day)
        progress = day / max(days - 1, 1)
        base = cfg.start_kg + (cfg.end_kg - cfg.start_kg) * progress
        t = day_start + datetime.timedelta(hours=7, minutes=rng.randint(0, 30))
        value = round(rng.gauss(base, cfg.std), 1)
        records.append(
            {
                "record_type": "signal",
                "signal": "weight",
                "start": iso_utc(t),
                "end": iso_utc(t),
                "unit": "kg",
                "samples": [{"t": iso_utc(t), "value": value}],
            }
        )
    return records


def generate_activity_energy(
    cfg: EnergyConfig, days: int, start: datetime.datetime, rng: random.Random
) -> List[dict]:
    """Generate one daily active-energy total with weekday/weekend distributions."""
    records = []
    for day in range(days):
        day_start = start + datetime.timedelta(days=day)
        is_weekend = day_start.weekday() >= 5
        mean = cfg.weekend_mean_kcal if is_weekend else cfg.weekday_mean_kcal
        std = cfg.weekend_std if is_weekend else cfg.weekday_std
        kcal = max(0, round(rng.gauss(mean, std)))
        records.append(
            {
                "record_type": "signal",
                "signal": "activity_energy",
                "start": iso_utc(day_start),
                "end": iso_utc(day_start + datetime.timedelta(days=1)),
                "unit": "kcal",
                "samples": [{"t": iso_utc(day_start), "value": kcal}],
            }
        )
    return records


def generate_signals(
    persona: Persona,
    days: int,
    rng: random.Random,
    start_date: Optional[datetime.date] = None,
) -> List[dict]:
    """Generate all configured signals for a persona, in a fixed order.

    Order: heart_rate, blood_pressure, steps, sleep, glucose, weight,
    activity_energy. Records receive deterministic ``id`` fields.
    """
    base = start_date or persona.start_date
    start = datetime.datetime(base.year, base.month, base.day)
    b = persona.baseline
    records: List[dict] = []
    if b.heart_rate:
        records.extend(generate_heart_rate(b.heart_rate, days, start, rng))
    if b.blood_pressure:
        records.extend(generate_blood_pressure(b.blood_pressure, days, start, rng))
    if b.steps:
        records.extend(generate_steps(b.steps, days, start, rng))
    if b.sleep:
        records.extend(generate_sleep(b.sleep, days, start, rng))
    if b.glucose:
        records.extend(generate_glucose(b.glucose, days, start, rng))
    if b.weight:
        records.extend(generate_weight(b.weight, days, start, rng))
    if b.activity_energy:
        records.extend(generate_activity_energy(b.activity_energy, days, start, rng))

    for record in records:
        record["id"] = stable_id(persona.slug, record["signal"], record["start"])
    return records
