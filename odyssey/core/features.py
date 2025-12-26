from dataclasses import dataclass, field
from typing import Dict, Optional

from .evidence_types import EvidenceType
from .geometry import Position


@dataclass(frozen=True)
class MaritimeFeatures:
    """
    Feature summary for maritime evidence.

    IMPORTANT:
    - Frozen for replay stability
    - Represents feature extraction only, not classification
    """
    evidence_type: EvidenceType
    frequency_hz: float = 0.0
    bandwidth_hz: float = 0.0
    bearing_deg: float = 0.0
    bearing_accuracy_deg: float = 10.0
    snr_db: float = 0.0
    doppler_shift_hz: float = 0.0
    position: Optional[Position] = None
    classification_confidence: float = 0.0
    signal_characteristics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        base = {
            "evidence_type": self.evidence_type.value,
            "frequency_hz": self.frequency_hz,
            "bandwidth_hz": self.bandwidth_hz,
            "bearing_deg": self.bearing_deg,
            "bearing_accuracy_deg": self.bearing_accuracy_deg,
            "snr_db": self.snr_db,
            "doppler_shift_hz": self.doppler_shift_hz,
            "classification_confidence": self.classification_confidence,
            "signal_characteristics": self.signal_characteristics,
        }
        if self.position:
            base["position"] = self.position.to_dict()
        return base
