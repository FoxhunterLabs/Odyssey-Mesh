from dataclasses import dataclass
from typing import Dict, List, Tuple
import random

from .event_log import EventLog
from .mesh_store import MeshStore
from .evidence_record import EvidenceRecord


@dataclass
class LinkRule:
    """
    Controls connectivity between two nodes.

    drop_rate:
      probability a record transfer attempt is dropped

    latency_ticks:
      store-and-forward delay before delivery

    bandwidth_limit:
      max records sent per gossip exchange per tick
    """
    up: bool = True
    drop_rate: float = 0.0
    latency_ticks: int = 0
    bandwidth_limit: int = 100

    def to_dict(self) -> dict:
        return {
            "up": self.up,
            "drop_rate": self.drop_rate,
            "latency_ticks": self.latency_ticks,
            "bandwidth_limit": self.bandwidth_limit,
        }


class GossipTransport:
    """
    Deterministic gossip replication with network effects.

    Invariants:
    - Deterministic with provided RNG
    - Never mutates EvidenceRecords
    - Delivery is logged
    """

    def __init__(self, rng: random.Random, log: EventLog, store: MeshStore) -> None:
        self.rng = rng
        self.log = log
        self.store = store

        self.links: Dict[Tuple[str, str], LinkRule] = {}
        self.inflight: List[Tuple[int, str, str, EvidenceRecord]] = []  # (deliver_tick, src, dst, rec)

    def set_link(self, a: str, b: str, rule: LinkRule) -> None:
        """
        Set symmetric link rule between two nodes.
        """
        self.links[(a, b)] = rule
        self.links[(b, a)] = rule

    def get_rule(self, src: str, dst: str) -> LinkRule:
        return self.links.get((src, dst), LinkRule())

    def gossip_step(self, tick_id: int, src: str, dst: str) -> None:
        """
        One gossip exchange from src to dst.

        Determinism:
        - Missing hashes are set-diffed from MeshStore
        - Hash list is shuffled using RNG (seeded)
        - Drop decisions use RNG
        """
        rule = self.get_rule(src, dst)
        if not rule.up:
            return

        missing_for_dst, _missing_for_src = self.store.get_missing_hashes(src, dst)

        send_hashes = list(missing_for_dst)
        self.rng.shuffle(send_hashes)
        send_hashes = send_hashes[: rule.bandwidth_limit]

        sent_count = 0
        for h in send_hashes:
            if self.rng.random() < rule.drop_rate:
                continue

            rec = self.store.records_by_hash.get(h)
            if not rec:
                continue

            deliver_tick = tick_id + max(0, rule.latency_ticks)
            self.inflight.append((deliver_tick, src, dst, rec))
            sent_count += 1

        if sent_count > 0:
            self.log.append(
                "gossip",
                {
                    "tick": tick_id,
                    "src": src,
                    "dst": dst,
                    "sent": sent_count,
                    "latency_ticks": rule.latency_ticks,
                    "missing_before": len(missing_for_dst),
                },
                tick_id,
            )

    def deliver_inflight(self, tick_id: int) -> int:
        """
        Deliver records whose delivery time has arrived.
        Returns number of newly delivered records (new to receiver).
        """
        remaining: List[Tuple[int, str, str, EvidenceRecord]] = []
        delivered_count = 0

        for deliver_tick, src, dst, rec in self.inflight:
            if deliver_tick <= tick_id:
                new_to_dst = self.store.ingest(dst, rec)
                if new_to_dst:
                    delivered_count += 1
                    self.log.append(
                        "delivery",
                        {
                            "tick": tick_id,
                            "src": src,
                            "dst": dst,
                            "record_id": rec.record_id,
                            "hash": rec.hash[:8],
                        },
                        tick_id,
                    )
            else:
                remaining.append((deliver_tick, src, dst, rec))

        self.inflight = remaining
        return delivered_count

    def get_network_stats(self) -> dict:
        total_links = len(self.links) // 2
        up_links = sum(1 for r in self.links.values() if r.up) // 2

        drop_rates = [r.drop_rate for r in self.links.values()]
        avg_drop = (sum(drop_rates) / len(drop_rates)) if drop_rates else 0.0

        return {
            "total_links": total_links,
            "up_links": up_links,
            "down_links": total_links - up_links,
            "avg_drop_rate": avg_drop,
            "inflight_count": len(self.inflight),
        }
