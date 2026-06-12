"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from vitalforge.personas import Persona, load_persona

REPO_ROOT = Path(__file__).resolve().parent.parent
PERSONA_DIR = REPO_ROOT / "examples" / "personas"
ALEX = PERSONA_DIR / "alex_rivera.yaml"
JORDAN = PERSONA_DIR / "jordan_kim.yaml"


@pytest.fixture
def alex_persona() -> Persona:
    return load_persona(ALEX)


@pytest.fixture
def jordan_persona() -> Persona:
    return load_persona(JORDAN)
