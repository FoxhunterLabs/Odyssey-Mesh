from dataclasses import dataclass
from typing import Dict, List, Tuple

from .evidence_record import EvidenceRecord
from .mesh_store import MeshStore
from .utils import circular_mean, circular_std


@dataclass
class MeshView:
    """
    Reconciliation view - descriptive only.

    Invariants:
    - Shows distribution of evidence (not fusion)
    - Preserves disagreement and absence
    - Provides inspectable stats only
    """
    window_id: int
    tick_id: int

    supporting_nodes: List[str]
    contradicting_nodes: List[str]
    ambiguous_nodes: List[str]
    unknown_nodes: List[Tuple[str, int]]  # (node_id, ticks_since_last)

    p_detect_distribution: List[Tuple[str, float, str]]  # (node_id, p_detect, node_type)
    health_distribution: List[Tuple[str, float]]
    calibration_status_summary: Dict[str, int]

    evidence_types_present: List[str]
    bearing_spread_deg: float
    bearing_mean_deg: float
    max_position_uncertainty_m: float
    avg_sensor_health: float

    notes: List[str]
    warnings: List[str]

    def to_dict(self) -> dict:
        return {
            "window_id": self.window_id,
            "tick_id": self.tick_id,
            "supporting_nodes": self.supporting_nodes,
            "contradicting_nodes": self.contradicting_nodes,
            "ambiguous_nodes": self.ambiguous_nodes,
            "unknown_nodes": self.unknown_nodes,
            "evidence_types": self.evidence_types_present,
            "bearing_stats": {
                "mean_deg": self.bearing_mean_deg,
                "spread_deg": self.bearing_spread_deg,
            },
            "position_uncertainty_m": self.max_position_uncertainty_m,
            "avg_sensor_health": self.avg_sensor_health,
            "calibration_summary": self.calibration_status_summary,
            "notes": self.notes,
            "warnings": self.warnings,
        }


class OdysseyMesh:
    """
    Mesh reconciliation engine.

    Invariants:
    - Transport and reconcile only (never fuse)
    - Preserve disagreement and absence
    - All outputs inspectable
    """

    def __init__(self, node_ids: List[str], store: MeshStore) -> None:
        self.node_ids = node_ids
        self.store = store

    def get_records_for_window(self, window_id: int) -> List[EvidenceRecord]:
        recs = [r for r in self.store.all_records() if r.window_id == window_id]
        recs.sort(key=lambda r: (r.tick_id, r.node_id, r.hash))
        return recs

    def get_latest_record_by_node(self, window_id: int) -> Dict[str, EvidenceRecord]:
        recs = self.get_records_for_window(window_id)
        latest: Dict[str, EvidenceRecord] = {}
        for r in recs:
            prev = latest.get(r.node_id)
            if prev is None or r.tick_id > prev.tick_id:
                latest[r.node_id] = r
        return latest

    def get_view(
        self,
        window_id: int,
        current_tick: int,
        support_threshold: float = 0.7,
        contradict_threshold: float = 0.3,
    ) -> MeshView:
        latest = self.get_latest_record_by_node(window_id)

        supporting: List[str] = []
        contradicting: List[str] = []
        ambiguous: List[str] = []

        p_dist: List[Tuple[str, float, str]] = []
        health_dist: List[Tuple[str, float]] = []
        calibration_counts = {"nominal": 0, "degraded": 0, "failed": 0}
        evidence_types = set()
        max_pos_uncertainty = 0.0
        bearings: List[float] = []
        total_health = 0.0
        health_count = 0

        for nid in self.node_ids:
            rec = latest.get(nid)
            if not rec:
                continue

            p_dist.append((nid, rec.p_detect_local, rec.node_type))
            health_dist.append((nid, rec.sensor_health))
            calibration_counts[rec.calibration_status] = calibration_counts.get(rec.calibration_status, 0) + 1
            evidence_types.add(rec.features.evidence_type.value)

            max_pos_uncertainty = max(max_pos_uncertainty, rec.position_accuracy_m)
            bearings.append(rec.features.bearing_deg)

            total_health += rec.sensor_health
            health_count += 1

            if rec.p_detect_local >= support_threshold:
                supporting.append(nid)
            elif rec.p_detect_local <= contradict_threshold:
                contradicting.append(nid)
            else:
                ambiguous.append(nid)

        unknown = self.store.get_absent_nodes(window_id, current_tick)

        bearing_mean = circular_mean(bearings) if bearings else 0.0
        bearing_spread = circular_std(bearings) if len(bearings) > 1 else 0.0
        avg_health = (total_health / health_count) if health_count > 0 else 0.0

        notes: List[str] = []
        warnings: List[str] = []

        if len(supporting) >= 2 and len(contradicting) >= 1:
            notes.append("DISAGREEMENT: Multiple nodes have conflicting evidence. Do not collapse to consensus.")
            warnings.append("Evidence conflict present")

        if len(unknown) > 0:
            notes.append(f"ABSENCE: {len(unknown)} node(s) missing in this window.")
            warnings.append(f"{len(unknown)} nodes absent")

        if bearing_spread > 45.0 and len(supporting) > 1:
            notes.append(f"BEARING SPREAD: {bearing_spread:.1f}° - consider multiple targets or measurement error")

        if max_pos_uncertainty > 100.0:
            notes.append(f"POSITION UNCERTAINTY: Up to {max_pos_uncertainty:.0f}m - geolocation confidence reduced")

        if (calibration_counts.get("degraded", 0) + calibration_counts.get("failed", 0)) > (len(self.node_ids) // 2):
            warnings.append("Majority of nodes have degraded/failed calibration")

        if avg_health < 0.6:
            warnings.append(f"Low average sensor health: {avg_health:.2f}")

        if not evidence_types:
            evidence_types.add("none")

        return MeshView(
            window_id=window_id,
            tick_id=current_tick,
            supporting_nodes=supporting,
            contradicting_nodes=contradicting,
            ambiguous_nodes=ambiguous,
            unknown_nodes=unknown,
            p_detect_distribution=sorted(p_dist, key=lambda x: x[0]),
            health_distribution=sorted(health_dist, key=lambda x: x[0]),
            calibration_status_summary=calibration_counts,
            evidence_types_present=list(evidence_types),
            bearing_spread_deg=bearing_spread,
            bearing_mean_deg=bearing_mean,
            max_position_uncertainty_m=max_pos_uncertainty,
            avg_sensor_health=avg_health,
            notes=notes,
            warnings=warnings,
        )
