import json
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from odyssey.core.geometry import Position
from odyssey.core.event_log import EventLog
from odyssey.core.mesh_store import MeshStore
from odyssey.core.transport import GossipTransport, LinkRule
from odyssey.core.node import OdysseyNode
from odyssey.core.mesh import OdysseyMesh, MeshView
from odyssey.core.supervisor import Supervisor
from odyssey.core.utils import stable_hash, utc_now_iso


@dataclass(frozen=True)
class NodeDefinition:
    id: str
    type: str
    lat: float
    lon: float
    accuracy_m: float


DEFAULT_NODES: List[NodeDefinition] = [
    NodeDefinition("HYDRO_A", "hydrophone", 34.5, -120.5, 25),
    NodeDefinition("HYDRO_B", "hydrophone", 34.6, -120.4, 30),
    NodeDefinition("RADAR_C", "radar", 34.55, -120.45, 15),
    NodeDefinition("AIS_D", "ais_receiver", 34.58, -120.48, 50),
    NodeDefinition("IR_E", "ir_camera", 34.52, -120.52, 10),
]


DEFAULT_RULES: Dict = {
    "k_of_n": 2,
    "require_bearing_agreement": True,
    "max_bearing_spread": 30.0,
    "min_healthy_nodes": 3,
    "escalate_on_warnings": True,
    "ignore_absent_nodes": False,
    "health_threshold": 0.7,
    "calibration_threshold": 0.5,
}


