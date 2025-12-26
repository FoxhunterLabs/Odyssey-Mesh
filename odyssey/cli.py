import argparse
import sys

from odyssey.sim.orchestrator import OdysseySimulation, default_audit_filename, audit_to_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="odyssey",
        description="Odyssey Mesh — governance-grade evidence simulation",
    )

    parser.add_argument(
        "run",
        nargs="?",
        default="run",
        help="Run a deterministic Odyssey Mesh simulation",
    )

    parser.add_argument("--seed", type=int, default=1337, help="RNG seed")
    parser.add_argument("--steps", type=int, default=10, help="Number of simulation ticks")
    parser.add_argument("--window-size", type=int, default=5, help="Window size (ticks)")
    parser.add_argument(
        "--target-present",
        action="store_true",
        help="Simulate target presence (simulation only)",
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        metavar="FILE",
        help="Export audit trail to JSON file",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    sim = OdysseySimulation(
        seed=args.seed,
        window_size=args.window_size,
    )

    # Apply world state ONCE (immutable thereafter)
    sim.world_state["target_present"] = bool(args.target_present)

    last_view = None
    last_rec = None

    for _ in range(int(args.steps)):
        last_view, last_rec = sim.step()

    # Operational summary (one line, no hype)
    if last_view and last_rec:
        print(
            f"tick={sim.tick} "
            f"window={sim.window_id} "
            f"state={last_rec['state']} "
            f"supporting={len(last_view.supporting_nodes)} "
            f"contradicting={len(last_view.contradicting_nodes)} "
            f"absent={len(last_view.unknown_nodes)}"
        )

    # Explicit audit export
    if args.export is not None:
        filename = args.export or default_audit_filename()
        audit = sim.export_audit_trail()
        with open(filename, "w", encoding="utf-8") as f:
            f.write(audit_to_json(audit))
        print(f"audit written to {filename}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
