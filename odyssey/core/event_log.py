import json
from typing import Dict, List, Optional

from .utils import utc_now_iso


class EventLog:
    """
    Append-only event log.

    Invariants:
    - Events are added, never mutated
    - Designed for audit and replay
    """

    def __init__(self) -> None:
        self.events: List[dict] = []

    def append(self, event_type: str, payload: dict, tick_id: Optional[int] = None) -> None:
        event = {
            "timestamp_utc": utc_now_iso(),
            "tick_id": tick_id,
            "type": event_type,
            "payload": payload,
        }
        self.events.append(event)

    def tail(self, n: int = 50) -> List[dict]:
        return self.events[-n:] if self.events else []

    def filter_by_type(self, event_type: str) -> List[dict]:
        return [e for e in self.events if e["type"] == event_type]

    def count_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for e in self.events:
            t = e.get("type", "unknown")
            counts[t] = counts.get(t, 0) + 1
        return counts

    def export_jsonl(self) -> str:
        """
        Export in JSON Lines format (one event per line).
        """
        return "\n".join(json.dumps(e, separators=(",", ":")) for e in self.events)

    def clear(self) -> None:
        """
        Clear the log.

        WARNING:
        Only use for resets in simulation / tests.
        """
        self.events.clear()
