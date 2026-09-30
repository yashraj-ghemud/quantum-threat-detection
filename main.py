"""
main.py
=======
Entry point for the Quantum-Inspired Cyber Threat Detection system.
SIH26141 — Blockchain & Cybersecurity.

Phase 0: Foundation — verifies the environment, loads configuration,
seeds the RNG, and confirms the Qiskit Aer simulator is reachable.
Subsequent phases will register and execute their own pipelines here.

Usage
-----
    python main.py
    python main.py --seed 123
    python main.py --config path/to/custom_config.yaml

No AI/ML libraries are used in this project.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure src/ is on the Python path when running main.py directly
# (not needed when installed via pip / pyproject.toml, but useful for dev).
# ---------------------------------------------------------------------------
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from utils.config import ConfigLoader
from utils.logger import get_logger
from utils.reproducibility import set_seed, get_run_context
from config.settings import PROJECT_NAME, PROJECT_ID, VERSION, PHASE


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description=f"{PROJECT_NAME} ({PROJECT_ID}) — {PHASE}",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed override (default: value from config YAML).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a custom quantum_config.yaml.",
    )
    return parser.parse_args()


def check_aer_available() -> bool:
    """Verify that Qiskit Aer is importable and the default backend exists.

    Returns
    -------
    bool
        ``True`` if Aer is available, ``False`` otherwise.
    """
    try:
        from qiskit_aer import AerSimulator  # noqa: F401
        _ = AerSimulator()
        return True
    except Exception:  # pragma: no cover
        return False


def run_phase0(cfg: ConfigLoader, log: object) -> None:
    """Execute Phase 0 environment verification.

    Parameters
    ----------
    cfg:
        Loaded configuration object.
    log:
        Logger instance.
    """
    log.info("=" * 60)
    log.info("  %s", PROJECT_NAME)
    log.info("  %s  |  v%s  |  %s", PROJECT_ID, VERSION, PHASE)
    log.info("=" * 60)

    # Seed
    applied_seed = set_seed(cfg.random_seed)
    ctx = get_run_context(applied_seed)
    log.info("Reproducibility  : seed=%d  numpy=%s", ctx["seed"], ctx["numpy_version"])

    # Config summary
    log.info("Simulator backend: %s  (shots=%d)", cfg.simulator_backend, cfg.shots)
    log.info("Measurement bases: %s", cfg.measurement_bases)
    log.info("Active phases    : %s", {k: v for k, v in cfg.phase_flags.items() if v})

    # Aer check
    aer_ok = check_aer_available()
    if aer_ok:
        log.info("Qiskit Aer       : available ✓")
    else:  # pragma: no cover
        log.warning("Qiskit Aer       : NOT available — install qiskit-aer")

    log.info("-" * 60)
    log.info("Phase 0 foundation check complete.")
    log.info("Proceed to Phase 1 to implement Bell states and entanglement.")
    log.info("=" * 60)


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Load configuration
    cfg = ConfigLoader(config_path=args.config)

    # Initialise logger (uses level from config)
    import logging
    logging.root.setLevel(getattr(logging, cfg.log_level, logging.INFO))
    log = get_logger(__name__)

    # Seed override from CLI
    if args.seed is not None:
        cfg._data["random_seed"] = args.seed  # override in-memory only

    run_phase0(cfg, log)


if __name__ == "__main__":
    main()
