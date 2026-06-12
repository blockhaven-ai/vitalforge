"""Dataset assembly: combine persona, signals, clinical, and trajectory
records into a single serializable document with generator metadata."""

from __future__ import annotations

import datetime
import random
from typing import Optional

from vitalforge.clinical import build_clinical_records
from vitalforge.personas import Persona
from vitalforge.signals import generate_signals
from vitalforge.trajectory import build_trajectory_records

GENERATOR_NAME = "vitalforge"
GENERATOR_VERSION = "0.1.0"


def _persona_block(persona: Persona) -> dict:
    return {
        "name": persona.profile.name,
        "slug": persona.slug,
        "birth_date": persona.profile.birth_date.isoformat(),
        "sex": persona.profile.sex,
        "height_cm": persona.profile.height_cm,
    }


def build_dataset(
    persona: Persona,
    days: int,
    seed: int,
    start_date: Optional[datetime.date] = None,
) -> dict:
    """Generate a daily-resolution dataset for ``days`` days.

    The same persona, days, seed, and start date always produce an identical
    dataset.
    """
    rng = random.Random(seed)
    effective_start = start_date or persona.start_date
    signals = generate_signals(persona, days, rng, start_date=effective_start)
    clinical = build_clinical_records(persona)
    return {
        "generator": {
            "name": GENERATOR_NAME,
            "version": GENERATOR_VERSION,
            "mode": "generate",
            "seed": seed,
            "days": days,
            "start_date": effective_start.isoformat(),
        },
        "persona": _persona_block(persona),
        "signals": signals,
        "clinical": clinical,
    }


def build_trajectory_dataset(persona: Persona, years: int, seed: int) -> dict:
    """Generate a multi-year trajectory dataset (year 0 through ``years``)."""
    rng = random.Random(seed)
    records = build_trajectory_records(persona, years, rng)
    return {
        "generator": {
            "name": GENERATOR_NAME,
            "version": GENERATOR_VERSION,
            "mode": "trajectory",
            "seed": seed,
            "years": years,
            "start_date": persona.start_date.isoformat(),
        },
        "persona": _persona_block(persona),
        "trajectory": records,
    }
