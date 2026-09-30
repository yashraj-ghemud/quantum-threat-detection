"""
sentinel
========
QVeris Sentinel: a teleportation-based Quantum Digital Signature (TQDS) engine
and the QSentinel quantum-inspired threat-detection framework.

SIH26141 | Blockchain & Cybersecurity.

The package is pure NumPy/SciPy. Qiskit is used only to *validate* the engine
(see :mod:`sentinel.analysis.validation`), never on the hot path.

Layout
------
- ``states``, ``linalg``, ``channels``   single-qubit algebra and channel library
- ``teleport``                           exact teleportation superoperators + sampler
- ``bell``                               Bell-pair statistics, CHSH and witness
- ``tomography``                         Pauli-frame de-twirling channel tomography
- ``stats``, ``sequential``              statistical toolkit, SPRT/CUSUM/EWMA
- ``protocol``                           the TQDS protocol (keys, distribution, signing, verification)
- ``adversary``                          attack catalog and adversary models
- ``detection``                          detectors, fingerprinting, fusion, monitors
- ``analysis``                           security/forgery analysis, evaluation jobs
- ``ledger``                             hash chain + Merkle tree primitives

No AI/ML is used anywhere in this package.
"""

import logging as _logging

__version__ = "2.0.0"

# v1's utils.logger configures the root logger at INFO; Qiskit's transpiler is
# very chatty at that level. Keep third-party numerics at WARNING.
for _name in ("qiskit", "qiskit_aer", "stevedore"):
    _logging.getLogger(_name).setLevel(_logging.WARNING)
ENGINE_NAME = "QVeris Sentinel"

__all__ = ["__version__", "ENGINE_NAME"]
