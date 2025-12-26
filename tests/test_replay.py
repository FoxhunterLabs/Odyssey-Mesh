from odyssey.sim.orchestrator import OdysseySimulation, verify_deterministic_replay


def test_deterministic_replay_basic():
    ok, details = verify_deterministic_replay(seed=1337, steps=10)
    assert ok, f"Replay divergence detected: {details}"


def test_replay_same_seed_same_hashes():
    sim1 = OdysseySimulation(seed=42)
    sim1.run(15)

    sim2 = OdysseySimulation(seed=42)
    sim2.run(15)

    assert sim1.tick == sim2.tick
    assert len(sim1.store.all_records()) == len(sim2.store.all_records())

    h1 = sim1.last_view.to_dict()
    h2 = sim2.last_view.to_dict()
    assert h1 == h2, "MeshView differs under identical seed"
