from typing import Dict, List, Optional, Set, Tuple

from .evidence_record import EvidenceRecord


class MeshStore:
    """
    Content-addressed store with deduplication and absence tracking.

    Invariants:
    - Never mutates EvidenceRecords
    - Deduplicates globally by record.hash
    - Tracks per-node knowledge sets (who knows what)
    - Tracks per-(node,window) last-seen tick for absence signaling
    """

    def __init__(self) -> None:
        self.records_by_hash: Dict[str, EvidenceRecord] = {}
        self.known_by_node: Dict[str, Set[str]] = {}
        self.absence_tracker: Dict[Tuple[str, int], int] = {}  # (node_id, window_id) -> last_active_tick

    def ensure_node(self, node_id: str) -> None:
        if node_id not in self.known_by_node:
            self.known_by_node[node_id] = set()

    def ingest(self, receiver_node_id: str, record: EvidenceRecord) -> bool:
        """
        Store record globally; mark as known by receiver.
        Returns True if record is new *to receiver*.
        """
        self.ensure_node(receiver_node_id)

        # Store globally (dedupe by hash)
        if record.hash not in self.records_by_hash:
            self.records_by_hash[record.hash] = record

        # Mark as known by receiver
        if record.hash in self.known_by_node[receiver_node_id]:
            return False

        self.known_by_node[receiver_node_id].add(record.hash)

        # Presence signal: node emitted evidence for this window
        key = (record.node_id, record.window_id)
        self.absence_tracker[key] = record.tick_id

        return True

    def get_missing_hashes(self, node_a: str, node_b: str) -> Tuple[Set[str], Set[str]]:
        """
        Hashes known by A not B, and known by B not A.
        """
        self.ensure_node(node_a)
        self.ensure_node(node_b)
        a = self.known_by_node[node_a]
        b = self.known_by_node[node_b]
        return (a - b, b - a)

    def fetch_records(self, hashes: Set[str]) -> List[EvidenceRecord]:
        out: List[EvidenceRecord] = []
        for h in hashes:
            rec = self.records_by_hash.get(h)
            if rec:
                out.append(rec)
        return out

    def all_records(self) -> List[EvidenceRecord]:
        """
        Deterministic ordering: (tick_id, node_id, hash)
        """
        records = list(self.records_by_hash.values())
        records.sort(key=lambda r: (r.tick_id, r.node_id, r.hash))
        return records

    def get_records_by_node(self, node_id: str) -> List[EvidenceRecord]:
        return [r for r in self.records_by_hash.values() if r.node_id == node_id]

    def get_absent_nodes(
        self,
        window_id: int,
        current_tick: int,
        grace_ticks: int = 10,
    ) -> List[Tuple[str, int]]:
        """
        Return nodes absent in window and ticks since last seen.

        grace_ticks:
        - allow late arrival before calling them "absent"
        """
        absent: List[Tuple[str, int]] = []
        for node_id in self.known_by_node.keys():
            key = (node_id, window_id)
            last_seen = self.absence_tracker.get(key)

            if last_seen is None:
                # never seen in this window
                absent.append((node_id, current_tick))
            elif current_tick - last_seen > grace_ticks:
                # not seen recently
                absent.append((node_id, current_tick - last_seen))

        return absent

    def get_node_health_stats(self) -> Dict[str, Dict[str, float]]:
        """
        Convenience: latest health stats by node.
        """
        stats: Dict[str, Dict[str, float]] = {}
        for node_id in self.known_by_node:
            records = self.get_records_by_node(node_id)
            if not records:
                continue

            latest = max(records, key=lambda r: r.tick_id)
            stats[node_id] = {
                "sensor_health": latest.sensor_health,
                "clock_drift_ms": latest.clock_drift_ms,
                "position_accuracy_m": latest.position_accuracy_m,
                "calibration_status": 1.0 if latest.calibration_status == "nominal" else 0.5,
            }
        return stats
