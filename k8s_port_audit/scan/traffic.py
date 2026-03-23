from __future__ import annotations

import socket
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path
from typing import Any

TCP_STATE_NAMES = {
    "01": "ESTABLISHED",
    "02": "SYN_SENT",
    "03": "SYN_RECV",
    "04": "FIN_WAIT1",
    "05": "FIN_WAIT2",
    "06": "TIME_WAIT",
    "07": "CLOSE",
    "08": "CLOSE_WAIT",
    "09": "LAST_ACK",
    "0A": "LISTEN",
    "0B": "CLOSING",
}


@dataclass(frozen=True)
class HostTcpObservation:
    local_address: str
    local_port: int
    remote_address: str
    remote_port: int
    state: str
    source_path: str


def parse_proc_tcp_table(table_path: Path, family: int) -> list[HostTcpObservation]:
    if not table_path.exists():
        return []

    observations: list[HostTcpObservation] = []
    for line in table_path.read_text(encoding="utf-8").splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4:
            continue

        local_address, local_port = decode_socket_address(fields[1], family)
        remote_address, remote_port = decode_socket_address(fields[2], family)
        observations.append(
            HostTcpObservation(
                local_address=local_address,
                local_port=local_port,
                remote_address=remote_address,
                remote_port=remote_port,
                state=TCP_STATE_NAMES.get(fields[3], fields[3]),
                source_path=str(table_path),
            )
        )
    return observations


def collect_host_tcp_observations(host_proc_root: Path) -> list[HostTcpObservation]:
    return [
        *parse_proc_tcp_table(host_proc_root / "1" / "net" / "tcp", socket.AF_INET),
        *parse_proc_tcp_table(host_proc_root / "1" / "net" / "tcp6", socket.AF_INET6),
    ]


def build_passive_observation_index(
    host_proc_root: Path,
    node_candidates: list[Any],
    local_node_name: str | None,
) -> tuple[dict[tuple[str, int], dict[str, Any]], dict[str, Any]]:
    # 该步骤只补充证据，不生成新的暴露面记录。
    summary = {
        "enabled": True,
        "available": False,
        "scope": "local_node_only",
        "host_proc_root": str(host_proc_root),
        "local_node_name": local_node_name,
        "raw_entry_count": 0,
        "matched_target_count": 0,
        "listener_target_count": 0,
        "active_traffic_target_count": 0,
        "error": None,
    }

    tcp_paths = [host_proc_root / "1" / "net" / "tcp", host_proc_root / "1" / "net" / "tcp6"]
    summary["available"] = any(path.exists() for path in tcp_paths)
    if not summary["available"]:
        summary["error"] = f"host proc TCP tables not found under {host_proc_root}"
        return {}, summary

    try:
        observations = collect_host_tcp_observations(host_proc_root)
    except Exception as exc:
        summary["error"] = str(exc)
        return {}, summary

    summary["raw_entry_count"] = len(observations)
    local_node_addresses = sorted(
        {
            node.address
            for node in node_candidates
            if not local_node_name or node.name == local_node_name
        }
    )
    if not local_node_addresses:
        summary["error"] = "local node addresses unavailable for passive observation"
        return {}, summary

    observation_map: dict[tuple[str, int], dict[str, Any]] = {}
    for observation in observations:
        if observation.local_port < 1 or is_loopback_address(observation.local_address):
            continue

        target_addresses = [observation.local_address]
        if is_unspecified_address(observation.local_address):
            # 0.0.0.0 / :: 监听仅映射回当前节点地址。
            target_addresses = local_node_addresses

        for target_address in target_addresses:
            key = (target_address, observation.local_port)
            entry = observation_map.get(key)
            if entry is None:
                entry = {
                    "states": [],
                    "listener_observed": False,
                    "traffic_observed": False,
                    "sample_count": 0,
                }
                observation_map[key] = entry

            if observation.state not in entry["states"]:
                entry["states"].append(observation.state)
            entry["sample_count"] += 1
            entry["listener_observed"] = entry["listener_observed"] or observation.state == "LISTEN"
            entry["traffic_observed"] = entry["traffic_observed"] or observation.state != "LISTEN"

    for entry in observation_map.values():
        entry["states"].sort()

    summary["matched_target_count"] = len(observation_map)
    summary["listener_target_count"] = sum(
        1 for entry in observation_map.values() if entry["listener_observed"]
    )
    summary["active_traffic_target_count"] = sum(
        1 for entry in observation_map.values() if entry["traffic_observed"]
    )
    return observation_map, summary


def annotate_results_with_traffic_observations(
    results: list[dict[str, Any]],
    observation_map: dict[tuple[str, int], dict[str, Any]],
) -> int:
    matched_count = 0
    for result in results:
        observation = observation_map.get((result["address"], result["port"]))
        if not observation:
            continue

        matched_count += 1
        result["traffic_observed"] = bool(observation["traffic_observed"])
        result["listener_observed"] = bool(observation["listener_observed"])
        result["observed_states"] = list(observation["states"])
        result["observed_sample_count"] = int(observation["sample_count"])

    return matched_count


def is_loopback_address(address_text: str) -> bool:
    try:
        return ip_address(address_text).is_loopback
    except ValueError:
        return False


def is_unspecified_address(address_text: str) -> bool:
    try:
        return ip_address(address_text).is_unspecified
    except ValueError:
        return False


def decode_socket_address(encoded: str, family: int) -> tuple[str, int]:
    host_hex, port_hex = encoded.split(":", 1)
    return decode_ip_address(host_hex, family), int(port_hex, 16)


def decode_ip_address(host_hex: str, family: int) -> str:
    raw = bytes.fromhex(host_hex)
    if family == socket.AF_INET:
        return socket.inet_ntop(family, raw[::-1])

    if family == socket.AF_INET6:
        reordered = b"".join(raw[offset : offset + 4][::-1] for offset in range(0, 16, 4))
        return socket.inet_ntop(family, reordered)

    raise ValueError(f"Unsupported address family: {family}")
