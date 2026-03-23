from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..runtime.dependencies import ensure_dependencies, yaml


def parse_port_spec(port_spec: str) -> list[int]:
    ports: set[int] = set()

    for item in port_spec.split(","):
        part = item.strip()
        if not part:
            continue

        if "-" in part:
            start_text, end_text = part.split("-", 1)
            if not start_text.isdigit() or not end_text.isdigit():
                raise ValueError(f"端口范围必须是数字，例如 80-100: {part}")

            start_port = int(start_text)
            end_port = int(end_text)
            if start_port < 1 or end_port > 65535 or start_port > end_port:
                raise ValueError(f"端口范围无效，合法范围是 1-65535，且 start <= end: {part}")

            ports.update(range(start_port, end_port + 1))
        else:
            if not part.isdigit():
                raise ValueError(f"端口必须是数字，例如 80 或 443: {part}")

            port = int(part)
            if port < 1 or port > 65535:
                raise ValueError(f"端口必须在 1-65535 之间: {part}")
            ports.add(port)

    return sorted(ports)


def coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError(f"无法解析字符串列表: {value!r}")


def coerce_port_spec(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    raise ValueError(f"无法解析端口配置: {value!r}")


def namespace_allowed(namespace: str | None, scanner_config: "ScannerConfig") -> bool:
    if not namespace:
        return True

    include = set(scanner_config.include_namespaces)
    exclude = set(scanner_config.exclude_namespaces)

    if include and namespace not in include:
        return False
    if namespace in exclude:
        return False
    return True


@dataclass
class ScannerConfig:
    timeout_seconds: float = 0.5
    concurrency: int = 300
    interval_seconds: int = 0
    watch_kubernetes_events: bool = True
    event_watch_timeout_seconds: int = 45
    event_debounce_seconds: float = 2.0
    output_path: str | None = None
    pretty_json: bool = True
    include_namespaces: list[str] = field(default_factory=list)
    exclude_namespaces: list[str] = field(default_factory=lambda: ["kube-public"])
    scan_service_external_ips: bool = True
    scan_node_ports: bool = True
    scan_host_ports: bool = True
    scan_host_network_ports: bool = True
    full_node_tcp_scan: bool = True
    full_node_tcp_port_spec: str = "1-65535"
    full_node_tcp_ports: list[int] = field(default_factory=list, repr=False)
    traffic_observation_enabled: bool = True
    traffic_observation_host_proc_root: str = "/host-proc"
    web_enabled: bool = True
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    web_refresh_seconds: int = 15

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScannerConfig":
        scan = payload.get("scan", {})
        scope = payload.get("scope", {})
        discovery = payload.get("discovery", {})
        ports = payload.get("ports", {})
        traffic_observation = payload.get("traffic_observation", {})
        report = payload.get("report", {})
        web = payload.get("web", {})

        config_obj = cls(
            timeout_seconds=float(scan.get("timeout_seconds", 0.5)),
            concurrency=int(scan.get("concurrency", 300)),
            interval_seconds=int(scan.get("interval_seconds", 0)),
            watch_kubernetes_events=bool(scan.get("watch_kubernetes_events", True)),
            event_watch_timeout_seconds=int(scan.get("event_watch_timeout_seconds", 45)),
            event_debounce_seconds=float(scan.get("event_debounce_seconds", 2.0)),
            output_path=scan.get("output_path"),
            pretty_json=bool(report.get("pretty_json", True)),
            include_namespaces=coerce_str_list(scope.get("include_namespaces")),
            exclude_namespaces=coerce_str_list(scope.get("exclude_namespaces", ["kube-public"])),
            scan_service_external_ips=bool(discovery.get("service_external_ips", True)),
            scan_node_ports=bool(discovery.get("node_ports", True)),
            scan_host_ports=bool(discovery.get("host_ports", True)),
            scan_host_network_ports=bool(discovery.get("host_network_ports", True)),
            full_node_tcp_scan=bool(discovery.get("full_node_tcp_scan", True)),
            full_node_tcp_port_spec=coerce_port_spec(ports.get("full_node_tcp_ports", "1-65535")),
            full_node_tcp_ports=parse_port_spec(
                coerce_port_spec(ports.get("full_node_tcp_ports", "1-65535"))
            ),
            traffic_observation_enabled=bool(traffic_observation.get("enabled", True)),
            traffic_observation_host_proc_root=str(
                traffic_observation.get("host_proc_root", "/host-proc")
            ),
            web_enabled=bool(web.get("enabled", True)),
            web_host=str(web.get("host", "0.0.0.0")),
            web_port=int(web.get("port", 8080)),
            web_refresh_seconds=int(web.get("refresh_seconds", 15)),
        )
        config_obj.validate()
        return config_obj

    def validate(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("scan.timeout_seconds 必须大于 0")
        if self.concurrency < 1:
            raise ValueError("scan.concurrency 必须大于 0")
        if self.interval_seconds < 0:
            raise ValueError("scan.interval_seconds 不能小于 0")
        if self.event_watch_timeout_seconds < 10:
            raise ValueError("scan.event_watch_timeout_seconds 不能小于 10")
        if self.event_debounce_seconds < 0:
            raise ValueError("scan.event_debounce_seconds 不能小于 0")
        if self.full_node_tcp_scan and not self.full_node_tcp_ports:
            raise ValueError("ports.full_node_tcp_ports 不能为空")
        if self.traffic_observation_enabled and not self.traffic_observation_host_proc_root.strip():
            raise ValueError("traffic_observation.host_proc_root 不能为空")
        if not 1 <= self.web_port <= 65535:
            raise ValueError("web.port 必须在 1-65535 之间")
        if self.web_refresh_seconds < 5:
            raise ValueError("web.refresh_seconds 不能小于 5")

    def to_report_dict(self) -> dict[str, Any]:
        payload = {
            "timeout_seconds": self.timeout_seconds,
            "concurrency": self.concurrency,
            "interval_seconds": self.interval_seconds,
            "watch_kubernetes_events": self.watch_kubernetes_events,
            "event_watch_timeout_seconds": self.event_watch_timeout_seconds,
            "event_debounce_seconds": self.event_debounce_seconds,
            "output_path": self.output_path,
            "pretty_json": self.pretty_json,
            "include_namespaces": list(self.include_namespaces),
            "exclude_namespaces": list(self.exclude_namespaces),
            "scan_service_external_ips": self.scan_service_external_ips,
            "scan_node_ports": self.scan_node_ports,
            "scan_host_ports": self.scan_host_ports,
            "scan_host_network_ports": self.scan_host_network_ports,
            "full_node_tcp_scan": self.full_node_tcp_scan,
            "full_node_tcp_port_spec": self.full_node_tcp_port_spec,
            "full_node_tcp_port_count": len(self.full_node_tcp_ports),
            "traffic_observation_enabled": self.traffic_observation_enabled,
            "traffic_observation_host_proc_root": self.traffic_observation_host_proc_root,
            "web_enabled": self.web_enabled,
            "web_host": self.web_host,
            "web_port": self.web_port,
            "web_refresh_seconds": self.web_refresh_seconds,
        }
        if self.output_path:
            payload["output_path"] = self.output_path
        return payload


def load_scanner_config(config_path: Path) -> ScannerConfig:
    ensure_dependencies()
    if yaml is None:
        raise RuntimeError("PyYAML 不可用")

    if not config_path.exists():
        raise FileNotFoundError(f"找不到配置文件: {config_path}")

    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_config, dict):
        raise ValueError("配置文件根节点必须是 YAML 对象")

    return ScannerConfig.from_dict(raw_config)
