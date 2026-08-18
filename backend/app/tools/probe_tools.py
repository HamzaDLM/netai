"""Safe simulated network probes used to exercise NetAI's live artifact UI.

These tools deliberately do not invoke the host shell or send network traffic.
They provide a production-shaped contract that can later be backed by an
isolated probe runner without changing the agent or frontend protocols.
"""

import hashlib
import math
import random
import re
import statistics
import time
from datetime import datetime, timezone
from typing import Annotated, Any

from app.agent_ui import complete_artifact, start_artifact, update_artifact
from app.tools import netai_tool

_SAFE_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,252}$")


def _validated_target(target: str) -> str:
    normalized = target.strip()
    if not _SAFE_TARGET_RE.fullmatch(normalized):
        raise ValueError("target must be a hostname or IP address without shell syntax")
    return normalized


def _rng_for(*parts: object) -> random.Random:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@netai_tool(
    name="network_ping",
    presentation={
        "artifact_kind": "network.ping.v1",
        "title": "Reachability test",
        "effect": "simulated_active_probe",
    },
)
def ping(
    target: Annotated[str, "Hostname or IP address to test"],
    count: Annotated[int, "Number of simulated ICMP requests (1-10)"] = 4,
    interval_ms: Annotated[
        int, "Delay between samples in milliseconds (50-1000)"
    ] = 250,
) -> dict[str, Any]:
    """Run a safe simulated ping and stream individual replies to an inline UI."""

    target = _validated_target(target)
    count = min(max(int(count), 1), 10)
    interval_ms = min(max(int(interval_ms), 50), 1000)
    rng = _rng_for("ping", target, count)
    forced_down = any(
        marker in target.lower() for marker in ("down", "offline", "unreachable")
    )
    started_at = _utc_now()
    artifact = start_artifact(
        kind="network.ping.v1",
        title=f"Ping {target}",
        data={
            "target": target,
            "simulated": True,
            "count": count,
            "sent": 0,
            "received": 0,
            "loss_percent": 0,
            "samples": [],
        },
        provenance={
            "source": "netai_mock_probe",
            "started_at": started_at,
            "simulated": True,
        },
    )

    samples: list[dict[str, Any]] = []
    received_latencies: list[float] = []
    received = 0
    base_latency = 5.0 + rng.random() * 35.0

    for sequence in range(1, count + 1):
        time.sleep(interval_ms / 1000)
        timed_out = forced_down or rng.random() < 0.08
        if timed_out:
            sample = {
                "sequence": sequence,
                "status": "timeout",
                "received_at": _utc_now(),
            }
        else:
            latency_ms = round(max(0.3, base_latency + rng.gauss(0, 2.4)), 2)
            received += 1
            received_latencies.append(latency_ms)
            sample = {
                "sequence": sequence,
                "status": "reply",
                "bytes": 64,
                "ttl": 55 + rng.randint(0, 8),
                "latency_ms": latency_ms,
                "received_at": _utc_now(),
            }
        samples.append(sample)
        sent = sequence
        loss_percent = round(((sent - received) / sent) * 100, 1)
        update_artifact(
            artifact,
            append_values={"samples": [sample]},
            set_values={
                "sent": sent,
                "received": received,
                "loss_percent": loss_percent,
            },
        )

    summary = {
        "sent": count,
        "received": received,
        "loss_percent": round(((count - received) / count) * 100, 1),
        "min_ms": round(min(received_latencies), 2) if received_latencies else None,
        "avg_ms": round(statistics.mean(received_latencies), 2)
        if received_latencies
        else None,
        "max_ms": round(max(received_latencies), 2) if received_latencies else None,
        "jitter_ms": (
            round(statistics.pstdev(received_latencies), 2)
            if len(received_latencies) > 1
            else 0.0
            if received_latencies
            else None
        ),
        "completed_at": _utc_now(),
    }
    complete_artifact(artifact, set_values=summary)
    return {
        "target": target,
        "simulated": True,
        "reachable": received > 0,
        **summary,
        "samples": samples,
        "artifact": {
            "id": artifact.id,
            "kind": artifact.kind,
            "schema_version": artifact.schema_version,
        },
    }


