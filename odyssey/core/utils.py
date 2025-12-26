import json
import math
import hashlib
from typing import List
from datetime import datetime, timezone


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def stable_hash(obj) -> str:
    """
    Deterministic SHA-256 hash.

    - Sorts keys
    - Uses compact separators
    - Critical for replay integrity
    """
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, x))


def circular_mean(angles_deg: List[float]) -> float:
    """Circular mean of angles in degrees."""
    if not angles_deg:
        return 0.0

    angles_rad = [math.radians(a) for a in angles_deg]
    sin_sum = sum(math.sin(a) for a in angles_rad)
    cos_sum = sum(math.cos(a) for a in angles_rad)

    mean_rad = math.atan2(sin_sum, cos_sum)
    return math.degrees(mean_rad) % 360.0


def circular_std(angles_deg: List[float]) -> float:
    """Circular standard deviation in degrees."""
    if len(angles_deg) < 2:
        return 0.0

    angles_rad = [math.radians(a) for a in angles_deg]
    sin_sum = sum(math.sin(a) for a in angles_rad)
    cos_sum = sum(math.cos(a) for a in angles_rad)

    R = math.sqrt(sin_sum**2 + cos_sum**2) / len(angles_rad)
    if R > 0:
        return math.degrees(math.sqrt(-2 * math.log(R)))
    return 360.0
