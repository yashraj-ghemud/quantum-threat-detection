"""
utils/config.py
===============
YAML-based configuration loader for the Quantum-Inspired Cyber Threat Detection
project (SIH26141).

Loads ``config/quantum_config.yaml`` (or a caller-specified path) and merges
the values with the compiled defaults in ``config.settings``.  All access is
via typed properties so IDEs and type-checkers can surface mistakes early.

No AI/ML libraries are used in this project.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

# Resolve the default config file relative to the project root, not this file.
_DEFAULT_CONFIG: Path = (
    Path(__file__).resolve().parent.parent.parent / "config" / "quantum_config.yaml"
)

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Load and expose project-wide configuration from a YAML file.

    Parameters
    ----------
    config_path:
        Absolute or project-relative path to the YAML config file.
        Defaults to ``config/quantum_config.yaml``.

    Examples
    --------
    >>> cfg = ConfigLoader()
    >>> cfg.random_seed
    42
    >>> cfg.simulator_backend
    'aer_simulator'
    """

    def __init__(self, config_path: Path | str | None = None) -> None:
        self._path: Path = Path(config_path) if config_path else _DEFAULT_CONFIG
        self._data: dict[str, Any] = self._load()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        """Read and parse the YAML file.

        Returns
        -------
        dict[str, Any]
            Parsed configuration dictionary.

        Raises
        ------
        FileNotFoundError
            If the config file does not exist at the resolved path.
        yaml.YAMLError
            If the YAML content is malformed.
        """
        if not self._path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self._path}"
            )
        with self._path.open("r", encoding="utf-8") as fh:
            data: dict[str, Any] = yaml.safe_load(fh) or {}
        logger.debug("Configuration loaded from %s", self._path)
        return data

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a top-level config value by key.

        Parameters
        ----------
        key:
            Top-level YAML key.
        default:
            Value returned when the key is absent.
        """
        return self._data.get(key, default)

    def get_nested(self, *keys: str, default: Any = None) -> Any:
        """Retrieve a nested config value using a sequence of keys.

        Parameters
        ----------
        *keys:
            Ordered sequence of keys to traverse.
        default:
            Value returned when any key is absent.

        Examples
        --------
        >>> cfg.get_nested("simulator", "shots")
        1024
        """
        node: Any = self._data
        for k in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(k, default)
            if node is default:
                return default
        return node

    # ------------------------------------------------------------------
    # Typed convenience properties
    # ------------------------------------------------------------------

    @property
    def random_seed(self) -> int:
        """Global random seed for reproducibility."""
        return int(self._data.get("random_seed", 42))

    @property
    def simulator_backend(self) -> str:
        """Qiskit Aer simulator backend name."""
        return str(self.get_nested("simulator", "backend", default="aer_simulator"))

    @property
    def shots(self) -> int:
        """Number of measurement shots per circuit execution."""
        return int(self.get_nested("simulator", "shots", default=1024))

    @property
    def max_parallel_threads(self) -> int:
        """Maximum parallel threads for the Aer simulator."""
        return int(self.get_nested("simulator", "max_parallel_threads", default=4))

    @property
    def measurement_bases(self) -> dict[str, str]:
        """Mapping of basis label to Qiskit basis string (X/Y/Z)."""
        return dict(
            self._data.get(
                "measurement_bases", {"X": "x", "Y": "y", "Z": "z"}
            )
        )

    @property
    def log_level(self) -> str:
        """Logging level string (e.g. 'INFO')."""
        return str(self.get_nested("logging", "level", default="INFO")).upper()

    @property
    def log_format(self) -> str:
        """Python logging format string."""
        return str(
            self.get_nested(
                "logging",
                "format",
                default="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            )
        )

    @property
    def log_date_format(self) -> str:
        """Date/time format used in log records."""
        return str(
            self.get_nested("logging", "date_format", default="%Y-%m-%dT%H:%M:%S")
        )

    @property
    def default_num_qubits(self) -> int:
        """Default qubit count for new circuits."""
        return int(self.get_nested("circuit", "num_qubits", default=2))

    @property
    def add_barriers(self) -> bool:
        """Whether to insert barriers between circuit stages."""
        return bool(self.get_nested("circuit", "barrier", default=True))

    # ------------------------------------------------------------------
    # Security-evaluation sample sizes
    # ------------------------------------------------------------------

    @property
    def n_legitimate_sessions(self) -> int:
        """Legitimate sessions to simulate for FAR/TN statistics."""
        return int(self.get_nested("evaluation", "n_legitimate_sessions", default=300))

    @property
    def n_attack_sessions_per_type(self) -> int:
        """Attack sessions to simulate per attack category."""
        return int(
            self.get_nested("evaluation", "n_attack_sessions_per_type", default=300)
        )

    @property
    def confidence_level(self) -> float:
        """Confidence level for reported FAR/FRR intervals."""
        return float(self.get_nested("evaluation", "confidence_level", default=0.95))

    @property
    def interval_method(self) -> str:
        """Binomial interval estimator: 'wilson' or 'clopper_pearson'."""
        return str(
            self.get_nested("evaluation", "interval_method", default="clopper_pearson")
        )

    @property
    def evaluation_signature_length(self) -> int:
        """Signature length used by the security-evaluation experiments."""
        return int(self.get_nested("evaluation", "signature_length", default=32))

    @property
    def n_baseline_sessions(self) -> int:
        """Sessions used to calibrate the detector before evaluation."""
        return int(self.get_nested("evaluation", "n_baseline_sessions", default=40))

    @property
    def phase_flags(self) -> dict[str, bool]:
        """Active/inactive status of each project phase."""
        return dict(self._data.get("phases", {}))

    def __repr__(self) -> str:
        return f"ConfigLoader(path={self._path!r}, seed={self.random_seed}, shots={self.shots})"