class OdysseySimulation:
    """
    Deterministic simulation orchestrator.

    Notes:
    - No Streamlit dependency
    - All randomness routed through seeded RNG objects
    - Produces MeshView + Supervisor recommendation per tick
    """

    def __init__(
        self,
        *,
        seed: int = 1337,
        window_size: int = 5,
        node_definitions: Optional[List[NodeDefinition]] = None,
        supervisor_rules: Optional[Dict] = None,
    ) -> None:
        self.seed = int(seed)
        self.window_size = int(window_size)

        self.node_definitions = node_definitions or list(DEFAULT_NODES)
        self.supervisor_rules = dict(supervisor_rules or DEFAULT_RULES)

        # Core state
        self.tick = 0
        self.window_id = 0

        # Audit + storage
        self.log = EventLog()
        self.store = MeshStore()

        # World state (simulation only)
        self.world_state: Dict = {
            "target_present": False,
            "target_range_km": 10.0,
            "target_bearing_deg": 45.0,
            "target_speed_knots": 12.0,
            "sea_state": 2,
            "ambient_noise_db": 60.0,
            "visibility_km": 15.0,
        }

        # Deterministic sim RNG (used for per-tick environment jitter)
        self.sim_rng = random.Random(self.seed + 424242)

        # Nodes
        self.nodes: Dict[str, OdysseyNode] = {}
        for i, nd in enumerate(self.node_definitions):
            node_rng = random.Random(self.seed + i * 1000)
            pos = Position(nd.lat, nd.lon, nd.accuracy_m)
            node = OdysseyNode(
                node_id=nd.id,
                node_type=nd.type,
                position=pos,
                rng=node_rng,
                log=self.log,
                store=self.store,
            )
            self.nodes[nd.id] = node

        # Transport RNG
        tr_rng = random.Random(self.seed + 999999)
        self.transport = GossipTransport(tr_rng, self.log, self.store)

        # Initialize links deterministically by node types
        node_ids = [nd.id for nd in self.node_definitions]
        for i, a in enumerate(node_ids):
            for j, b in enumerate(node_ids):
                if i < j:
                    if "HYDRO" in a and "HYDRO" in b:
                        rule = LinkRule(up=True, drop_rate=0.05, latency_ticks=2, bandwidth_limit=50)
                    elif "RADAR" in a or "RADAR" in b:
                        rule = LinkRule(up=True, drop_rate=0.02, latency_ticks=1, bandwidth_limit=100)
                    else:
                        rule = LinkRule(up=True, drop_rate=0.08, latency_ticks=3, bandwidth_limit=30)
                    self.transport.set_link(a, b, rule)

        # Mesh + supervisor
        self.mesh = OdysseyMesh(node_ids, self.store)
        self.supervisor = Supervisor(self.log)

        # Latest outputs
        self.last_view: Optional[MeshView] = None
        self.last_recommendation: Optional[dict] = None

        self.log.append(
            "sim_init",
            {
                "seed": self.seed,
                "window_size": self.window_size,
                "nodes": [nd.__dict__ for nd in self.node_definitions],
                "rules_hash": stable_hash(self.supervisor_rules),
            },
            tick_id=0,
        )

    def _make_local_environment(self) -> Dict:
        """
        Simulation-only interface: each node sees a slightly jittered version
        of the shared world state.

        IMPORTANT:
        This jitter MUST be deterministic -> uses self.sim_rng.
        """
        return {
            "target_present": bool(self.world_state["target_present"]),
            "target_range_km": float(self.world_state["target_range_km"]) + self.sim_rng.uniform(-2, 2),
            "target_bearing_deg": (float(self.world_state["target_bearing_deg"]) + self.sim_rng.uniform(-10, 10)) % 360.0,
            "target_speed_knots": float(self.world_state["target_speed_knots"]),
            "sea_state": int(self.world_state["sea_state"]),
            "ambient_noise_db": float(self.world_state["ambient_noise_db"]),
        }

    def step(self) -> Tuple[MeshView, dict]:
        """
        Execute one deterministic simulation tick.
        Returns (MeshView, supervisor_recommendation).
        """
        self.tick += 1
        self.window_id = self.tick // self.window_size

        # Nodes emit evidence
        for node in self.nodes.values():
            env = self._make_local_environment()
            node.step(self.tick, self.window_id, env)

        # Gossip exchanges (pairwise)
        node_ids = list(self.nodes.keys())
        for src in node_ids:
            for dst in node_ids:
                if src != dst:
                    self.transport.gossip_step(self.tick, src, dst)

        delivered = self.transport.deliver_inflight(self.tick)

        # Reconciliation (no fusion)
        view = self.mesh.get_view(
            window_id=self.window_id,
            current_tick=self.tick,
            support_threshold=0.7,
            contradict_threshold=0.3,
        )
        self.last_view = view

        # Supervisor evaluation (thin, rule-based)
        recommendation = self.supervisor.evaluate(
            tick_id=self.tick,
            view=view,
            rules=self.supervisor_rules,
        )
        self.last_recommendation = recommendation

        self.log.append(
            "tick_complete",
            {
                "tick": self.tick,
                "window": self.window_id,
                "records_emitted": len(self.nodes),
                "records_delivered": delivered,
                "total_records": len(self.store.all_records()),
                "view_hash": stable_hash(view.to_dict()),
            },
            self.tick,
        )

        return view, recommendation

    def run(self, steps: int) -> Tuple[MeshView, dict]:
        """
        Run N steps deterministically.
        Returns final (MeshView, recommendation).
        """
        out_view: Optional[MeshView] = None
        out_rec: Optional[dict] = None
        for _ in range(int(steps)):
            out_view, out_rec = self.step()
        assert out_view is not None and out_rec is not None
        return out_view, out_rec

    def export_audit_trail(self) -> Dict:
        """
        Export audit trail sufficient for forensic replay.

        Note: world_state_history is left minimal here; you can extend
        to capture per-tick world states if desired.
        """
        records_audit = [r.to_audit_dict() for r in self.store.all_records()]
        audit = {
            "metadata": {
                "export_time": utc_now_iso(),
                "system": "Odyssey Mesh v1.0",
                "seed": self.seed,
                "final_tick": self.tick,
                "window_size": self.window_size,
                "invariants": [
                    "Evidence-only mesh",
                    "Disagreement preserved",
                    "Absence as signal",
                    "Deterministic replay",
                    "Human governance upstream",
                ],
            },
            "configuration": {
                "nodes": [nd.__dict__ for nd in self.node_definitions],
                "supervisor_rules": self.supervisor_rules,
                "window_size": self.window_size,
            },
            "world_state": dict(self.world_state),
            "world_state_history": [],
            "evidence_records": records_audit,
            "event_log": list(self.log.events),
            "link_states": self._export_link_states(),
            "final_state": {
                "meshview": self.last_view.to_dict() if self.last_view else None,
                "supervisor_recommendation": self.last_recommendation,
            },
            "integrity_hashes": {
                "records_hash": stable_hash(records_audit),
                "events_hash": stable_hash(self.log.events),
                "rules_hash": stable_hash(self.supervisor_rules),
            },
        }
        return audit

    def _export_link_states(self) -> Dict[str, Dict]:
        node_ids = list(self.nodes.keys())
        out: Dict[str, Dict] = {}
        for i, a in enumerate(node_ids):
            for j, b in enumerate(node_ids):
                if i < j:
                    rule = self.transport.get_rule(a, b)
                    out[f"{a}<->{b}"] = rule.to_dict()
        return out


def verify_deterministic_replay(seed: int, steps: int = 10) -> Tuple[bool, Dict]:
    """
    Run two simulations with the same seed/steps and compare key state.
    """
    sim1 = OdysseySimulation(seed=seed)
    sim1.run(steps)
    state1 = {
        "tick": sim1.tick,
        "window": sim1.window_id,
        "total_records": len(sim1.store.all_records()),
        "total_events": len(sim1.log.events),
        "meshview_hash": stable_hash(sim1.last_view.to_dict()) if sim1.last_view else None,
        "supervisor_state": sim1.last_recommendation["state"] if sim1.last_recommendation else None,
    }

    sim2 = OdysseySimulation(seed=seed)
    sim2.run(steps)
    state2 = {
        "tick": sim2.tick,
        "window": sim2.window_id,
        "total_records": len(sim2.store.all_records()),
        "total_events": len(sim2.log.events),
        "meshview_hash": stable_hash(sim2.last_view.to_dict()) if sim2.last_view else None,
        "supervisor_state": sim2.last_recommendation["state"] if sim2.last_recommendation else None,
    }

    identical = state1 == state2
    return identical, {"run1": state1, "run2": state2}


def audit_to_json(audit: Dict, *, indent: int = 2) -> str:
    return json.dumps(audit, indent=indent, sort_keys=True)


def default_audit_filename(prefix: str = "odyssey_audit") -> str:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}.json"
