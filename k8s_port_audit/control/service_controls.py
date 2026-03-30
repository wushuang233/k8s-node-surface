from __future__ import annotations

import hashlib
from typing import Any

from ..domain import ExposureCandidate
from ..report.platform import platform_role_for_candidate
from ..runtime.dependencies import ApiException, client
from ..settings.config import ScannerConfig, namespace_allowed

MANAGED_LABEL = "k8s-port-audit.io/managed-exposure"
MANAGED_BY_VALUE = "true"
OWNER_NAMESPACE_ANNOTATION = "k8s-port-audit.io/original-namespace"
OWNER_SERVICE_ANNOTATION = "k8s-port-audit.io/original-service"
PUBLIC_TYPE_ANNOTATION = "k8s-port-audit.io/public-service-type"

SUPPORTED_SERVICE_TYPES = {"ClusterIP", "NodePort", "LoadBalancer"}
PUBLIC_SERVICE_TYPES = {"NodePort", "LoadBalancer"}


class ServiceControlError(RuntimeError):
    """业务 Service 治理请求不满足执行条件。"""


class ServiceExposureController:
    """按端口治理业务 Service 的对外暴露。

    这里要兼顾两类场景：
    1. 原始 Service 是 ClusterIP，需要按端口对外打开
    2. 原始 Service 已经是 NodePort / LoadBalancer，需要按端口收回或改端口

    Kubernetes 原生 Service.type 是整条 Service 生效，不支持在同一个对象里只让部分端口对外。
    因此精细治理时采用“内部 Service + 受控公开 Service”的组合：
    - 原始 Service 保持或收回为 ClusterIP
    - 需要对外的端口放到受控公开 Service 里

    对已经是 NodePort / LoadBalancer 的业务 Service，第一次做精细治理时会先接管：
    - 把原始 Service 收回为 ClusterIP
    - 再把当前仍需对外的端口迁到受控公开 Service
    """

    def __init__(self, scanner_config: ScannerConfig) -> None:
        if client is None:
            raise RuntimeError("缺少 kubernetes 依赖")

        self.scanner_config = scanner_config
        self.core_api = client.CoreV1Api()

    @property
    def public_service_type(self) -> str:
        return self.scanner_config.service_control_public_service_type

    @property
    def node_port_range(self) -> tuple[int, int]:
        return self.scanner_config.service_control_node_port_range

    @property
    def node_port_range_spec(self) -> str:
        return self.scanner_config.service_control_node_port_range_spec

    @staticmethod
    def service_labels(service: Any) -> dict[str, str]:
        return dict(getattr(getattr(service, "metadata", None), "labels", None) or {})

    @staticmethod
    def service_annotations(service: Any) -> dict[str, str]:
        return dict(getattr(getattr(service, "metadata", None), "annotations", None) or {})

    @staticmethod
    def managed_service_name(namespace: str, service_name: str) -> str:
        digest = hashlib.sha1(f"{namespace}/{service_name}".encode("utf-8")).hexdigest()[:6]
        base = f"{service_name}-public"
        max_base_length = 63 - len(digest) - 1
        trimmed = base[:max_base_length].rstrip("-") or "svc"
        return f"{trimmed}-{digest}"

    @staticmethod
    def current_service_type(service: Any) -> str:
        return getattr(getattr(service, "spec", None), "type", None) or "ClusterIP"

    @classmethod
    def port_protocol(cls, port_def: Any) -> str:
        return (getattr(port_def, "protocol", None) or "TCP").upper()

    @classmethod
    def tcp_port_defs(cls, service: Any) -> list[Any]:
        return [
            port_def
            for port_def in getattr(getattr(service, "spec", None), "ports", None) or []
            if cls.port_protocol(port_def) == "TCP" and getattr(port_def, "port", None)
        ]

    @classmethod
    def has_non_tcp_ports(cls, service: Any) -> bool:
        for port_def in getattr(getattr(service, "spec", None), "ports", None) or []:
            if cls.port_protocol(port_def) != "TCP":
                return True
        return False

    @classmethod
    def port_key(cls, port_def: Any) -> str:
        return f"{cls.port_protocol(port_def)}:{int(getattr(port_def, 'port', 0) or 0)}"

    def normalize_public_port(self, public_port: Any, public_type: str) -> int | None:
        if public_port in {None, "", 0, "0"}:
            return None
        try:
            port_value = int(str(public_port).strip())
        except (TypeError, ValueError) as exc:
            raise ServiceControlError("外部端口必须是数字") from exc
        if not 1 <= port_value <= 65535:
            raise ServiceControlError("外部端口必须在 1-65535 之间")
        if public_type == "NodePort":
            start_port, end_port = self.node_port_range
            if not start_port <= port_value <= end_port:
                raise ServiceControlError(f"NodePort 必须在 {self.node_port_range_spec} 范围内")
        return port_value

    @staticmethod
    def managed_port_name(port_def: Any) -> str:
        original_name = getattr(port_def, "name", None)
        port_number = int(getattr(port_def, "port", 0) or 0)
        if original_name:
            suffix = str(port_number)
            prefix = original_name[: max(1, 15 - len(suffix) - 1)].rstrip("-")
            return f"{prefix}-{suffix}"[:15]
        return f"tcp-{port_number}"[:15]

    def is_managed_service(self, service: Any) -> bool:
        return self.service_labels(service).get(MANAGED_LABEL) == MANAGED_BY_VALUE

    def is_system_service(self, service: Any) -> bool:
        candidate = ExposureCandidate(
            namespace=getattr(getattr(service, "metadata", None), "namespace", None) or "-",
            resource_name=getattr(getattr(service, "metadata", None), "name", None) or "-",
            group_name=getattr(getattr(service, "metadata", None), "name", None) or "-",
            labels=self.service_labels(service),
            reason="service_node_port",
        )
        return bool(platform_role_for_candidate(candidate))

    def is_internal_service(self, service: Any) -> bool:
        namespace = getattr(getattr(service, "metadata", None), "namespace", None) or "-"
        name = getattr(getattr(service, "metadata", None), "name", None) or "-"
        labels = self.service_labels(service)
        if namespace == "port-audit":
            return True
        return labels.get("app") == "k8s-port-audit" or name == "k8s-port-audit"

    def service_manageability(self, service: Any) -> tuple[bool, str | None]:
        namespace = getattr(getattr(service, "metadata", None), "namespace", None)
        if not namespace_allowed(namespace, self.scanner_config):
            return False, "不在当前扫描范围"
        if self.is_managed_service(service):
            return False, "受控公开 Service"
        if self.is_internal_service(service):
            return False, "工具自身 Service"
        if self.is_system_service(service):
            return False, "K8s 系统组件"

        service_spec = getattr(service, "spec", None)
        service_type = self.current_service_type(service)
        if service_type not in SUPPORTED_SERVICE_TYPES:
            return False, f"当前类型为 {service_type}"
        if getattr(service_spec, "cluster_ip", None) == "None":
            return False, "Headless Service"
        if not getattr(service_spec, "selector", None):
            return False, "缺少 selector"
        if not self.tcp_port_defs(service):
            return False, "没有可治理的 TCP 端口"
        if self.has_non_tcp_ports(service):
            return False, "包含非 TCP 端口，暂不治理"
        if getattr(service_spec, "external_ips", None):
            return False, "带 externalIPs，暂不治理"
        return True, None

    def get_original_service(self, namespace: str, service_name: str) -> Any:
        return self.core_api.read_namespaced_service(service_name, namespace)

    def get_managed_service(self, namespace: str, service_name: str) -> Any | None:
        managed_name = self.managed_service_name(namespace, service_name)
        try:
            return self.core_api.read_namespaced_service(managed_name, namespace)
        except ApiException as exc:
            if getattr(exc, "status", None) == 404:
                return None
            raise

    def managed_port_map(self, managed_service: Any | None) -> dict[str, Any]:
        if managed_service is None:
            return {}
        return {
            self.port_key(port_def): port_def
            for port_def in getattr(getattr(managed_service, "spec", None), "ports", None) or []
        }

    def current_public_port_map(self, original_service: Any, managed_service: Any | None) -> dict[str, dict[str, Any]]:
        if managed_service is not None:
            managed_type = self.current_service_type(managed_service)
            current_map: dict[str, dict[str, Any]] = {}
            for port_def in getattr(getattr(managed_service, "spec", None), "ports", None) or []:
                current_map[self.port_key(port_def)] = {
                    "public_type": managed_type,
                    "node_port": int(getattr(port_def, "node_port", None) or 0) or None,
                    "public_port": int(getattr(port_def, "port", None) or 0) or None,
                }
            return current_map

        original_type = self.current_service_type(original_service)
        if original_type not in PUBLIC_SERVICE_TYPES:
            return {}

        current_map = {}
        for port_def in self.tcp_port_defs(original_service):
            current_map[self.port_key(port_def)] = {
                "public_type": original_type,
                "node_port": int(getattr(port_def, "node_port", None) or 0) or None,
                "public_port": int(getattr(port_def, "port", None) or 0) or None,
            }
        return current_map

    @staticmethod
    def effective_public_port(public_config: dict[str, Any] | None) -> int | None:
        if not public_config:
            return None
        if public_config.get("public_type") == "NodePort":
            return public_config.get("node_port")
        return public_config.get("public_port")

    @staticmethod
    def affected_node_ports(
        current_port_map: dict[str, dict[str, Any]],
        desired_port_map: dict[str, dict[str, Any]],
        port_key: str,
    ) -> list[int]:
        ports: set[int] = set()
        for port_map in (current_port_map, desired_port_map):
            node_port = int((port_map.get(port_key) or {}).get("node_port") or 0)
            if node_port > 0:
                ports.add(node_port)
        return sorted(ports)

    def preferred_public_type(self, original_service: Any, managed_service: Any | None) -> str:
        if managed_service is not None:
            return self.current_service_type(managed_service)
        original_type = self.current_service_type(original_service)
        if original_type in PUBLIC_SERVICE_TYPES:
            return original_type
        return self.public_service_type

    def list_controls(self) -> dict[str, Any]:
        services = self.core_api.list_service_for_all_namespaces(watch=False).items
        control_items: list[dict[str, Any]] = []
        open_port_count = 0

        for service in services:
            manageable, reason = self.service_manageability(service)
            if not manageable:
                continue

            namespace = service.metadata.namespace
            service_name = service.metadata.name
            managed_service = self.get_managed_service(namespace, service_name)
            public_port_map = self.current_public_port_map(service, managed_service)
            public_type = self.preferred_public_type(service, managed_service)
            port_items: list[dict[str, Any]] = []

            for port_def in self.tcp_port_defs(service):
                key = self.port_key(port_def)
                current_public = public_port_map.get(key)
                is_public = current_public is not None
                if is_public:
                    open_port_count += 1
                effective_public_port = self.effective_public_port(current_public)

                port_items.append(
                    {
                        "key": key,
                        "protocol": self.port_protocol(port_def),
                        "port_name": getattr(port_def, "name", None) or "",
                        "service_port": int(getattr(port_def, "port", None) or 0),
                        "target_port": (
                            str(getattr(port_def, "target_port", None))
                            if getattr(port_def, "target_port", None) is not None
                            else ""
                        ),
                        "public": is_public,
                        "public_type": current_public.get("public_type") if current_public else public_type,
                        "public_port": current_public.get("public_port") if current_public else None,
                        "node_port": current_public.get("node_port") if current_public else None,
                        "effective_public_port": effective_public_port,
                    }
                )

            control_items.append(
                {
                    "namespace": namespace,
                    "service_name": service_name,
                    "selector": dict(getattr(getattr(service, "spec", None), "selector", None) or {}),
                    "service_type": self.current_service_type(service),
                    "public_service_type": public_type,
                    "node_port_range": self.node_port_range_spec,
                    "public_service_name": self.managed_service_name(namespace, service_name),
                    "manageable": True,
                    "disabled_reason": reason,
                    "open_port_count": sum(1 for item in port_items if item["public"]),
                    "ports": sorted(port_items, key=lambda item: (not item["public"], item["service_port"], item["key"])),
                }
            )

        control_items.sort(key=lambda item: (item["namespace"], item["service_name"]))
        return {
            "enabled": self.scanner_config.service_control_enabled,
            "public_service_type": self.public_service_type,
            "node_port_range": self.node_port_range_spec,
            "service_count": len(control_items),
            "open_port_count": open_port_count,
            "items": control_items,
            "mode_note": "按端口治理业务 Service。对已有 NodePort / LoadBalancer，会先收回原始 Service，再保留选中的外部端口。",
        }

    def build_original_clusterip_patch(self, original_service: Any) -> dict[str, Any]:
        ports: list[dict[str, Any]] = []
        for port_def in getattr(getattr(original_service, "spec", None), "ports", None) or []:
            port_body: dict[str, Any] = {
                "port": int(getattr(port_def, "port", None) or 0),
                "protocol": self.port_protocol(port_def),
                "targetPort": (
                    getattr(port_def, "target_port", None)
                    if getattr(port_def, "target_port", None) is not None
                    else int(getattr(port_def, "port", None) or 0)
                ),
            }
            name = getattr(port_def, "name", None)
            if name:
                port_body["name"] = name
            app_protocol = getattr(port_def, "app_protocol", None)
            if app_protocol:
                port_body["appProtocol"] = app_protocol
            ports.append(port_body)

        return {
            "spec": {
                "type": "ClusterIP",
                "ports": ports,
            }
        }

    def build_managed_service_body(
        self,
        original_service: Any,
        selected_port_config: dict[str, dict[str, Any]],
        public_type: str,
    ) -> dict[str, Any]:
        namespace = original_service.metadata.namespace
        service_name = original_service.metadata.name
        managed_name = self.managed_service_name(namespace, service_name)
        selector = dict(getattr(getattr(original_service, "spec", None), "selector", None) or {})
        original_labels = self.service_labels(original_service)
        original_annotations = self.service_annotations(original_service)
        ports: list[dict[str, Any]] = []

        for port_def in self.tcp_port_defs(original_service):
            key = self.port_key(port_def)
            config = selected_port_config.get(key)
            if not config:
                continue

            port_body: dict[str, Any] = {
                "name": self.managed_port_name(port_def),
                "protocol": self.port_protocol(port_def),
                "targetPort": (
                    getattr(port_def, "target_port", None)
                    if getattr(port_def, "target_port", None) is not None
                    else int(getattr(port_def, "port", None) or 0)
                ),
            }

            if public_type == "LoadBalancer":
                port_body["port"] = int(config.get("public_port") or getattr(port_def, "port", None) or 0)
            else:
                port_body["port"] = int(getattr(port_def, "port", None) or 0)
                if config.get("node_port"):
                    port_body["nodePort"] = int(config["node_port"])

            app_protocol = getattr(port_def, "app_protocol", None)
            if app_protocol:
                port_body["appProtocol"] = app_protocol
            ports.append(port_body)

        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": managed_name,
                "namespace": namespace,
                "labels": {
                    **original_labels,
                    MANAGED_LABEL: MANAGED_BY_VALUE,
                    "app.kubernetes.io/managed-by": "k8s-port-audit",
                    "k8s-port-audit.io/source-service": service_name,
                },
                "annotations": {
                    **original_annotations,
                    OWNER_NAMESPACE_ANNOTATION: namespace,
                    OWNER_SERVICE_ANNOTATION: service_name,
                    PUBLIC_TYPE_ANNOTATION: public_type,
                },
            },
            "spec": {
                "type": public_type,
                "selector": selector,
                "ports": ports,
            },
        }

    def desired_public_port_map(
        self,
        original_service: Any,
        managed_service: Any | None,
        port_key: str,
        expose: bool,
        public_port: int | None,
    ) -> tuple[dict[str, dict[str, Any]], str]:
        current_map = self.current_public_port_map(original_service, managed_service)
        public_type = self.preferred_public_type(original_service, managed_service)
        desired_map = {key: dict(value) for key, value in current_map.items()}

        original_port_map = {self.port_key(port_def): port_def for port_def in self.tcp_port_defs(original_service)}
        if port_key not in original_port_map:
            raise ServiceControlError(f"未找到端口: {port_key}")

        if not expose:
            desired_map.pop(port_key, None)
            return desired_map, public_type

        original_port_def = original_port_map[port_key]
        entry = desired_map.get(port_key, {"public_type": public_type})
        entry["public_type"] = public_type
        if public_type == "NodePort":
            entry["public_port"] = int(getattr(original_port_def, "port", None) or 0)
            if public_port is not None:
                entry["node_port"] = public_port
            else:
                entry["node_port"] = entry.get("node_port")
        else:
            entry["public_port"] = (
                public_port
                if public_port is not None
                else entry.get("public_port") or int(getattr(original_port_def, "port", None) or 0)
            )
            entry["node_port"] = None
        desired_map[port_key] = entry
        return desired_map, public_type

    def reconcile_exposure(
        self,
        original_service: Any,
        managed_service: Any | None,
        desired_port_map: dict[str, dict[str, Any]],
        public_type: str,
    ) -> None:
        namespace = original_service.metadata.namespace
        service_name = original_service.metadata.name
        original_type = self.current_service_type(original_service)

        if original_type != "ClusterIP":
            self.core_api.patch_namespaced_service(
                service_name,
                namespace,
                self.build_original_clusterip_patch(original_service),
            )

        if not desired_port_map:
            if managed_service is not None:
                self.core_api.delete_namespaced_service(managed_service.metadata.name, namespace)
            return

        body = self.build_managed_service_body(original_service, desired_port_map, public_type)
        if managed_service is None:
            self.core_api.create_namespaced_service(namespace, body)
        else:
            self.core_api.patch_namespaced_service(managed_service.metadata.name, namespace, body)

    def set_port_exposure(
        self,
        namespace: str,
        service_name: str,
        port_key: str,
        expose: bool,
        public_port: int | None = None,
    ) -> dict[str, Any]:
        original_service = self.get_original_service(namespace, service_name)
        manageable, reason = self.service_manageability(original_service)
        if not manageable:
            raise ServiceControlError(reason or "当前 Service 不可治理")

        managed_service = self.get_managed_service(namespace, service_name)
        public_type = self.preferred_public_type(original_service, managed_service)
        current_port_map = self.current_public_port_map(original_service, managed_service)
        normalized_public_port = self.normalize_public_port(public_port, public_type)
        desired_port_map, public_type = self.desired_public_port_map(
            original_service,
            managed_service,
            port_key,
            expose,
            normalized_public_port,
        )
        affected_node_ports = self.affected_node_ports(current_port_map, desired_port_map, port_key)
        self.reconcile_exposure(original_service, managed_service, desired_port_map, public_type)

        return {
            "namespace": namespace,
            "service_name": service_name,
            "port_key": port_key,
            "action": "opened" if expose else "closed",
            "managed_service_name": self.managed_service_name(namespace, service_name),
            "public_service_type": public_type,
            "public_port": normalized_public_port,
            "affected_node_ports": affected_node_ports,
        }
