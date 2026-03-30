from __future__ import annotations

from typing import Any

from ..control.service_controls import (
    MANAGED_LABEL,
    OWNER_NAMESPACE_ANNOTATION,
    OWNER_SERVICE_ANNOTATION,
)
from ..domain import DiscoverySnapshot, NodeCandidate, ProbeTarget
from ..settings.config import ScannerConfig, namespace_allowed
from .traffic import is_unspecified_address


class HostExposureDiscovery:
    """把 Kubernetes 对象转换成宿主机地址上的探测目标。"""

    def __init__(self, core_api: Any, scanner_config: ScannerConfig) -> None:
        self.core_api = core_api
        self.scanner_config = scanner_config

    def namespace_allowed(self, namespace: str | None) -> bool:
        return namespace_allowed(namespace, self.scanner_config)

    @staticmethod
    def service_selected(
        service: Any,
        service_refs: set[tuple[str, str]] | None,
    ) -> bool:
        if not service_refs:
            return True
        return (service.metadata.namespace, service.metadata.name) in service_refs

    @staticmethod
    def pod_selected(
        pod: Any,
        pod_refs: set[tuple[str, str]] | None,
    ) -> bool:
        if not pod_refs:
            return True
        return (pod.metadata.namespace, pod.metadata.name) in pod_refs

    @staticmethod
    def add_target(
        target_map: dict[tuple[str, int], ProbeTarget],
        address: str | None,
        port: int | None,
        source: dict[str, Any],
    ) -> None:
        if not address or not port:
            return

        # 探测维度按 address:port 去重，同时保留多条 source 供后续归因。
        key = (address, int(port))
        target = target_map.get(key)
        if target is None:
            target = ProbeTarget(address=address, port=int(port))
            target_map[key] = target

        if source not in target.sources:
            target.sources.append(source)

    def collect_node_addresses(self, inventory: dict[str, int]) -> list[dict[str, str]]:
        nodes = self.core_api.list_node(watch=False).items
        inventory["nodes_seen"] = len(nodes)
        node_addresses: list[dict[str, str]] = []
        seen_addresses: set[tuple[str, str]] = set()

        for node in nodes:
            for address in node.status.addresses or []:
                if address.type not in {"InternalIP", "ExternalIP"} or not address.address:
                    continue

                key = (node.metadata.name, address.address)
                if key in seen_addresses:
                    continue

                seen_addresses.add(key)
                node_addresses.append(
                    {
                        "name": node.metadata.name,
                        "address": address.address,
                        "address_type": address.type,
                    }
                )

        inventory["nodes_eligible"] = len(node_addresses)
        return node_addresses

    @staticmethod
    def build_node_candidates(node_addresses: list[dict[str, str]]) -> list[NodeCandidate]:
        return [
            NodeCandidate(
                name=node["name"],
                address=node["address"],
                address_type=node.get("address_type"),
            )
            for node in node_addresses
        ]

    @staticmethod
    def index_node_addresses(node_addresses: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
        indexed: dict[str, list[dict[str, str]]] = {}
        for node in node_addresses:
            indexed.setdefault(node["name"], []).append(node)
        return indexed

    @staticmethod
    def build_inventory_template() -> dict[str, int]:
        return {
            "nodes_seen": 0,
            "nodes_eligible": 0,
            "services_seen": 0,
            "services_eligible": 0,
            "pods_seen": 0,
            "pods_eligible": 0,
            "service_external_ip_targets": 0,
            "service_load_balancer_targets": 0,
            "service_node_port_targets": 0,
            "pod_host_port_targets": 0,
            "host_network_port_targets": 0,
            "full_node_scan_nodes": 0,
            "full_node_scan_ports_per_node": 0,
            "full_node_scan_targets": 0,
            "unique_targets": 0,
        }

    @staticmethod
    def service_source_name(service: Any) -> str:
        metadata = getattr(service, "metadata", None)
        labels = dict(getattr(metadata, "labels", None) or {})
        annotations = dict(getattr(metadata, "annotations", None) or {})
        if labels.get(MANAGED_LABEL) != "true":
            return getattr(metadata, "name", None) or "-"
        owner_namespace = annotations.get(OWNER_NAMESPACE_ANNOTATION)
        owner_service = annotations.get(OWNER_SERVICE_ANNOTATION)
        if owner_namespace and owner_service and owner_namespace == getattr(metadata, "namespace", None):
            return owner_service
        return getattr(metadata, "name", None) or "-"

    def collect_service_targets(
        self,
        target_map: dict[tuple[str, int], ProbeTarget],
        inventory: dict[str, int],
        node_addresses: list[dict[str, str]],
        service_refs: set[tuple[str, str]] | None = None,
    ) -> None:
        if not (self.scanner_config.scan_service_external_ips or self.scanner_config.scan_node_ports):
            return

        # 仅保留最终映射到宿主机地址的 Service 路径。
        services = self.core_api.list_service_for_all_namespaces(watch=False).items
        inventory["services_seen"] = len(services)

        for service in services:
            namespace = service.metadata.namespace
            if not self.namespace_allowed(namespace):
                continue
            if not self.service_selected(service, service_refs):
                continue

            inventory["services_eligible"] += 1
            service_spec = service.spec
            service_status = getattr(service, "status", None)
            service_type = service_spec.type or "ClusterIP"
            source_name = self.service_source_name(service)

            for port_def in service_spec.ports or []:
                protocol = (port_def.protocol or "TCP").upper()
                if protocol != "TCP" or not port_def.port:
                    continue

                service_port = int(port_def.port)
                source_common = {
                    "kind": "service",
                    "namespace": namespace,
                    "name": source_name,
                    "service_name": source_name,
                    "actual_service_name": service.metadata.name,
                    "service_type": service_type,
                    "labels": dict(getattr(service.metadata, "labels", None) or {}),
                    "port_name": port_def.name,
                    "target_port": str(port_def.target_port) if port_def.target_port is not None else None,
                }

                if self.scanner_config.scan_service_external_ips:
                    for external_ip in getattr(service_spec, "external_ips", None) or []:
                        self.add_target(
                            target_map,
                            external_ip,
                            service_port,
                            {
                                **source_common,
                                "reason": "service_external_ip",
                            },
                        )
                        inventory["service_external_ip_targets"] += 1

                    load_balancer = getattr(service_status, "load_balancer", None)
                    for ingress in getattr(load_balancer, "ingress", None) or []:
                        ingress_host = getattr(ingress, "ip", None) or getattr(ingress, "hostname", None)
                        self.add_target(
                            target_map,
                            ingress_host,
                            service_port,
                            {
                                **source_common,
                                "reason": "service_load_balancer",
                            },
                        )
                        inventory["service_load_balancer_targets"] += 1

                if self.scanner_config.scan_node_ports and port_def.node_port:
                    # NodePort 对应“每个节点地址 + nodePort”的组合。
                    for node in node_addresses:
                        self.add_target(
                            target_map,
                            node["address"],
                            int(port_def.node_port),
                            {
                                **source_common,
                                "reason": "service_node_port",
                                "node_name": node["name"],
                            },
                        )
                        inventory["service_node_port_targets"] += 1

    def collect_partial_node_port_targets(
        self,
        target_map: dict[tuple[str, int], ProbeTarget],
        inventory: dict[str, int],
        node_addresses: list[dict[str, str]],
        node_port_refs: set[int] | None = None,
    ) -> None:
        if not node_port_refs:
            return

        # 业务 Service 端口治理只需要补扫受影响的 NodePort。
        # 这里不做整轮 1-65535，只对“变更前/变更后”涉及到的节点端口做定点刷新。
        for node in node_addresses:
            for port in sorted(node_port_refs):
                self.add_target(
                    target_map,
                    node["address"],
                    int(port),
                    {
                        "kind": "node",
                        "namespace": "-",
                        "name": node["name"],
                        "node_name": node["name"],
                        "address_type": node.get("address_type"),
                        "reason": "node_full_scan",
                    },
                )

    def collect_pod_targets(
        self,
        target_map: dict[tuple[str, int], ProbeTarget],
        inventory: dict[str, int],
        node_addresses_by_name: dict[str, list[dict[str, str]]],
        pod_refs: set[tuple[str, str]] | None = None,
    ) -> None:
        if not (self.scanner_config.scan_host_ports or self.scanner_config.scan_host_network_ports):
            return

        # 普通 PodIP 不纳入结果，仅保留映射到节点网络命名空间的声明端口。
        pods = self.core_api.list_pod_for_all_namespaces(watch=False).items
        inventory["pods_seen"] = len(pods)

        for pod in pods:
            namespace = pod.metadata.namespace
            if not self.namespace_allowed(namespace):
                continue
            if not self.pod_selected(pod, pod_refs):
                continue
            if pod.status.phase != "Running":
                continue

            node_name = getattr(pod.spec, "node_name", None)
            if not node_name:
                continue

            inventory["pods_eligible"] += 1
            host_network = bool(getattr(pod.spec, "host_network", False))
            node_addresses = node_addresses_by_name.get(node_name, [])
            if not node_addresses:
                continue

            for container in pod.spec.containers or []:
                for port_def in container.ports or []:
                    protocol = (port_def.protocol or "TCP").upper()
                    if protocol != "TCP":
                        continue

                    if self.scanner_config.scan_host_ports and getattr(port_def, "host_port", None):
                        host_port = int(port_def.host_port)
                        host_ip = getattr(port_def, "host_ip", None)
                        if host_ip and not is_unspecified_address(host_ip):
                            host_addresses = [host_ip]
                        else:
                            # 未显式指定 hostIP 时，hostPort 需要展开到当前节点的全部可探测地址。
                            host_addresses = [item["address"] for item in node_addresses]

                        for address in sorted(set(host_addresses)):
                            self.add_target(
                                target_map,
                                address,
                                host_port,
                                {
                                    "kind": "pod",
                                    "namespace": namespace,
                                    "name": pod.metadata.name,
                                    "labels": dict(getattr(pod.metadata, "labels", None) or {}),
                                    "container": container.name,
                                    "node_name": node_name,
                                    "reason": "pod_host_port",
                                    "port_name": port_def.name,
                                    "target_port": str(port_def.container_port) if port_def.container_port else None,
                                },
                            )
                            inventory["pod_host_port_targets"] += 1

                    if (
                        self.scanner_config.scan_host_network_ports
                        and host_network
                        and getattr(port_def, "container_port", None)
                    ):
                        # hostNetwork Pod 共享节点网络命名空间，containerPort 对外表现为节点地址上的端口。
                        for node in node_addresses:
                            self.add_target(
                                target_map,
                                node["address"],
                                int(port_def.container_port),
                                {
                                    "kind": "pod",
                                    "namespace": namespace,
                                    "name": pod.metadata.name,
                                    "labels": dict(getattr(pod.metadata, "labels", None) or {}),
                                    "container": container.name,
                                    "node_name": node_name,
                                    "reason": "host_network_pod_port",
                                    "port_name": port_def.name,
                                },
                            )
                            inventory["host_network_port_targets"] += 1

    def discover(
        self,
        service_refs: set[tuple[str, str]] | None = None,
        pod_refs: set[tuple[str, str]] | None = None,
        node_port_refs: set[int] | None = None,
    ) -> DiscoverySnapshot:
        inventory = self.build_inventory_template()
        target_map: dict[tuple[str, int], ProbeTarget] = {}

        node_addresses = self.collect_node_addresses(inventory)
        node_candidates = self.build_node_candidates(node_addresses)
        node_addresses_by_name = self.index_node_addresses(node_addresses)

        self.collect_service_targets(target_map, inventory, node_addresses, service_refs=service_refs)
        self.collect_partial_node_port_targets(
            target_map,
            inventory,
            node_addresses,
            node_port_refs=node_port_refs,
        )
        self.collect_pod_targets(
            target_map,
            inventory,
            node_addresses_by_name,
            pod_refs=pod_refs,
        )

        inventory["unique_targets"] = len(target_map)
        targets = sorted(target_map.values(), key=lambda item: (item.address, item.port))
        return DiscoverySnapshot(
            targets=targets,
            node_candidates=node_candidates,
            inventory=inventory,
        )
