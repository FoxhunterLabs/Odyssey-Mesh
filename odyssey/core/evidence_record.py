from dataclasses import dataclass
from typing import List, Optional

from .features import MaritimeFeatures
from .utils import stable_hash, utc_now_iso, clamp


@dataclass(frozen=True)
class EvidenceRecord:
    """
    EvidenceRecord is the ONLY admissible unit of information
    in Odyssey Mesh.

    Invariants:
    - Immutable once created
    - Fully explainable
    - Deterministically hashable
    - Never expresses decisions
    """
    # Identity & timing
    record_id: str
    node_id: str
    node_type: str
    tick_id: int
    window_id: int
    timestamp_utc: str

    # Local perception only
    p_detect_local: float
    features: MaritimeFeatures

    # Node state
    sensor_health: float
    clock_drift_ms: float
    position_accuracy_m: float
    calibration_status: str

    # Explainability
    explanations: List[str]
    raw_data_hash: str
    processing_version: str

    # Integrity chain
    prev_hash: Optional[str]
    hash: str

    @staticmethod
    def build(
        *,
        node_id: str,
        node_type: str,
        tick_id: int,
        window_id: int,
        p_detect_local: float,
        features: MaritimeFeatures,
        sensor_health: float,
        clock_drift_ms: float,
        position_accuracy_m: float,
        calibration_status: str,
        explanations: List[str],
        prev_hash: Optional[str],
        raw_data_hash: str = "",
        processing_version: str = "v1.0",
    ) -> "EvidenceRecord":
        """
        Deterministically construct an EvidenceRecord.

        NOTE:
        Timestamp is included in hash and must be generated here.
        """
        base = {
            "node_id": node_id,
            "node_type": node_type,
            "tick_id": tick_id,
            "window_id": window_id,
            "timestamp_utc": utc_now_iso(),
            "p_detect_local": round(clamp(p_detect_local, 0.0, 1.0), 6),
            "features": features.to_dict(),
            "sensor_health": round(clamp(sensor_health, 0.0, 1.0), 6),
            "clock_drift_ms": round(clock_drift_ms, 3),
            "position_accuracy_m": round(position_accuracy_m, 1),
            "calibration_status": calibration_status,
            "explanations": explanations,
            "raw_data_hash": raw_data_hash,
            "processing_version": processing_version,
            "prev_hash": prev_hash,
        }

        full_hash = stable_hash(base)
        record_id = full_hash[:16]

        return EvidenceRecord(
            record_id=record_id,
            node_id=node_id,
            node_type=node_type,
            tick_id=tick_id,
            window_id=window_id,
            timestamp_utc=base["timestamp_utc"],
            p_detect_local=base["p_detect_local"],
            features=features,
            sensor_health=base["sensor_health"],
            clock_drift_ms=base["clock_drift_ms"],
            position_accuracy_m=base["position_accuracy_m"],
            calibration_status=calibration_status,
            explanations=explanations,
            raw_data_hash=raw_data_hash,
            processing_version=processing_version,
            prev_hash=prev_hash,
            hash=full_hash[:32],
        )

    def to_audit_dict(self) -> dict:
        """Compact representation for audit logs."""
        return {
            "record_id": self.record_id,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "tick_id": self.tick_id,
            "window_id": self.window_id,
            "p_detect_local": self.p_detect_local,
            "sensor_health": self.sensor_health,
            "clock_drift_ms": self.clock_drift_ms,
            "calibration_status": self.calibration_status,
            "evidence_type": self.features.evidence_type.value,
            "bearing_deg": self.features.bearing_deg,
            "snr_db": self.features.snr_db,
            "hash": self.hash,
            "prev_hash": self.prev_hash[:16] if self.prev_hash else None,
            "processing_version": self.processing_version,
        }
