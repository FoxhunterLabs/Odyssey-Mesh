import math
import random
from typing import Dict, List, Optional

from .evidence_types import EvidenceType
from .geometry import Position
from .features import MaritimeFeatures
from .evidence_record import EvidenceRecord
from .event_log import EventLog
from .mesh_store import MeshStore
from .utils import clamp


class OdysseyNode:
    """
    Deterministic node that produces EvidenceRecords.

    Invariants:
    - Emits evidence, never decisions
    - Confidence computation must be explainable from the record
    - No hidden fusion or access to other nodes' evidence
    """

    def __init__(
        self,
        node_id: str,
        node_type: str,
        position: Position,
        rng: random.Random,
        log: EventLog,
        store: MeshStore,
    ) -> None:
        self.node_id = node_id
        self.node_type = node_type
        self.position = position
        self.rng = rng
        self.log = log
        self.store = store

        self.tick_id = 0
        self.prev_hash: Optional[str] = None

        # Persistent state (part of replay state)
        self.clock_drift_ms = self.rng.uniform(-10, 10)
        self.sensor_health = self.rng.uniform(0.8, 1.0)
        self.calibration_status = "nominal"
        self.position_accuracy_m = 50.0

        # Node-specific parameters (deterministic from seed)
        self.detection_sensitivity = self.rng.uniform(0.7, 1.3)
        self.false_positive_rate = self.rng.uniform(0.01, 0.05)

        # Trend display only (not used in decision logic)
        self.recent_p_detect: List[float] = []

    def _update_node_state(self, tick_id: int) -> None:
        self.tick_id = tick_id

        # Clock drift random walk
        self.clock_drift_ms += self.rng.uniform(-0.5, 0.5)
        self.clock_drift_ms = clamp(self.clock_drift_ms, -50.0, 50.0)

        # Sensor health drift / occasional degradation or recovery
        if self.rng.random() < 0.01:
            self.sensor_health = clamp(self.sensor_health - self.rng.uniform(0.1, 0.3), 0.1, 1.0)
            self.calibration_status = "degraded"
        elif self.rng.random() < 0.02:
            self.sensor_health = clamp(self.sensor_health + self.rng.uniform(0.01, 0.05), 0.1, 1.0)
            if self.sensor_health > 0.9:
                self.calibration_status = "nominal"

        # Position accuracy variation (GPS quality)
        self.position_accuracy_m += self.rng.uniform(-5, 5)
        self.position_accuracy_m = clamp(self.position_accuracy_m, 10.0, 200.0)

    def _compute_features(self, simulated_environment: Dict) -> MaritimeFeatures:
        """
        Simulation-only feature extraction.

        In production, nodes sample physical sensors; this function
        represents that boundary.
        """
        target_present = bool(simulated_environment.get("target_present", False))
        target_range_km = float(simulated_environment.get("target_range_km", 10.0))
        target_bearing = float(simulated_environment.get("target_bearing_deg", 0.0))
        sea_state = int(simulated_environment.get("sea_state", 2))

        base_noise = 1.0 + (sea_state - 1) * 0.3

        signal_strength = 0.0
        if target_present:
            range_factor = max(0.1, 1.0 / (target_range_km / 5.0))
            signal_strength = self.rng.uniform(0.5, 1.5) * range_factor * self.sensor_health

        noise_sample = abs(self.rng.gauss(0, base_noise))
        total_signal = signal_strength + noise_sample

        snr_db = (
            10 * math.log10((signal_strength + 1e-6) / (noise_sample + 1e-6))
            if noise_sample > 0
            else 0.0
        )

        # Evidence type based on node type
        if self.node_type == "hydrophone":
            evidence_type = EvidenceType.ACOUSTIC_NARROWBAND
            frequency = 1000 + self.rng.uniform(-100, 100)
            bandwidth = 10 + self.rng.uniform(-2, 2)
        elif self.node_type == "radar":
            evidence_type = EvidenceType.RADAR_CONTACT
            frequency = 9400e6
            bandwidth = 1e6
        elif self.node_type == "ais_receiver":
            evidence_type = EvidenceType.AIS_SIGNAL
            frequency = 162e6
            bandwidth = 25e3
        elif self.node_type == "ir_camera":
            evidence_type = EvidenceType.IR_SIGNATURE
            frequency = 0.0
            bandwidth = 0.0
        else:
            evidence_type = EvidenceType.UNKNOWN
            frequency = 0.0
            bandwidth = 0.0

        bearing_accuracy = 5.0 + (1.0 - self.sensor_health) * 20.0
        measured_bearing = (target_bearing + self.rng.uniform(-bearing_accuracy, bearing_accuracy)) % 360.0

        node_position = self.position if self.position_accuracy_m < 100 else None

        return MaritimeFeatures(
            evidence_type=evidence_type,
            frequency_hz=frequency,
            bandwidth_hz=bandwidth,
            bearing_deg=measured_bearing,
            bearing_accuracy_deg=bearing_accuracy,
            snr_db=snr_db,
            doppler_shift_hz=self.rng.uniform(-5, 5),
            position=node_position,
            classification_confidence=self.sensor_health * 0.8 + 0.2,
            signal_characteristics={
                "peak_to_avg": total_signal / (noise_sample + 1e-6),
                "stability": self.rng.uniform(0.7, 1.0),
                "persistence": self.rng.uniform(0.5, 1.0),
            },
        )

    def _compute_p_detect_local(self, features: MaritimeFeatures) -> float:
        """
        Local confidence estimate (NOT a decision).
        """
        snr_factor = clamp(1.0 - math.exp(-features.snr_db / 10.0), 0.0, 1.0)
        health_factor = self.sensor_health**2
        drift_factor = 1.0 - clamp(abs(self.clock_drift_ms) / 100.0, 0.0, 0.3)
        pos_factor = 1.0 - clamp(self.position_accuracy_m / 200.0, 0.0, 0.5)
        sensitivity_factor = self.detection_sensitivity

        raw_p = snr_factor * health_factor * drift_factor * pos_factor * sensitivity_factor

        if self.rng.random() < self.false_positive_rate:
            raw_p = max(raw_p, self.rng.uniform(0.3, 0.6))

        return clamp(raw_p, 0.0, 1.0)

    def step(self, tick_id: int, window_id: int, simulated_environment: Dict) -> EvidenceRecord:
        """
        One deterministic tick: update internal state, sample environment,
        compute features, emit EvidenceRecord.
        """
        self._update_node_state(tick_id)

        features = self._compute_features(simulated_environment)
        p_detect = self._compute_p_detect_local(features)

        self.recent_p_detect.append(p_detect)
        if len(self.recent_p_detect) > 5:
            self.recent_p_detect.pop(0)

        explanations = [
            f"Node {self.node_id} ({self.node_type}) local confidence: {p_detect:.3f}",
            f"SNR: {features.snr_db:.1f} dB → SNR factor: {1.0 - math.exp(-features.snr_db/10.0):.3f}",
            f"Sensor health: {self.sensor_health:.3f} → Health factor: {self.sensor_health**2:.3f}",
            f"Clock drift: {self.clock_drift_ms:.1f} ms → Drift factor: {1.0 - clamp(abs(self.clock_drift_ms)/100.0, 0.0, 0.3):.3f}",
            f"Position accuracy: {self.position_accuracy_m:.1f} m → Position factor: {1.0 - clamp(self.position_accuracy_m/200.0, 0.0, 0.5):.3f}",
            f"Node sensitivity: {self.detection_sensitivity:.3f}",
            f"False positive rate: {self.false_positive_rate:.3f}",
            "THIS IS EVIDENCE, NOT A DETECTION DECISION",
        ]

        record = EvidenceRecord.build(
            node_id=self.node_id,
            node_type=self.node_type,
            tick_id=tick_id,
            window_id=window_id,
            p_detect_local=p_detect,
            features=features,
            sensor_health=self.sensor_health,
            clock_drift_ms=self.clock_drift_ms,
            position_accuracy_m=self.position_accuracy_m,
            calibration_status=self.calibration_status,
            explanations=explanations,
            prev_hash=self.prev_hash,
            raw_data_hash=f"raw_{tick_id}_{self.node_id}",
            processing_version="v1.0",
        )

        # Node ingests its own record
        self.store.ingest(self.node_id, record)
        self.prev_hash = record.hash

        self.log.append(
            "evidence_emit",
            {
                "node_id": self.node_id,
                "node_type": self.node_type,
                "tick": tick_id,
                "window": window_id,
                "record_id": record.record_id,
                "p_detect": p_detect,
                "hash": record.hash[:8],
                "features_type": features.evidence_type.value,
            },
            tick_id,
        )

        return record
