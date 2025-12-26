from typing import Dict, List

from .event_log import EventLog
from .mesh import MeshView
from .utils import stable_hash


class Supervisor:
    """
    Thin supervisor - applies explicit rules to MeshView.

    Invariants:
    - Never fuses evidence
    - Never acts autonomously
    - Only recommends attention based on explicit rules
    """

    def __init__(self, log: EventLog) -> None:
        self.log = log
        self.state_history: List[dict] = []
        self.current_state = "IDLE"
        self.attention_since_reset = 0

    def evaluate(self, tick_id: int, view: MeshView, rules: Dict) -> dict:
        """
        Apply rule-based evaluation to MeshView.
        Returns recommendation only.

        Expected rules shape:
        {
            "k_of_n": 2,
            "require_bearing_agreement": True,
            "max_bearing_spread": 30.0,
            "min_healthy_nodes": 3,
            "escalate_on_warnings": True,
            "ignore_absent_nodes": False,
            "health_threshold": 0.7,
            "calibration_threshold": 0.5,
        }
        """
        # Rule 1: K-of-N supporting nodes
        k_needed = int(rules.get("k_of_n", 2))
        k_of_n_met = len(view.supporting_nodes) >= k_needed

        # Rule 2: Bearing agreement (if required)
        bearing_agreement = True
        if bool(rules.get("require_bearing_agreement", False)):
            bearing_agreement = view.bearing_spread_deg <= float(rules.get("max_bearing_spread", 30.0))

        # Rule 3: Sufficient healthy nodes
        health_thr = float(rules.get("health_threshold", 0.7))
        healthy_count = sum(1 for _, h in view.health_distribution if h > health_thr)
        sufficient_health = healthy_count >= int(rules.get("min_healthy_nodes", 3))

        # Rule 4: Calibration status quality
        total_nodes = len(view.p_detect_distribution)
        nominal_cal = int(view.calibration_status_summary.get("nominal", 0))
        cal_thr = float(rules.get("calibration_threshold", 0.5))
        good_calibration = ((nominal_cal / total_nodes) if total_nodes > 0 else 0.0) >= cal_thr

        # Rule 5: Handle warnings
        # If escalate_on_warnings=True and warnings exist => fail attention gate
        handle_warnings = not (bool(rules.get("escalate_on_warnings", True)) and bool(view.warnings))

        # Rule 6: Handle absent nodes
        absent_ok = bool(rules.get("ignore_absent_nodes", False)) or len(view.unknown_nodes) == 0

        should_raise_attention = (
            k_of_n_met
            and bearing_agreement
            and sufficient_health
            and good_calibration
            and handle_warnings
            and absent_ok
        )

        # State transitions (operator convenience only)
        new_state = "IDLE"
        if should_raise_attention:
            new_state = "ATTENTION"
            self.attention_since_reset += 1
        elif k_of_n_met and bearing_agreement:
            new_state = "WATCH"
        else:
            new_state = "IDLE"

        # Log state changes
        if new_state != self.current_state:
            self.log.append(
                "supervisor_state_change",
                {
                    "tick": tick_id,
                    "from": self.current_state,
                    "to": new_state,
                    "window": view.window_id,
                    "reason": {
                        "k_of_n_met": k_of_n_met,
                        "bearing_agreement": bearing_agreement,
                        "sufficient_health": sufficient_health,
                        "good_calibration": good_calibration,
                        "handle_warnings": handle_warnings,
                        "absent_ok": absent_ok,
                    },
                    "rule_hash": stable_hash(rules),
                },
                tick_id,
            )

            self.state_history.append(
                {
                    "tick": tick_id,
                    "state": new_state,
                    "window": view.window_id,
                    "view_hash": stable_hash(view.to_dict()),
                }
            )

            self.current_state = new_state

        return {
            "state": new_state,
            "should_raise_attention": should_raise_attention,
            "attention_count": self.attention_since_reset,
            "rule_evaluation": {
                "k_of_n": f"{len(view.supporting_nodes)}/{k_needed}",
                "bearing_spread": f"{view.bearing_spread_deg:.1f}°",
                "healthy_nodes": f"{healthy_count}/{int(rules.get('min_healthy_nodes', 3))}",
                "calibration_nominal": f"{nominal_cal}/{total_nodes}",
                "warnings_present": bool(view.warnings),
                "absent_nodes": len(view.unknown_nodes),
            },
            "view_summary": view.to_dict(),
        }

    def reset_attention_counter(self) -> None:
        self.attention_since_reset = 0
        self.log.append("supervisor_reset", {"attention_count_reset": True})

    def get_state_history(self, limit: int = 50) -> List[dict]:
        return self.state_history[-limit:] if self.state_history else []
