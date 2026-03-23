from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict


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
    traffic_observed: bool
    listener_observed: bool
    observed_states: list[str]
    observed_sample_count: int


class ExposureItem(ExposureCandidate, total=False):
    discovery_paths: list[str]
    related_objects: list[str]
    note: str
