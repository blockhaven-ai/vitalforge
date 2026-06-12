"""vitalforge: persona-driven synthetic longitudinal health data generator."""

from vitalforge.dataset import build_dataset, build_trajectory_dataset
from vitalforge.personas import Persona, PersonaError, load_persona

__version__ = "0.1.0"

__all__ = [
    "Persona",
    "PersonaError",
    "build_dataset",
    "build_trajectory_dataset",
    "load_persona",
    "__version__",
]
