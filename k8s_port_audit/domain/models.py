from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict


@dataclass
class ScanRequest:
    source: str
    reason: str | None = None
    full_scan: bool = True
    service_refs: set[tuple[str, str]] = field(default_factory=set)
    pod_refs: set[tuple[str, str]] = field(default_factory=set)

    def merged_with(self, other: "ScanRequest") -> "ScanRequest":
        return ScanRequest(
            source=other.source,
            reason=other.reason or self.reason,
            full_scan=self.full_scan or other.full_scan,
            service_refs=set(self.service_refs) | set(other.service_refs),
            pod_refs=set(self.pod_refs) | set(other.pod_refs),
        )


@dataclass
class ProbeTarget:
    address: str
    port: int
    sources: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class NodeCandidate:
    name: str
    address: str
    address_type: str | None = None


@dataclass
class DiscoverySnapshot:
    targets: list[ProbeTarget]
    node_candidates: list[NodeCandidate]
    inventory: dict[str, int]


class TargetSource(TypedDict, total=False):
    kind: str
    namespace: str
    name: str
    service_name: str
    service_type: str
    node_name: str
    container: str
    reason: str
    port_name: str | None
    target_port: str | None
    address_type: str | None
    labels: dict[str, str]


class ProbeResult(TypedDict, total=False):
    address: str
    port: int
    status: str
    latency_ms: float | None
    error: str | None
    started_at: str
    sources: list[TargetSource]
    traffic_observed: bool
    listener_observed: bool
    observed_states: list[str]
    observed_sample_count: int


class ExposureCandidate(TypedDict, total=False):
    namespace: str
    resource_kind: str
    resource_name: str
    group_name: str
    service_type: str | None
    exposure_type: str
    address: str
    port: int
    status: str
    latency_ms: float | None
    error: str | None
    port_name: str | None
    target_port: str | None
    node_name: str | None
    container: str | None
    reason: str | None
    platform_role: str | None
    traffic_observed: bool
    listener_observed: bool
    observed_states: list[str]
    observed_sample_count: int
    labels: dict[str, str]


class ExposureItem(ExposureCandidate, total=False):
    discovery_paths: list[str]
    related_objects: list[str]
    platform_roles: list[str]
    business_candidate_present: bool
    note: str
