from __future__ import annotations

"""把原始探测结果整理成页面使用的暴露对象。"""

from typing import Any

from ..domain import ExposureCandidate, ExposureItem, ProbeResult, TargetSource
from .exposure import exposure_priority, exposure_type_for_reason, status_priority
from .platform import platform_role_for_candidate


def build_exposure_items(results: list[ProbeResult]) -> list[ExposureItem]:
    """按 address:port 收口原始探测结果。"""

    items_by_target: dict[tuple[str, int], ExposureItem] = {}

    for result in results:
        candidates = build_exposure_candidates(result)
        if not candidates:
            continue

        key = (result["address"], result["port"])
        primary_candidate = select_primary_candidate(candidates)
        item = items_by_target.get(key)

        if item is None:
            item = ExposureItem(
                **primary_candidate,
                discovery_paths=[],
                related_objects=[],
            )
            items_by_target[key] = item
        else:
            promote_primary_candidate(item, primary_candidate)

        merge_result_evidence(item, primary_candidate)
        merge_candidate_relationships(item, candidates)

    items = list(items_by_target.values())
    for item in items:
        finalize_item(item)

    items.sort(
        key=lambda item: (
            status_priority(item.get("status")),
            exposure_priority(item.get("exposure_type")),
            item.get("namespace", "-"),
            item.get("resource_name", "-"),
            item.get("address", ""),
            int(item.get("port", 0)),
        )
    )
    return items


def build_resource_groups(items: list[ExposureItem]) -> list[dict[str, Any]]:
    object_groups: dict[tuple[str, str, str], dict[str, Any]] = {}

    for item in items:
        group_key = (
            item.get("namespace", "-"),
            item.get("group_name", "-"),
            item.get("resource_kind", "Service"),
        )
        group = object_groups.get(group_key)
        if group is None:
            group = {
                "namespace": item.get("namespace", "-"),
                "resource_name": item.get("group_name", "-"),
                "resource_kind": item.get("resource_kind", "Service"),
                "service_type": item.get("service_type"),
                "items": [],
            }
            object_groups[group_key] = group
        group["items"].append(item)

    grouped_items: list[dict[str, Any]] = []
    for group in object_groups.values():
        group_status_counts: dict[str, int] = {}
        exposure_types: set[str] = set()
        open_targets: set[str] = set()

        group["items"].sort(
            key=lambda item: (
                status_priority(item.get("status")),
                exposure_priority(item.get("exposure_type")),
                item.get("address", ""),
                int(item.get("port", 0)),
            )
        )

        for item in group["items"]:
            status = item.get("status", "unknown")
            group_status_counts[status] = group_status_counts.get(status, 0) + 1
            exposure_types.add(item.get("exposure_type", ""))
            if status == "open":
                open_targets.add(f"{item.get('address')}:{item.get('port')}")

        grouped_items.append(
            {
                "namespace": group["namespace"],
                "resource_name": group["resource_name"],
                "resource_kind": group["resource_kind"],
                "service_type": group["service_type"],
                "items": group["items"],
                "status_counts": group_status_counts,
                "exposure_types": sorted(exposure_types, key=exposure_priority),
                "open_target_count": len(open_targets),
                "open_targets": sorted(open_targets),
            }
        )

    grouped_items.sort(
        key=lambda item: (
            -item["open_target_count"],
            item["namespace"],
            item["resource_kind"],
            item["resource_name"],
        )
    )
    return grouped_items


