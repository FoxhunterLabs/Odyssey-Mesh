from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    """
    Geographic position with accuracy estimate.

    accuracy_m represents a 95% confidence radius.
    """
    lat: float
    lon: float
    accuracy_m: float

    def to_dict(self) -> dict:
        return {
            "lat": self.lat,
            "lon": self.lon,
            "accuracy_m": self.accuracy_m,
        }
