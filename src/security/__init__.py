"""
security -- Quantum-based threat detection package.

Phase 4 -- SIH26141 | Blockchain & Cybersecurity.

Modules
-------
statistics  : Measurement statistics from binary QDS outcomes (Phase 4)
fingerprint : Session fingerprinting from verification results (Phase 4)
anomaly     : Deterministic anomaly scoring bounded [0,1] (Phase 4)
thresholds  : Percentile/sigma threshold calibration (Phase 4)
detector    : ThreatDetector engine, NORMAL/SUSPICIOUS/THREAT (Phase 4)
"""

from security.statistics import (
    MeasurementStats,
    BasisStats,
    compute_measurement_stats,
    compute_basis_stats,
    stats_from_verification,
)

from security.fingerprint import (
    BasisFingerprint,
    SessionFingerprint,
    build_fingerprint,
    build_baseline_fingerprint,
)

from security.anomaly import (
    AnomalyBreakdown,
    ANOMALY_WEIGHTS,
    compute_anomaly_score,
    compute_anomaly_breakdown,
    z_score_mismatch,
)

from security.thresholds import (
    ThresholdConfig,
    CalibrationResult,
    DEFAULT_WARNING_THRESHOLD,
    DEFAULT_CRITICAL_THRESHOLD,
    percentile_calibrate,
    sigma_calibrate,
    fixed_calibrate,
)

from security.detector import (
    DetectionResult,
    ThreatDetector,
    Classification,
    NORMAL,
    SUSPICIOUS,
    THREAT,
)

__all__: list[str] = [
    # statistics
    "MeasurementStats", "BasisStats",
    "compute_measurement_stats", "compute_basis_stats", "stats_from_verification",
    # fingerprint
    "BasisFingerprint", "SessionFingerprint",
    "build_fingerprint", "build_baseline_fingerprint",
    # anomaly
    "AnomalyBreakdown", "ANOMALY_WEIGHTS",
    "compute_anomaly_score", "compute_anomaly_breakdown", "z_score_mismatch",
    # thresholds
    "ThresholdConfig", "CalibrationResult",
    "DEFAULT_WARNING_THRESHOLD", "DEFAULT_CRITICAL_THRESHOLD",
    "percentile_calibrate", "sigma_calibrate", "fixed_calibrate",
    # detector
    "DetectionResult", "ThreatDetector", "Classification",
    "NORMAL", "SUSPICIOUS", "THREAT",
]