def summarize_exposure_items(items: list[ExposureItem]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    exposure_type_counts: dict[str, int] = {}
    unique_resources: set[tuple[str, str, str]] = set()
    unique_addresses: set[str] = set()
    namespaces: set[str] = set()

    for item in items:
        status = item.get("status", "unknown")
        exposure_type = item.get("exposure_type", "Unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        exposure_type_counts[exposure_type] = exposure_type_counts.get(exposure_type, 0) + 1
        unique_resources.add(
            (
                item.get("namespace", "-"),
                item.get("resource_kind", "Service"),
                item.get("resource_name", "-"),
            )
        )
        unique_addresses.add(item.get("address", ""))
        namespaces.add(item.get("namespace", "-"))

    return {
        "item_count": len(items),
        "resource_count": len(unique_resources),
        "namespace_count": len(namespaces),
        "unique_address_count": len(unique_addresses),
        "open_count": status_counts.get("open", 0),
        "traffic_observed_count": sum(
            1 for item in items if item.get("traffic_observed") or item.get("listener_observed")
        ),
        "status_counts": status_counts,
        "exposure_type_counts": exposure_type_counts,
    }


def build_exposure_candidates(result: ProbeResult) -> list[ExposureCandidate]:
    candidates: list[ExposureCandidate] = []
    for source in result.get("sources", []):
        candidate = build_exposure_candidate(result, source)
        if candidate:
            candidates.append(candidate)
    return candidates


def build_exposure_candidate(
    result: ProbeResult,
    source: TargetSource,
) -> ExposureCandidate | None:
    reason = source.get("reason")
    exposure_type = exposure_type_for_reason(reason)
    if not exposure_type:
        return None

    namespace = source.get("namespace") or "-"
    resource_kind = "Node" if reason == "node_full_scan" else source.get("kind", "service").title()
    resource_name = source.get("name") or source.get("service_name") or source.get("node_name") or "-"
    group_name = source.get("service_name") or resource_name

    candidate = ExposureCandidate(
        namespace=namespace,
        resource_kind=resource_kind,
        resource_name=resource_name,
        group_name=group_name,
        service_type=source.get("service_type"),
        exposure_type=exposure_type,
        address=result["address"],
        port=result["port"],
        status=result["status"],
        latency_ms=result.get("latency_ms"),
        error=result.get("error"),
        port_name=source.get("port_name"),
        target_port=source.get("target_port"),
        node_name=source.get("node_name"),
        container=source.get("container"),
        reason=reason,
        traffic_observed=bool(result.get("traffic_observed")),
        listener_observed=bool(result.get("listener_observed")),
        observed_states=list(result.get("observed_states") or []),
        observed_sample_count=int(result.get("observed_sample_count") or 0),
        labels=dict(source.get("labels") or {}),
    )
    candidate["platform_role"] = platform_role_for_candidate(candidate)
    return candidate


def select_primary_candidate(candidates: list[ExposureCandidate]) -> ExposureCandidate:
    return min(
        candidates,
        key=lambda item: (
            exposure_priority(item.get("exposure_type")),
            item.get("namespace", "-"),
            item.get("resource_name", "-"),
        ),
    )


def promote_primary_candidate(item: ExposureItem, candidate: ExposureCandidate) -> None:
    if exposure_priority(candidate.get("exposure_type")) >= exposure_priority(item.get("exposure_type")):
        return

    # 页面主分类只展示一个最明确的暴露类型，其余路径保留在 discovery_paths 中。
    for field_name in (
        "namespace",
        "resource_kind",
        "resource_name",
        "group_name",
        "service_type",
        "exposure_type",
        "latency_ms",
        "error",
        "port_name",
        "target_port",
        "node_name",
        "container",
        "reason",
        "platform_role",
    ):
        item[field_name] = candidate.get(field_name)


def merge_result_evidence(item: ExposureItem, candidate: ExposureCandidate) -> None:
    item["traffic_observed"] = bool(item.get("traffic_observed")) or bool(candidate.get("traffic_observed"))
    item["listener_observed"] = bool(item.get("listener_observed")) or bool(candidate.get("listener_observed"))
    item["observed_sample_count"] = max(
        int(item.get("observed_sample_count") or 0),
        int(candidate.get("observed_sample_count") or 0),
    )

    observed_states = item.setdefault("observed_states", [])
    for state in candidate.get("observed_states", []):
        if state not in observed_states:
            observed_states.append(state)


def merge_candidate_relationships(
    item: ExposureItem,
    candidates: list[ExposureCandidate],
) -> None:
    discovery_paths = item.setdefault("discovery_paths", [])
    related_objects = item.setdefault("related_objects", [])
    platform_roles = item.setdefault("platform_roles", [])

    for candidate in candidates:
        exposure_type = candidate.get("exposure_type")
        if exposure_type and exposure_type not in discovery_paths:
            discovery_paths.append(exposure_type)

        related_object = format_related_object(candidate)
        if related_object not in related_objects:
            related_objects.append(related_object)

        platform_role = candidate.get("platform_role")
        if platform_role:
            if platform_role not in platform_roles:
                platform_roles.append(platform_role)
        elif candidate.get("resource_kind") != "Node":
            # NodeListener 是宿主机直接暴露面的旁路证据，不应把已经命中的系统组件标记冲掉。
            item["business_candidate_present"] = True


def finalize_item(item: ExposureItem) -> None:
    discovery_paths = item.setdefault("discovery_paths", [])
    related_objects = item.setdefault("related_objects", [])
    platform_roles = item.setdefault("platform_roles", [])
    discovery_paths.sort(key=exposure_priority)
    related_objects.sort()
    platform_roles.sort()

    if item.pop("business_candidate_present", False) or not platform_roles:
        item["platform_role"] = None
        item["platform_roles"] = []
    elif item.get("platform_role") not in platform_roles:
        item["platform_role"] = platform_roles[0]

    note_parts = [
        ", ".join(discovery_paths),
        "; ".join(related_objects[:3]),
    ]
    if item.get("traffic_observed") and item.get("observed_states"):
        note_parts.append("流量状态 " + ", ".join(item["observed_states"]))
    elif item.get("listener_observed"):
        note_parts.append("检测到监听状态")
    item["note"] = " / ".join(part for part in note_parts if part)


def format_related_object(candidate: ExposureCandidate) -> str:
    namespace = candidate.get("namespace")
    resource_kind = candidate.get("resource_kind", "Service")
    resource_name = candidate.get("resource_name", "-")

    if namespace and namespace != "-":
        return f"{resource_kind} {namespace}/{resource_name}"
    return f"{resource_kind} {resource_name}"
