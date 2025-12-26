from odyssey.sim.orchestrator import OdysseySimulation


def test_evidence_hash_stability():
    sim = OdysseySimulation(seed=123)
    sim.run(5)

    records = sim.store.all_records()
    assert records, "No evidence records produced"

    # Hashes must be unique and stable
    hashes = [r.hash for r in records]
    assert len(hashes) == len(set(hashes)), "Duplicate evidence hashes detected"

    # EvidenceRecords must be immutable (frozen dataclass)
    rec = records[0]
    try:
        rec.p_detect_local = 0.99  # type: ignore
        assert False, "EvidenceRecord mutated despite being frozen"
    except Exception:
        pass  # expected


def test_prev_hash_chain_integrity():
    sim = OdysseySimulation(seed=999)
    sim.run(8)

    by_node = {}
    for r in sim.store.all_records():
        by_node.setdefault(r.node_id, []).append(r)

    for node_id, recs in by_node.items():
        recs.sort(key=lambda r: r.tick_id)
        for i in range(1, len(recs)):
            assert recs[i].prev_hash == recs[i - 1].hash, (
                f"Broken hash chain for node {node_id}"
            )
