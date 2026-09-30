"""
config/settings.py
==================
Centralised Python-level settings for Quantum-Inspired Cyber Threat Detection.
All hard-coded defaults mirror quantum_config.yaml; runtime values are loaded
from YAML by utils.config.ConfigLoader and override these defaults.

No AI/ML libraries are used anywhere in this project.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Project Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
CONFIG_DIR: Final[Path] = PROJECT_ROOT / "config"
CONFIG_FILE: Final[Path] = CONFIG_DIR / "quantum_config.yaml"
LOGS_DIR: Final[Path] = PROJECT_ROOT / "logs"
EXPERIMENTS_DIR: Final[Path] = PROJECT_ROOT / "experiments"
DOCS_DIR: Final[Path] = PROJECT_ROOT / "docs"

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
RANDOM_SEED: Final[int] = 42

# ---------------------------------------------------------------------------
# Quantum Simulator
# ---------------------------------------------------------------------------
SIMULATOR_BACKEND: Final[str] = "aer_simulator"
SHOTS: Final[int] = 1024
MAX_PARALLEL_THREADS: Final[int] = 4

# ---------------------------------------------------------------------------
# Measurement Bases (Pauli eigenstates)
# ---------------------------------------------------------------------------
BASIS_X: Final[str] = "x"
BASIS_Y: Final[str] = "y"
BASIS_Z: Final[str] = "z"
SUPPORTED_BASES: Final[tuple[str, ...]] = (BASIS_X, BASIS_Y, BASIS_Z)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: Final[str] = os.environ.get("QTD_LOG_LEVEL", "INFO")
LOG_FORMAT: Final[str] = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT: Final[str] = "%Y-%m-%dT%H:%M:%S"
LOG_TO_FILE: Final[bool] = False
LOG_FILE: Final[Path] = LOGS_DIR / "qtd.log"

# ---------------------------------------------------------------------------
# Circuit Defaults
# ---------------------------------------------------------------------------
DEFAULT_NUM_QUBITS: Final[int] = 2
ADD_BARRIERS: Final[bool] = True

# ---------------------------------------------------------------------------
# Project Metadata
# ---------------------------------------------------------------------------
PROJECT_NAME: Final[str] = "Quantum-Inspired Cyber Threat Detection"
PROJECT_ID: Final[str] = "SIH26141"
VERSION: Final[str] = "0.1.0"
PHASE: Final[str] = "Phase 0 — Foundation"
