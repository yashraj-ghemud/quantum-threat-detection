"""
utils/validation.py
===================
Input validation helpers for the Quantum-Inspired Cyber Threat Detection
project (SIH26141).

All public functions raise ``ValueError`` (or ``TypeError``) with descriptive
messages rather than silently returning defaults, so errors surface early.

No AI/ML libraries are used in this project.
"""

from __future__ import annotations

from typing import Any

from config.settings import SUPPORTED_BASES
from utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Basis validation
# ---------------------------------------------------------------------------

def validate_basis(basis: Any) -> str:
    """Validate that *basis* is a supported Pauli measurement basis.

    Parameters
    ----------
    basis:
        Candidate basis value.  Expected to be one of ``'x'``, ``'y'``,
        ``'z'`` (case-insensitive).

    Returns
    -------
    str
        Normalised lowercase basis string.

    Raises
    ------
    TypeError
        If *basis* is not a string.
    ValueError
        If *basis* is not in ``SUPPORTED_BASES``.

    Examples
    --------
    >>> validate_basis("X")
    'x'
    >>> validate_basis("z")
    'z'
    """
    if not isinstance(basis, str):
        raise TypeError(
            f"Basis must be a string, got {type(basis).__name__!r}."
        )
    normalised = basis.strip().lower()
    if normalised not in SUPPORTED_BASES:
        raise ValueError(
            f"Unsupported basis {basis!r}. "
            f"Must be one of {sorted(SUPPORTED_BASES)}."
        )
    return normalised


# ---------------------------------------------------------------------------
# Shot count validation
# ---------------------------------------------------------------------------

def validate_shots(shots: Any) -> int:
    """Validate that *shots* is a positive integer.

    Parameters
    ----------
    shots:
        Candidate shot count value.

    Returns
    -------
    int
        Validated shot count.

    Raises
    ------
    TypeError
        If *shots* cannot be interpreted as an integer.
    ValueError
        If *shots* is less than 1.

    Examples
    --------
    >>> validate_shots(1024)
    1024
    """
    try:
        shots_int = int(shots)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"Shots must be an integer, got {type(shots).__name__!r}: {shots!r}."
        ) from exc
    if shots_int < 1:
        raise ValueError(f"Shots must be >= 1, got {shots_int}.")
    return shots_int


# ---------------------------------------------------------------------------
# Qubit count validation
# ---------------------------------------------------------------------------

def validate_num_qubits(num_qubits: Any, *, min_qubits: int = 1) -> int:
    """Validate that *num_qubits* is an integer >= *min_qubits*.

    Parameters
    ----------
    num_qubits:
        Candidate qubit count.
    min_qubits:
        Minimum acceptable value (default ``1``).

    Returns
    -------
    int
        Validated qubit count.

    Raises
    ------
    TypeError
        If *num_qubits* cannot be interpreted as an integer.
    ValueError
        If *num_qubits* < *min_qubits*.
    """
    try:
        n = int(num_qubits)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"num_qubits must be an integer, got {type(num_qubits).__name__!r}."
        ) from exc
    if n < min_qubits:
        raise ValueError(
            f"num_qubits must be >= {min_qubits}, got {n}."
        )
    return n


# ---------------------------------------------------------------------------
# Generic non-empty string validation
# ---------------------------------------------------------------------------

def validate_non_empty_string(value: Any, field_name: str = "value") -> str:
    """Validate that *value* is a non-empty string.

    Parameters
    ----------
    value:
        Candidate string.
    field_name:
        Human-readable field name used in error messages.

    Returns
    -------
    str
        Stripped, non-empty string.

    Raises
    ------
    TypeError
        If *value* is not a string.
    ValueError
        If *value* is empty or whitespace-only.
    """
    if not isinstance(value, str):
        raise TypeError(
            f"{field_name!r} must be a string, got {type(value).__name__!r}."
        )
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name!r} must not be empty or whitespace.")
    return stripped
