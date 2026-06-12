"""Distribution sanity tests for the signal generators."""

from __future__ import annotations

import datetime
import random

import pytest

from vitalforge.signals import (
    GLUCOSE_CLAMP,
    HR_CLAMP,
    generate_signals,
)

DAYS = 30


def _records(persona, signal: str, days: int = DAYS):
    rng = random.Random(7)
    return [r for r in generate_signals(persona, days, rng) if r["signal"] == signal]


def _hour(iso: str) -> int:
    return int(iso[11:13])


def test_heart_rate_within_physiologic_bounds(alex_persona):
    for rec in _records(alex_persona, "heart_rate"):
        for s in rec["samples"]:
            assert HR_CLAMP[0] <= s["value"] <= HR_CLAMP[1]


def test_heart_rate_circadian_dip(alex_persona):
    night, day = [], []
    for rec in _records(alex_persona, "heart_rate"):
        for s in rec["samples"]:
            hour = _hour(s["t"])
            if hour >= 22 or hour < 6:
                night.append(s["value"])
            elif 9 <= hour < 18:
                day.append(s["value"])
    assert night and day
    night_mean = sum(night) / len(night)
    day_mean = sum(day) / len(day)
    assert night_mean < day_mean - 5, (
        f"expected nocturnal dip: night mean {night_mean:.1f} vs day mean {day_mean:.1f}"
    )


def test_blood_pressure_trend_and_bounds(alex_persona):
    records = _records(alex_persona, "blood_pressure")
    assert len(records) == DAYS
    systolics = []
    for rec in records:
        for s in rec["samples"]:
            assert 90 <= s["systolic"] <= 200
            assert 50 <= s["diastolic"] <= 130
            assert s["systolic"] > s["diastolic"]
        systolics.append(sum(s["systolic"] for s in rec["samples"]) / len(rec["samples"]))
    first_week = sum(systolics[:7]) / 7
    last_week = sum(systolics[-7:]) / 7
    assert last_week < first_week, "configured downward trend not present"


def test_sleep_episodes_sum_to_total(alex_persona):
    for rec in _records(alex_persona, "sleep"):
        episode_sum = sum(ep["duration_min"] for ep in rec["episodes"])
        assert episode_sum == pytest.approx(rec["total_sleep_min"], abs=0.5)
        start = datetime.datetime.strptime(rec["sleep_onset"], "%Y-%m-%dT%H:%M:%SZ")
        end = datetime.datetime.strptime(rec["end"], "%Y-%m-%dT%H:%M:%SZ")
        window_min = (end - start).total_seconds() / 60
        assert episode_sum == pytest.approx(window_min, abs=1.5)


def test_sleep_stages_are_known(alex_persona):
    for rec in _records(alex_persona, "sleep"):
        for ep in rec["episodes"]:
            assert ep["stage"] in ("light", "deep", "rem")


def test_glucose_bounds_and_contexts(alex_persona):
    fasting, postprandial = [], []
    for rec in _records(alex_persona, "glucose"):
        for s in rec["samples"]:
            assert GLUCOSE_CLAMP[0] <= s["value"] <= GLUCOSE_CLAMP[1]
            if s["context"] == "fasting":
                fasting.append(s["value"])
            else:
                postprandial.append(s["value"])
    assert len(fasting) == DAYS
    assert len(postprandial) == 2 * DAYS
    assert sum(fasting) / len(fasting) < sum(postprandial) / len(postprandial)


def test_steps_positive_and_plausible(alex_persona):
    records = _records(alex_persona, "steps")
    assert len(records) == DAYS
    for rec in records:
        value = rec["samples"][0]["value"]
        assert 0 <= value < 50000


def test_weight_follows_configured_trajectory(alex_persona):
    records = _records(alex_persona, "weight")
    cfg = alex_persona.baseline.weight
    first = records[0]["samples"][0]["value"]
    last = records[-1]["samples"][0]["value"]
    assert first == pytest.approx(cfg.start_kg, abs=3 * cfg.std + 0.1)
    assert last == pytest.approx(cfg.end_kg, abs=3 * cfg.std + 0.6)


def test_only_configured_signals_generated(jordan_persona):
    rng = random.Random(1)
    signals = {r["signal"] for r in generate_signals(jordan_persona, 5, rng)}
    assert "glucose" not in signals  # jordan has no glucose baseline
    assert "heart_rate" in signals


def test_signal_ids_unique(alex_persona):
    rng = random.Random(3)
    records = generate_signals(alex_persona, DAYS, rng)
    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids))
