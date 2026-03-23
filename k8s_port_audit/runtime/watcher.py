from __future__ import annotations

"""基于 Kubernetes watch 的变更触发刷新。"""

import threading
from dataclasses import dataclass
from typing import Any, Callable

from ..settings.config import ScannerConfig, namespace_allowed
from .dependencies import client, watch
from .state import ScanCoordinator


@dataclass(frozen=True)
class WatchSpec:
    label: str
    list_call: Callable[..., Any]
    namespaced: bool = False


class KubernetesEventWatcher:
    """监听核心资源变更，并把扫描请求交给 ScanCoordinator 排队。"""

    def __init__(self, scanner_config: ScannerConfig, scan_coordinator: ScanCoordinator) -> None:
        self.scanner_config = scanner_config
        self.scan_coordinator = scan_coordinator
        self.core_api = client.CoreV1Api() if client is not None else None
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._watchers: list[Any] = []
        self._lock = threading.Lock()
        self._resource_signatures: dict[tuple[str, str | None, str], Any] = {}

    def enabled(self) -> bool:
        return (
            self.scanner_config.watch_kubernetes_events
            and self.core_api is not None
            and watch is not None
        )

    def start(self) -> None:
        if not self.enabled():
            return

        for spec in self.watch_specs():
            thread = threading.Thread(
                target=self.watch_resource_forever,
                args=(spec,),
                name=f"k8s-watch-{spec.label.lower()}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

        print("Kubernetes 事件触发刷新已启用。", flush=True)

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            watchers = list(self._watchers)

        for watcher_instance in watchers:
            try:
                watcher_instance.stop()
            except Exception:
                continue

        for thread in self._threads:
            thread.join(timeout=1.5)

    def watch_specs(self) -> list[WatchSpec]:
        if self.core_api is None:
            return []

        return [
            WatchSpec("Pod", self.core_api.list_pod_for_all_namespaces, namespaced=True),
            WatchSpec("Service", self.core_api.list_service_for_all_namespaces, namespaced=True),
            WatchSpec("Node", self.core_api.list_node, namespaced=False),
        ]

    @staticmethod
    def object_namespace(resource: Any) -> str | None:
        return getattr(getattr(resource, "metadata", None), "namespace", None)

    @staticmethod
    def object_name(resource: Any) -> str:
        return getattr(getattr(resource, "metadata", None), "name", None) or "-"

    def object_key(self, spec: WatchSpec, resource: Any) -> tuple[str, str | None, str]:
        return (spec.label, self.object_namespace(resource), self.object_name(resource))

    def pod_signature(self, pod: Any) -> tuple[Any, ...] | None:
        namespace = self.object_namespace(pod)
        if not namespace_allowed(namespace, self.scanner_config):
            return None
        if getattr(getattr(pod, "status", None), "phase", None) != "Running":
            return None

        host_network = bool(getattr(getattr(pod, "spec", None), "host_network", False))
        node_name = getattr(getattr(pod, "spec", None), "node_name", None)
        host_ports: list[tuple[Any, ...]] = []
        host_network_ports: list[tuple[Any, ...]] = []

        for container in getattr(getattr(pod, "spec", None), "containers", None) or []:
            for port_def in getattr(container, "ports", None) or []:
                protocol = (getattr(port_def, "protocol", None) or "TCP").upper()
                if protocol != "TCP":
                    continue

                host_port = getattr(port_def, "host_port", None)
                if self.scanner_config.scan_host_ports and host_port:
                    host_ports.append(
                        (
                            container.name,
                            getattr(port_def, "name", None),
                            int(host_port),
                            getattr(port_def, "host_ip", None) or "",
                            int(getattr(port_def, "container_port", None) or 0),
                        )
                    )

                container_port = getattr(port_def, "container_port", None)
                if self.scanner_config.scan_host_network_ports and host_network and container_port:
                    host_network_ports.append(
                        (
                            container.name,
                            getattr(port_def, "name", None),
                            int(container_port),
                        )
                    )

        if not host_ports and not host_network_ports:
            return None

        return (
            node_name,
            host_network,
            tuple(sorted(host_ports)),
            tuple(sorted(host_network_ports)),
        )

    def service_signature(self, service: Any) -> tuple[Any, ...] | None:
        namespace = self.object_namespace(service)
        if not namespace_allowed(namespace, self.scanner_config):
            return None

        service_spec = getattr(service, "spec", None)
        service_status = getattr(service, "status", None)
        external_ips: list[str] = []
        load_balancer_targets: list[str] = []
        node_ports: list[tuple[Any, ...]] = []

        for external_ip in getattr(service_spec, "external_ips", None) or []:
            if self.scanner_config.scan_service_external_ips and external_ip:
                external_ips.append(str(external_ip))

        load_balancer = getattr(service_status, "load_balancer", None)
        for ingress in getattr(load_balancer, "ingress", None) or []:
            ingress_host = getattr(ingress, "ip", None) or getattr(ingress, "hostname", None)
            if self.scanner_config.scan_service_external_ips and ingress_host:
                load_balancer_targets.append(str(ingress_host))

        for port_def in getattr(service_spec, "ports", None) or []:
            protocol = (getattr(port_def, "protocol", None) or "TCP").upper()
            if protocol != "TCP":
                continue
            if self.scanner_config.scan_node_ports and getattr(port_def, "node_port", None):
                node_ports.append(
                    (
                        getattr(port_def, "name", None),
                        int(port_def.node_port),
                        int(getattr(port_def, "port", None) or 0),
                    )
                )

        if not external_ips and not load_balancer_targets and not node_ports:
            return None

        return (
            getattr(service_spec, "type", None) or "ClusterIP",
            tuple(sorted(set(external_ips))),
            tuple(sorted(set(load_balancer_targets))),
            tuple(sorted(node_ports)),
        )

    @staticmethod
    def node_signature(node: Any) -> tuple[Any, ...] | None:
        addresses = [
            (address.type, address.address)
            for address in getattr(getattr(node, "status", None), "addresses", None) or []
            if address.type in {"InternalIP", "ExternalIP"} and address.address
        ]
        if not addresses:
            return None
        return tuple(sorted(addresses))

    def exposure_signature(self, spec: WatchSpec, resource: Any) -> tuple[Any, ...] | None:
        if spec.label == "Pod":
            return self.pod_signature(resource)
        if spec.label == "Service":
            return self.service_signature(resource)
        if spec.label == "Node":
            return self.node_signature(resource)
        return None

    def initial_resource_version(self, spec: WatchSpec) -> str | None:
        response = spec.list_call(watch=False, _request_timeout=30)
        metadata = getattr(response, "metadata", None)
        return getattr(metadata, "resource_version", None)

    def register_watcher(self, watcher_instance: Any) -> None:
        with self._lock:
            self._watchers.append(watcher_instance)

    def unregister_watcher(self, watcher_instance: Any) -> None:
        with self._lock:
            if watcher_instance in self._watchers:
                self._watchers.remove(watcher_instance)

    def should_refresh_for_event(self, spec: WatchSpec, event_type: str, resource: Any) -> bool:
        key = self.object_key(spec, resource)
        signature = self.exposure_signature(spec, resource)

        with self._lock:
            previous_signature = self._resource_signatures.get(key)

            if event_type == "DELETED":
                if key in self._resource_signatures:
                    del self._resource_signatures[key]
                return previous_signature is not None or signature is not None

            if signature is None:
                if key in self._resource_signatures:
                    del self._resource_signatures[key]
                    return True
                return False

            if previous_signature == signature:
                return False

            self._resource_signatures[key] = signature
            return True

    def request_scan_for_event(self, spec: WatchSpec, event_type: str, resource: Any) -> None:
        namespace = self.object_namespace(resource)
        object_name = self.object_name(resource)
        full_scan = spec.label == "Node"
        service_refs: set[tuple[str, str]] = set()
        pod_refs: set[tuple[str, str]] = set()

        if namespace and spec.label == "Service":
            service_refs.add((namespace, object_name))
        if namespace and spec.label == "Pod":
            pod_refs.add((namespace, object_name))

        if namespace:
            reason = f"{spec.label} {event_type} {namespace}/{object_name}"
        else:
            reason = f"{spec.label} {event_type} {object_name}"

        self.scan_coordinator.request_scan(
            "k8s_watch",
            reason=reason,
            full_scan=full_scan,
            service_refs=service_refs,
            pod_refs=pod_refs,
        )
        refresh_kind = "完整刷新" if full_scan else "局部刷新"
        print(f"检测到 Kubernetes 变更，准备{refresh_kind}: {reason}", flush=True)

    def watch_resource_forever(self, spec: WatchSpec) -> None:
        backoff_seconds = 2.0

        while not self._stop_event.is_set():
            watcher_instance = watch.Watch() if watch is not None else None
            if watcher_instance is None:
                return

            self.register_watcher(watcher_instance)
            try:
                resource_version = self.initial_resource_version(spec)
                stream = watcher_instance.stream(
                    spec.list_call,
                    resource_version=resource_version,
                    timeout_seconds=self.scanner_config.event_watch_timeout_seconds,
                )
                for event in stream:
                    if self._stop_event.is_set():
                        watcher_instance.stop()
                        break

                    resource = event.get("object")
                    event_type = str(event.get("type") or "UNKNOWN")
                    if resource is None:
                        continue

                    if not self.should_refresh_for_event(spec, event_type, resource):
                        continue
                    self.request_scan_for_event(spec, event_type, resource)

                backoff_seconds = 2.0
            except Exception as exc:
                if self._stop_event.is_set():
                    break

                print(
                    f"Kubernetes 事件监听异常，{backoff_seconds:.0f} 秒后重连 "
                    f"({spec.label}): {type(exc).__name__}: {exc}",
                    flush=True,
                )
                if self._stop_event.wait(backoff_seconds):
                    break
                backoff_seconds = min(backoff_seconds * 2, 30.0)
            finally:
                try:
                    watcher_instance.stop()
                except Exception:
                    pass
                self.unregister_watcher(watcher_instance)
