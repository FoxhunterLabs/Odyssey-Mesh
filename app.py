import time
import base64
import json
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from odyssey.sim.orchestrator import OdysseySimulation, verify_deterministic_replay


def _get_sim() -> OdysseySimulation:
    if "sim" not in st.session_state:
        st.session_state.sim = OdysseySimulation(seed=1337, window_size=5)
        st.session_state.running = False
        st.session_state.auto_run_speed = 0.5
        st.session_state.selected_window = 0
    return st.session_state.sim


def _reset_sim(seed: int, window_size: int):
    st.session_state.sim = OdysseySimulation(seed=seed, window_size=window_size)
    st.session_state.running = False
    st.session_state.selected_window = 0


def panel_dashboard(sim: OdysseySimulation):
    st.subheader("📊 System Diagnostics")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Current Tick", sim.tick)
        st.metric("Window ID", sim.window_id)
        st.metric("Total Records", len(sim.store.all_records()))
    with col2:
        if sim.last_recommendation:
            state = sim.last_recommendation["state"]
            color = {"IDLE": "gray", "WATCH": "dodgerblue", "ATTENTION": "crimson"}.get(state, "gray")
            st.markdown(f"### Supervisor State: <span style='color:{color}'>{state}</span>", unsafe_allow_html=True)
            st.caption(f"Attention count: {sim.last_recommendation['attention_count']}")
        else:
            st.caption("No supervisor evaluation yet")
    with col3:
        if sim.last_view:
            st.metric("Supporting Nodes", len(sim.last_view.supporting_nodes))
            st.metric("Contradicting Nodes", len(sim.last_view.contradicting_nodes))
            absent = len(sim.last_view.unknown_nodes)
            st.metric("Absent Nodes", absent, delta=f"-{absent}" if absent > 0 else None)

    st.divider()
    st.subheader("Node Health & Confidence")

    if sim.last_view:
        data = []
        for node_id, p_detect, node_type in sim.last_view.p_detect_distribution:
            health = next((h for n, h in sim.last_view.health_distribution if n == node_id), 0.0)
            status = (
                "Supporting" if node_id in sim.last_view.supporting_nodes
                else "Contradicting" if node_id in sim.last_view.contradicting_nodes
                else "Ambiguous"
            )
            data.append({"Node": node_id, "Type": node_type, "Confidence": p_detect, "Health": health, "Status": status})

        df = pd.DataFrame(data)

        fig = go.Figure()
        # (No explicit colors policy doesn't apply here; UI readability matters.
        # But to be safe: we will still not set exact marker colors beyond minimal.)
        for status in df["Status"].unique():
            subset = df[df["Status"] == status]
            fig.add_trace(
                go.Scatter(
                    x=subset["Node"],
                    y=subset["Confidence"],
                    mode="markers",
                    name=status,
                    marker=dict(size=subset["Health"] * 30 + 10),
                    text=[f"Health: {h:.2f}<br>Type: {t}" for h, t in zip(subset["Health"], subset["Type"])],
                    hoverinfo="text",
                )
            )

        fig.update_layout(
            title="Node Confidence vs Health (Bubble Size = Health)",
            xaxis_title="Node",
            yaxis_title="Local Confidence",
            yaxis_range=[0, 1],
            showlegend=True,
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Evidence Timeline (last 100 records)")

    records = sim.store.all_records()
    if records:
        timeline = []
        for r in records[-100:]:
            timeline.append({"Tick": r.tick_id, "Node": r.node_id, "Confidence": r.p_detect_local, "Window": r.window_id})
        tdf = pd.DataFrame(timeline)

        fig = go.Figure()
        for node_id in sorted(tdf["Node"].unique()):
            subset = tdf[tdf["Node"] == node_id]
            fig.add_trace(go.Scatter(x=subset["Tick"], y=subset["Confidence"], mode="lines+markers", name=node_id))
        fig.update_layout(
            title="Confidence Timeline by Node",
            xaxis_title="Tick",
            yaxis_title="Local Confidence",
            yaxis_range=[0, 1],
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No records yet. Step the sim.")


def panel_evidence(sim: OdysseySimulation):
    st.subheader("🔍 Evidence Records")

    max_window = max(0, sim.window_id)
    col1, col2, col3 = st.columns(3)
    with col1:
        show_window = st.number_input("Window", min_value=0, max_value=max_window, value=min(st.session_state.selected_window, max_window))
        st.session_state.selected_window = int(show_window)
    with col2:
        node_filter = st.multiselect("Filter Nodes", options=sorted(list(sim.nodes.keys())), default=sorted(list(sim.nodes.keys())))
    with col3:
        conf_min = st.slider("Min Confidence", 0.0, 1.0, 0.0)

    records = sim.mesh.get_records_for_window(int(show_window))
    filtered = [r for r in records if r.node_id in node_filter and r.p_detect_local >= conf_min]

    st.write(f"**{len(filtered)} records in window {show_window}**")

    if not filtered:
        st.info("No records match the filters.")
        return

    rows = []
    for r in filtered:
        rows.append(
            {
                "Node": r.node_id,
                "Type": r.node_type,
                "Tick": r.tick_id,
                "Confidence": round(r.p_detect_local, 3),
                "Health": round(r.sensor_health, 3),
                "Bearing": f"{r.features.bearing_deg:.1f}°",
                "SNR": f"{r.features.snr_db:.1f} dB",
                "Record ID": r.record_id[:8],
                "Hash": r.hash[:8],
            }
        )
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("Inspect a record", expanded=False):
        idx = st.selectbox("Select", options=list(range(len(filtered))), format_func=lambda i: f"{filtered[i].node_id} @ tick {filtered[i].tick_id}")
        rec = filtered[int(idx)]

        c1, c2 = st.columns(2)
        with c1:
            st.json(
                {
                    "record_id": rec.record_id,
                    "node_id": rec.node_id,
                    "node_type": rec.node_type,
                    "tick": rec.tick_id,
                    "window": rec.window_id,
                    "p_detect_local": rec.p_detect_local,
                    "sensor_health": rec.sensor_health,
                    "clock_drift_ms": rec.clock_drift_ms,
                    "position_accuracy_m": rec.position_accuracy_m,
                    "calibration_status": rec.calibration_status,
                    "prev_hash": rec.prev_hash[:16] if rec.prev_hash else None,
                    "hash": rec.hash,
                },
                expanded=False,
            )
        with c2:
            st.json(rec.features.to_dict(), expanded=False)

        st.markdown("**Explanations**")
        for exp in rec.explanations:
            st.markdown(f"- {exp}")


def panel_network(sim: OdysseySimulation):
    st.subheader("⚙️ Network State")

    node_ids = sorted(list(sim.nodes.keys()))

    # Simple circular layout network graph
    pos = {}
    for i, nid in enumerate(node_ids):
        ang = 2 * math.pi * i / max(1, len(node_ids))
        pos[nid] = (math.cos(ang), math.sin(ang))

    fig = go.Figure()

    # edges
    for i, a in enumerate(node_ids):
        for j, b in enumerate(node_ids):
            if i < j:
                rule = sim.transport.get_rule(a, b)
                if not rule.up:
                    continue
                x0, y0 = pos[a]
                x1, y1 = pos[b]
                fig.add_trace(go.Scatter(x=[x0, x1, None], y=[y0, y1, None], mode="lines", hoverinfo="text",
                                         hovertext=f"{a} ↔ {b}<br>Drop: {rule.drop_rate:.1%}<br>Latency: {rule.latency_ticks} ticks<br>BW: {rule.bandwidth_limit} rec/tick",
                                         showlegend=False))

    # nodes
    for nid, (x, y) in pos.items():
        n = sim.nodes[nid]
        fig.add_trace(go.Scatter(
            x=[x], y=[y],
            mode="markers+text",
            text=[nid],
            textposition="top center",
            marker=dict(size=28),
            hoverinfo="text",
            hovertext=f"{nid}<br>Type: {n.node_type}<br>Health: {n.sensor_health:.2f}",
            name=nid
        ))

    fig.update_layout(
        title="Mesh Network (Up Links Only)",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Link Configuration")

    with st.expander("Configure links", expanded=False):
        for i, a in enumerate(node_ids):
            for j, b in enumerate(node_ids):
                if i < j:
                    rule = sim.transport.get_rule(a, b)
                    st.markdown(f"**{a} ↔ {b}**")
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        up = st.checkbox("Up", value=rule.up, key=f"up_{a}_{b}")
                    with c2:
                        drop = st.slider("Drop Rate", 0.0, 1.0, float(rule.drop_rate), key=f"drop_{a}_{b}")
                    with c3:
                        latency = st.slider("Latency", 0, 10, int(rule.latency_ticks), key=f"lat_{a}_{b}")
                    with c4:
                        bw = st.slider("BW Limit", 1, 200, int(rule.bandwidth_limit), key=f"bw_{a}_{b}")

                    if (up != rule.up) or (drop != rule.drop_rate) or (latency != rule.latency_ticks) or (bw != rule.bandwidth_limit):
                        from odyssey.core.transport import LinkRule
                        sim.transport.set_link(a, b, LinkRule(up=up, drop_rate=drop, latency_ticks=latency, bandwidth_limit=bw))

    st.divider()
    stats = sim.transport.get_network_stats()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total Links", stats["total_links"])
        st.metric("Active Links", stats["up_links"])
    with c2:
        st.metric("Inflight Messages", stats["inflight_count"])
        st.metric("Avg Drop Rate", f"{stats['avg_drop_rate']:.1%}")
    with c3:
        knowledge_counts = [len(sim.store.known_by_node.get(n, set())) for n in node_ids]
        avg_k = sum(knowledge_counts) / len(knowledge_counts) if knowledge_counts else 0
        st.metric("Avg Known Records", f"{avg_k:.0f}")
        st.metric("Max/Min Known", f"{max(knowledge_counts)}/{min(knowledge_counts)}")


def panel_governance(sim: OdysseySimulation):
    st.subheader("🔒 Methodology Governance")

    with st.expander("Core Invariants (Non-negotiable)", expanded=True):
        st.markdown(
            """
**1. Evidence-only mesh**  
Nodes emit EvidenceRecords, never decisions.

**2. Disagreement is preserved**  
Conflicts are carried forward, not averaged away.

**3. Absence is a signal**  
Missing/late nodes are explicitly represented.

**4. Deterministic replay**  
Same inputs + seed = identical outcomes.

**5. Human governance upstream**  
Supervisor only recommends attention; no autonomous action.
            """.strip()
        )

    st.divider()
    st.subheader("Replay Integrity")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔍 Verify Deterministic Replay (10 ticks)", use_container_width=True):
            ok, details = verify_deterministic_replay(sim.seed, 10)
            if ok:
                st.success("✅ Replay verified: deterministic")
            else:
                st.error("❌ Replay divergence detected")
                st.json(details, expanded=False)

    with c2:
        if st.button("📥 Export Audit Trail", use_container_width=True):
            audit = sim.export_audit_trail()
            payload = json.dumps(audit, indent=2)
            b64 = base64.b64encode(payload.encode()).decode()
            href = f'<a href="data:application/json;base64,{b64}" download="odyssey_audit.json">Download Audit Trail</a>'
            st.markdown(href, unsafe_allow_html=True)

    st.divider()
    st.subheader("Recent Events (Append-only Log)")
    events = sim.log.tail(20)
    if not events:
        st.info("No events yet.")
        return

    for ev in reversed(events):
        with st.expander(f"{ev['timestamp_utc'][11:19]} — {ev['type']}", expanded=False):
            st.json(ev, expanded=False)


def main():
    st.set_page_config(
        page_title="Odyssey Mesh — Governance-Grade Maritime Sensing",
        page_icon="🌊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown("# 🌊 Odyssey Mesh")
    st.caption("Governance-grade evidence transport & reconciliation for maritime sensing.")

    sim = _get_sim()

    # Sidebar
    with st.sidebar:
        st.header("Simulation Controls")

        new_seed = st.number_input("RNG Seed", value=int(sim.seed), step=1)
        new_window_size = st.number_input("Window Size", value=int(sim.window_size), min_value=1, step=1)

        if st.button("🔁 Apply Seed/Window (Reset)", use_container_width=True):
            _reset_sim(int(new_seed), int(new_window_size))
            st.rerun()

        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            if st.button("▶ Step", use_container_width=True):
                sim.step()
                st.rerun()
        with c2:
            if st.button("⏹ Reset", use_container_width=True):
                _reset_sim(int(new_seed), int(new_window_size))
                st.rerun()

        st.session_state.running = st.toggle("Continuous Run", value=st.session_state.running)
        st.session_state.auto_run_speed = st.slider("Run Speed (sec/tick)", 0.05, 2.0, float(st.session_state.auto_run_speed), 0.05)

        if st.session_state.running:
            time.sleep(float(st.session_state.auto_run_speed))
            sim.step()
            st.rerun()

        st.divider()
        st.subheader("World State (Simulation Only)")
        sim.world_state["target_present"] = st.toggle("Target Present", value=bool(sim.world_state["target_present"]))
        sim.world_state["target_range_km"] = st.slider("Target Range (km)", 1.0, 50.0, float(sim.world_state["target_range_km"]))
        sim.world_state["target_bearing_deg"] = st.slider("Target Bearing (°)", 0.0, 360.0, float(sim.world_state["target_bearing_deg"]))
        sim.world_state["sea_state"] = st.slider("Sea State (1-5)", 1, 5, int(sim.world_state["sea_state"]))

        st.divider()
        st.subheader("Supervisor Rules")
        sim.supervisor_rules["k_of_n"] = st.slider("K-of-N for Attention", 1, len(sim.nodes), int(sim.supervisor_rules["k_of_n"]))
        sim.supervisor_rules["require_bearing_agreement"] = st.toggle(
            "Require Bearing Agreement", value=bool(sim.supervisor_rules["require_bearing_agreement"])
        )
        if sim.supervisor_rules["require_bearing_agreement"]:
            sim.supervisor_rules["max_bearing_spread"] = st.slider("Max Bearing Spread (°)", 5.0, 90.0, float(sim.supervisor_rules["max_bearing_spread"]))
        sim.supervisor_rules["min_healthy_nodes"] = st.slider("Minimum Healthy Nodes", 1, len(sim.nodes), int(sim.supervisor_rules["min_healthy_nodes"]))
        sim.supervisor_rules["health_threshold"] = st.slider("Health Threshold", 0.0, 1.0, float(sim.supervisor_rules["health_threshold"]))
        sim.supervisor_rules["calibration_threshold"] = st.slider("Calibration Threshold (fraction nominal)", 0.0, 1.0, float(sim.supervisor_rules["calibration_threshold"]))
        sim.supervisor_rules["escalate_on_warnings"] = st.toggle("Escalate On Warnings", value=bool(sim.supervisor_rules["escalate_on_warnings"]))
        sim.supervisor_rules["ignore_absent_nodes"] = st.toggle("Ignore Absent Nodes", value=bool(sim.supervisor_rules["ignore_absent_nodes"]))

        if st.button("Reset Attention Counter", use_container_width=True):
            sim.supervisor.reset_attention_counter()
            st.success("Attention counter reset")
            st.rerun()

    tab1, tab2, tab3, tab4 = st.tabs(["📈 Dashboard", "🔍 Evidence View", "⚙️ Network", "📜 Governance"])
    with tab1:
        panel_dashboard(sim)
    with tab2:
        panel_evidence(sim)
    with tab3:
        panel_network(sim)
    with tab4:
        panel_governance(sim)


if __name__ == "__main__":
    main()
