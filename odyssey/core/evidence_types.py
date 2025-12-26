from enum import Enum


class EvidenceType(Enum):
    """
    Types of maritime evidence.

    NOTE:
    - Enum values are frozen for deterministic replay
    - Extensions must preserve existing values
    """
    ACOUSTIC_NARROWBAND = "acoustic_narrowband"
    ACOUSTIC_BROADBAND = "acoustic_broadband"
    RADAR_CONTACT = "radar_contact"
    AIS_SIGNAL = "ais_signal"
    IR_SIGNATURE = "ir_signature"
    ENVIRONMENTAL = "environmental"
    UNKNOWN = "unknown"