@netai_tool(
    name="network_traceroute",
    presentation={
        "artifact_kind": "network.traceroute.v1",
        "title": "Path trace",
        "effect": "simulated_active_probe",
    },
)
def traceroute(
    target: Annotated[str, "Hostname or IP address to trace"],
    max_hops: Annotated[int, "Maximum simulated hops (3-12)"] = 8,
) -> dict[str, Any]:
    """Run a safe simulated traceroute and stream each discovered hop."""

    target = _validated_target(target)
    max_hops = min(max(int(max_hops), 3), 12)
    rng = _rng_for("traceroute", target, max_hops)
    hop_count = min(max_hops, 4 + rng.randint(0, 3))
    artifact = start_artifact(
        kind="network.traceroute.v1",
        title=f"Traceroute to {target}",
        data={
            "target": target,
            "simulated": True,
            "max_hops": max_hops,
            "complete": False,
            "hops": [],
        },
        provenance={
            "source": "netai_mock_probe",
            "started_at": _utc_now(),
            "simulated": True,
        },
    )

    hops: list[dict[str, Any]] = []
    for hop_number in range(1, hop_count + 1):
        time.sleep(0.22)
        is_destination = hop_number == hop_count
        timeout = hop_number == 3 and rng.random() < 0.35 and not is_destination
        if timeout:
            hop = {
                "hop": hop_number,
                "status": "timeout",
                "address": None,
                "hostname": None,
                "latencies_ms": [],
            }
        else:
            latencies = [
                round(2.0 + hop_number * 4.5 + rng.random() * 3.5, 2) for _ in range(3)
            ]
            hop = {
                "hop": hop_number,
                "status": "destination" if is_destination else "reply",
                "address": target
                if is_destination
                else f"10.{20 + hop_number}.{rng.randint(0, 8)}.1",
                "hostname": target
                if is_destination
                else f"hop-{hop_number}.example.net",
                "latencies_ms": latencies,
            }
        hops.append(hop)
        update_artifact(
            artifact,
            append_values={"hops": [hop]},
            set_values={"current_hop": hop_number},
        )

    completed_at = _utc_now()
    complete_artifact(
        artifact,
        set_values={
            "complete": True,
            "reached_destination": True,
            "hop_count": hop_count,
            "completed_at": completed_at,
        },
    )
    return {
        "target": target,
        "simulated": True,
        "reached_destination": True,
        "hop_count": hop_count,
        "hops": hops,
        "completed_at": completed_at,
        "artifact": {
            "id": artifact.id,
            "kind": artifact.kind,
            "schema_version": artifact.schema_version,
        },
    }


@netai_tool(
    name="network_latency_chart",
    presentation={
        "artifact_kind": "network.latency-chart.v1",
        "title": "Latency history",
        "effect": "simulated_active_probe",
    },
)
def latency_chart(
    target: Annotated[str, "Hostname or IP address to chart"],
    points: Annotated[int, "Number of simulated chart points (5-30)"] = 12,
) -> dict[str, Any]:
    """Generate a safe simulated latency series and stream it to a chart."""

    target = _validated_target(target)
    points = min(max(int(points), 5), 30)
    rng = _rng_for("latency-chart", target, points)
    artifact = start_artifact(
        kind="network.latency-chart.v1",
        title=f"Latency to {target}",
        data={
            "target": target,
            "simulated": True,
            "unit": "ms",
            "points": [],
        },
        provenance={
            "source": "netai_mock_probe",
            "started_at": _utc_now(),
            "simulated": True,
        },
    )

    values: list[float] = []
    series: list[dict[str, Any]] = []
    baseline = 18 + rng.random() * 20
    for index in range(points):
        time.sleep(0.10)
        value = round(
            max(0.5, baseline + math.sin(index / 2.3) * 5 + rng.gauss(0, 1.8)), 2
        )
        point = {"timestamp": _utc_now(), "value": value}
        values.append(value)
        series.append(point)
        update_artifact(
            artifact,
            append_values={"points": [point]},
            set_values={"latest_ms": value},
        )

    summary = {
        "min_ms": round(min(values), 2),
        "avg_ms": round(statistics.mean(values), 2),
        "max_ms": round(max(values), 2),
        "completed_at": _utc_now(),
    }
    complete_artifact(artifact, set_values=summary)
    return {
        "target": target,
        "simulated": True,
        "unit": "ms",
        "points": series,
        **summary,
        "artifact": {
            "id": artifact.id,
            "kind": artifact.kind,
            "schema_version": artifact.schema_version,
        },
    }
