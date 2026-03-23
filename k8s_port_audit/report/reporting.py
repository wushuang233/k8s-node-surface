from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..domain import NodeCandidate
from .exposure_summary import build_exposure_items, build_resource_groups, summarize_exposure_items


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_methodology_summary() -> dict[str, Any]:
    return {
        "title": "暴露面判定逻辑",
        "steps": [
            "对 Node 的 InternalIP 和 ExternalIP 在 full_node_tcp_ports 范围内执行 TCP 建连。",
            "结合 Kubernetes 元数据，对开放端口按 ExternalIP、LoadBalancer、NodePort、HostPort、HostNetwork、NodeListener 分类。",
            "读取当前节点的 /proc TCP 表，补充监听与活跃连接证据。",
        ],
        "focus": "结果仅保留宿主机地址上的 TCP 暴露面；ClusterIP、Endpoint、普通 PodIP 不纳入结果。",
        "limitations": [
            "被动 TCP 证据仅覆盖当前运行节点。",
            "最终公网可达性仍受 ACL、防火墙、NAT、WAF 等因素影响。",
            "当前仅支持 TCP。",
        ],
    }


def build_scan_summary(inventory: dict[str, int], results: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    open_targets: list[str] = []
    traffic_observed_count = 0

    for result in results:
        status = result["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "open":
            open_targets.append(f"{result['address']}:{result['port']}")
        if result.get("traffic_observed") or result.get("listener_observed"):
            traffic_observed_count += 1

    return {
        "inventory": inventory,
        "result_counts": status_counts,
        "open_target_count": len(open_targets),
        "open_targets": open_targets,
        "traffic_observed_count": traffic_observed_count,
    }


def build_node_inventory(node_candidates: list[NodeCandidate]) -> list[dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}

    for candidate in node_candidates:
        entry = nodes.get(candidate.name)
        if entry is None:
            entry = {
                "name": candidate.name,
                "addresses": [],
            }
            nodes[candidate.name] = entry

        address_record = {
            "address": candidate.address,
            "address_type": candidate.address_type,
        }
        if address_record not in entry["addresses"]:
            entry["addresses"].append(address_record)

    for entry in nodes.values():
        entry["addresses"].sort(
            key=lambda item: (
                0 if item.get("address_type") == "InternalIP" else 1,
                item.get("address") or "",
            )
        )

    return sorted(nodes.values(), key=lambda item: item["name"])


def build_host_exposure_summary(
    results: list[dict[str, Any]],
    node_candidates: list[NodeCandidate] | None = None,
) -> dict[str, Any]:
    # 先把 address:port 收口为稳定的页面对象，再单独构建对象分组和摘要统计。
    items = build_exposure_items(results)
    grouped_items = build_resource_groups(items)
    summary = summarize_exposure_items(items)

    return {
        "summary": summary,
        "items": items,
        "resource_groups": grouped_items,
        "node_inventory": build_node_inventory(node_candidates or []),
    }


def emit_report(report: dict[str, Any], output_path: str | None, pretty_json: bool) -> None:
    indent = 2 if pretty_json else None
    payload = json.dumps(report, ensure_ascii=False, indent=indent)
    print(payload, flush=True)

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
