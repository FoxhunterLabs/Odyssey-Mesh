________________________________________
# 🌊 Odyssey Mesh

**Governance-grade evidence transport and reconciliation for maritime sensing**

Odyssey Mesh is a deterministic, evidence-only system for transporting, reconciling, and auditing maritime sensor data.  
It is explicitly designed to **preserve disagreement**, **treat absence as signal**, and **refuse autonomous decisions**.

This is not a fusion engine.  
It is a system for *seeing clearly* before humans decide.

---

## Why Odyssey Mesh Exists

Modern sensing systems fail quietly in three ways:

1. **They collapse disagreement** into a single score  
2. **They hide absence** (silent nodes look like agreement)  
3. **They drift** due to hidden state and non-replayable behavior  

Odyssey Mesh is built to do the opposite.

It assumes:
- Sensors disagree
- Networks fail
- Humans must remain responsible  

And it encodes those assumptions as **non-negotiable invariants**.

---

## Core Invariants (Non-Negotiable)

1. **Evidence-only mesh**  
   Nodes emit *EvidenceRecords*, never detections, classifications, or actions.

2. **Disagreement is preserved**  
   Conflicting evidence is carried forward explicitly — never averaged away.

3. **Absence is a signal**  
   Missing, late, or silent nodes are tracked and surfaced.

4. **Deterministic replay**  
   Same inputs + same seed = identical outcomes. No hidden state.

5. **Human governance upstream**  
   The system never triggers actions. A thin supervisor may recommend attention — nothing more.

These are design constraints, not features.

---

## System Architecture (High Level)

┌──────────┐
│ Nodes │ (honest witnesses)
│ │ emit EvidenceRecords
└────┬─────┘
│
▼
┌──────────┐
│ Transport│ (deterministic gossip)
│ Layer │
└────┬─────┘
│
▼
┌──────────┐
│ Mesh │ (reconciliation only)
│ View │ → disagreement + absence visible
└────┬─────┘
│
▼
┌──────────┐
│Supervisor│ (thin, rule-based)
│ │ recommends attention only
└──────────┘

There is **no fusion layer**.  
There is **no autonomous decision path**.

---

## What an EvidenceRecord Is

An `EvidenceRecord` is the **only admissible unit of information** in Odyssey Mesh.

It contains:
- local confidence (not a decision)
- extracted features
- sensor health & calibration state
- explicit explanations
- cryptographic hash + chain to previous record

It is:
- immutable
- replayable
- inspectable
- auditable

If something cannot be explained from an `EvidenceRecord`, it does not exist.

---

## Determinism & Auditability

Odyssey Mesh is deterministic by construction:

- All randomness is seeded
- Network behavior (drops, latency) is explicit
- Replay is verified by tests
- Audit exports include hashes for records, events, and rules

If two runs disagree, that is a **bug**, not a mystery.

---

## Quick Start (2 minutes)

### Install
```bash
pip install -e .
Run headless (CLI)
odyssey run --seed 1337 --steps 25 --target-present --export audit.json
Example output:
tick=25 window=5 state=WATCH supporting=2 contradicting=1 absent=1
audit written to audit.json
Run the UI
streamlit run app.py
The UI is a viewer, not the system.
________________________________________
CLI Philosophy
The CLI is intentionally thin.
It:
•	runs a deterministic simulation
•	prints a one-line operational summary
•	exports an audit trail if explicitly requested
It does not:
•	stream decisions
•	auto-escalate
•	mutate rules mid-run
•	hide outputs
If the CLI feels “helpful,” it’s wrong.
________________________________________
Tests That Matter
Odyssey Mesh includes smoke tests only — tests that enforce philosophy:
•	deterministic replay
•	evidence immutability
•	hash chain integrity
•	supervisor non-autonomy
Run them with:
pytest
If these fail, the system is untrustworthy.
________________________________________
What This System Explicitly Refuses
Odyssey Mesh refuses to:
•	❌ Collapse evidence into a single score
•	❌ Auto-escalate or act
•	❌ Hide disagreement
•	❌ Ignore missing nodes
•	❌ Adapt itself to “improve” decisions
•	❌ Optimize for certainty
These refusals are safety features.
________________________________________
Intended Use
Odyssey Mesh is suitable for:
•	maritime domain awareness
•	infrastructure & perimeter sensing
•	governance-sensitive environments
•	human-in-the-loop operations
•	audit-first system design
It is not intended for:
•	autonomous weapons
•	closed-loop control
•	opaque ML fusion
•	real-time decision engines
________________________________________
Status
This repository is a reference implementation.
It prioritizes:
•	clarity over performance
•	inspectability over optimization
•	governance over autonomy
Production deployments should treat this as a methodological baseline, not a drop-in product.
________________________________________
License
MIT________________________________________
