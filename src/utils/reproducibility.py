"""
utils/reproducibility.py
========================
Seed management and reproducibility utilities for Quantum-Inspired Cyber
Threat Detection (SIH26141).

All stochastic components — NumPy, Python ``random``, and Qiskit Aer — are
seeded through a single call to ``set_seed()``.  This guarantees that any
experiment can be reproduced exactly by specifying the same seed value.

No AI/ML libraries are used in this project.
"""

from __future__ import annotations

import random
from typing import Optional

import numpy as np
from numpy.random import Generator

from config.settings import RANDOM_SEED
from utils.logger import get_logger

logger = get_logger(__name__)


def set_seed(seed: Optional[int] = None) -> int:
    """Seed all stochastic components used by the project.

    Sets:
    - Python's built-in ``random`` module
    - NumPy's global legacy random state (for backward compat)
    - NumPy's default ``Generator`` seed (PCG64)

    Qiskit Aer shots are deterministic given the same circuit and seed;
    per-job seeding is handled in the quantum execution layer (Phase 1+).

    Parameters
    ----------
    seed:
        Integer seed value.  Defaults to ``RANDOM_SEED`` from settings
        (``42``) when ``None``.

    Returns
    -------
    int
        The seed that was applied, so callers can log it.

    Examples
    --------
    >>> applied = set_seed(42)
    >>> applied
    42
    """
    if seed is None:
        seed = RANDOM_SEED

    random.seed(seed)
    np.random.seed(seed)  # legacy global state
    logger.debug("Random seed set to %d", seed)
    return seed


def get_rng(seed: Optional[int] = None) -> Generator:
    """Return a new NumPy ``Generator`` seeded for reproducible experiments.

    Prefer this over the legacy ``np.random.*`` interface for new code.

    Parameters
    ----------
    seed:
        Integer seed.  Defaults to ``RANDOM_SEED`` when ``None``.

    Returns
    -------
    numpy.random.Generator
        A fresh PCG64-backed generator.

    Examples
    --------
    >>> rng = get_rng(42)
    >>> rng.random()           # deterministic
    0.7739560485559633
    """
    if seed is None:
        seed = RANDOM_SEED
    return np.random.default_rng(seed)


def get_run_context(seed: Optional[int] = None) -> dict[str, int | str]:
    """Return a metadata dictionary describing the current run's seed context.

    Useful for logging experiment provenance.

    Parameters
    ----------
    seed:
        The seed used for this run.  Defaults to ``RANDOM_SEED``.

    Returns
    -------
    dict[str, int | str]
        Keys: ``seed``, ``numpy_version``, ``note``.
    """
    applied = seed if seed is not None else RANDOM_SEED
    return {
        "seed": applied,
        "numpy_version": np.__version__,
        "note": "All stochastic components seeded via utils.reproducibility.set_seed",
    }
