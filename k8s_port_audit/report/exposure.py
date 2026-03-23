from __future__ import annotations

"""集中定义暴露类型标签和排序规则。

这样 discovery、reporting、probe 合并逻辑可以共享同一套分类口径。
"""

EXPOSURE_REASON_LABELS = {
    "service_external_ip": "ExternalIP",
    "service_load_balancer": "LoadBalancer",
    "service_node_port": "NodePort",
    "pod_host_port": "HostPort",
    "host_network_pod_port": "HostNetworkPod",
    "node_full_scan": "NodeListener",
}

EXPOSURE_PRIORITY = {
    "ExternalIP": 0,
    "LoadBalancer": 1,
    "NodePort": 2,
    "HostPort": 3,
    "HostNetworkPod": 4,
    "NodeListener": 5,
}

STATUS_PRIORITY = {
    "open": 0,
    "timeout": 1,
    "unreachable": 2,
    "closed": 3,
    "error": 4,
}


def exposure_type_for_reason(reason: str | None) -> str | None:
    if not reason:
        return None
    return EXPOSURE_REASON_LABELS.get(reason)


def exposure_priority(exposure_type: str | None) -> int:
    return EXPOSURE_PRIORITY.get(exposure_type or "", 99)


def status_priority(status: str | None) -> int:
    return STATUS_PRIORITY.get(status or "", 99)
