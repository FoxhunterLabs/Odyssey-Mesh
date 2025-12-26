from odyssey.sim.orchestrator import OdysseySimulation


def test_supervisor_produces_state():
    sim = OdysseySimulation(seed=2024)
    sim.run(5)

    assert sim.last_recommendation is not None
    assert "state" in sim.last_recommendation
    assert sim.last_recommendation["state"] in {"IDLE", "WATCH", "ATTENTION"}


def test_supervisor_does_not_autonomously_escalate():
    sim = OdysseySimulation(seed=2024)

    # Very strict rules to prevent attention
    sim.supervisor_rules.update({
        "k_of_n": 10,
        "min_healthy_nodes": 10,
        "require_bearing_agreement": True,
        "max_bearing_spread": 1.0,
    })

    sim.run(10)

    assert sim.last_recommendation["state"] != "ATTENTION", (
        "Supervisor escalated despite impossible rules"
    )
