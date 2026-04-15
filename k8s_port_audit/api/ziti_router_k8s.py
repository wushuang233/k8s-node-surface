from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from ..runtime.dependencies import ApiException, client, yaml

DEFAULT_ZITI_NAMESPACE = "openziti"
DEFAULT_ROUTER_IMAGE = "docker.io/openziti/ziti-router:1.7.2"
DEFAULT_ROUTER_IMAGE_PULL_POLICY = "IfNotPresent"
DEFAULT_ROUTER_STORAGE_CLASS = "local-path"
DEFAULT_ROUTER_STORAGE_SIZE = "50Mi"
DEFAULT_ROUTER_EDGE_LISTENER_PORT = 3022
DEFAULT_ROUTER_SERVICE_PORT = 30222
DEFAULT_ROUTER_FS_GROUP = 2171


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sanitize_k8s_name(value: str, prefix: str = "ziti-router") -> str:
    raw = re.sub(r"[^a-z0-9-]+", "-", str(value or "").strip().lower()).strip("-")
    if not raw:
        raw = prefix
    if raw[0].isdigit():
        raw = f"{prefix}-{raw}"
    if len(raw) <= 63:
        return raw
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"{raw[:54].rstrip('-')}-{digest}"


def parse_int(value: Any, default: int | None = None) -> int | None:
    if value in {None, ""}:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_controller_endpoint(controller_url: str) -> str:
    parsed = urlsplit(str(controller_url or "").strip())
    host = (parsed.hostname or "").strip()
    if not host:
        raise ValueError("controller URL 缺少 host")
    if parsed.port:
        port = parsed.port
    elif parsed.scheme == "https":
        port = 443
    else:
        port = 80
    return f"tls:{host}:{port}"


def detect_node_internal_ip(core_api: Any) -> str:
    if client is None:
        return ""
    try:
        nodes = core_api.list_node().items
    except Exception:
        return ""

    for node in nodes:
        for address in getattr(getattr(node, "status", None), "addresses", None) or []:
            if getattr(address, "type", "") == "InternalIP" and getattr(address, "address", ""):
                return str(address.address).strip()
    return ""


def read_container_env(deployment: Any, env_name: str) -> str:
    containers = getattr(getattr(getattr(deployment, "spec", None), "template", None), "spec", None)
    for container in getattr(containers, "containers", None) or []:
        for env_item in getattr(container, "env", None) or []:
            if getattr(env_item, "name", "") == env_name and getattr(env_item, "value", None):
                return str(env_item.value).strip()
    return ""


def read_secret_name_from_env(deployment: Any, env_name: str) -> str:
    containers = getattr(getattr(getattr(deployment, "spec", None), "template", None), "spec", None)
    for container in getattr(containers, "containers", None) or []:
        for env_item in getattr(container, "env", None) or []:
            if getattr(env_item, "name", "") != env_name:
                continue
            value_from = getattr(env_item, "value_from", None) or getattr(env_item, "valueFrom", None)
            secret_ref = getattr(value_from, "secret_key_ref", None) or getattr(value_from, "secretKeyRef", None)
            name = getattr(secret_ref, "name", None)
            if name:
                return str(name).strip()
    return ""


def read_volume_resource_names(deployment: Any) -> dict[str, str]:
    names = {"configMapName": "", "pvcName": ""}
    template_spec = getattr(getattr(getattr(deployment, "spec", None), "template", None), "spec", None)
    for volume in getattr(template_spec, "volumes", None) or []:
        config_map = getattr(volume, "config_map", None) or getattr(volume, "configMap", None)
        claim = getattr(volume, "persistent_volume_claim", None) or getattr(volume, "persistentVolumeClaim", None)
        if config_map and getattr(config_map, "name", None):
            names["configMapName"] = str(config_map.name).strip()
        if claim and getattr(claim, "claim_name", None):
            names["pvcName"] = str(claim.claim_name).strip()
    return names


def read_service_for_selector(core_api: Any, namespace: str, selector: dict[str, str]) -> Any | None:
    if not selector:
        return None
    try:
        services = core_api.list_namespaced_service(namespace).items
    except Exception:
        return None

    selector_items = {str(key): str(value) for key, value in selector.items()}
    for service in services:
        service_selector = getattr(getattr(service, "spec", None), "selector", None) or {}
        normalized = {str(key): str(value) for key, value in service_selector.items()}
        if normalized == selector_items:
            return service
    return None


def list_cluster_services(core_api: Any) -> list[Any]:
    try:
        return list(getattr(core_api.list_service_for_all_namespaces(), "items", None) or [])
    except Exception:
        return []


def find_node_port_conflict(
    core_api: Any,
    node_port: int,
    *,
    exclude_namespace: str = "",
    exclude_service_name: str = "",
) -> dict[str, str] | None:
    if node_port <= 0:
        return None

    normalized_namespace = str(exclude_namespace or "").strip()
    normalized_service_name = str(exclude_service_name or "").strip()

    for service in list_cluster_services(core_api):
        metadata = getattr(service, "metadata", None)
        spec = getattr(service, "spec", None)
        service_name = str(getattr(metadata, "name", "") or "").strip()
        service_namespace = str(getattr(metadata, "namespace", "") or "").strip()

        if (
            normalized_namespace
            and normalized_service_name
            and service_namespace == normalized_namespace
            and service_name == normalized_service_name
        ):
            continue

        for port in getattr(spec, "ports", None) or []:
            allocated = int(getattr(port, "node_port", None) or getattr(port, "nodePort", None) or 0)
            if allocated != node_port:
                continue
            return {
                "namespace": service_namespace,
                "serviceName": service_name,
                "serviceType": str(getattr(spec, "type", "") or "").strip(),
            }

    return None


def parse_router_advertise(config_map: Any) -> tuple[str, int | None]:
    data = getattr(config_map, "data", None) or {}
    config_text = str(data.get("ziti-router.yaml") or "")
    match = re.search(r"advertise:\s*([^\s:]+):(\d+)", config_text)
    if not match:
        return "", None
    return match.group(1).strip(), parse_int(match.group(2))


def read_router_config_text(config_map: Any | None) -> str:
    data = getattr(config_map, "data", None) or {}
    return str(data.get("ziti-router.yaml") or "")


def parse_router_tunnel_mode(config_map: Any | None = None, config_text: str | None = None) -> str:
    text = config_text if config_text is not None else read_router_config_text(config_map)
    if not text.strip():
        return ""

    if yaml is not None:
        try:
            parsed = yaml.safe_load(text) or {}
            listeners = parsed.get("listeners") or []
            for listener in listeners if isinstance(listeners, list) else []:
                if not isinstance(listener, dict):
                    continue
                if str(listener.get("binding") or "").strip() != "tunnel":
                    continue
                options = listener.get("options") or {}
                mode = str(options.get("mode") or "").strip()
                return mode or "enabled"
        except Exception:
            pass

    match = re.search(r"binding:\s*tunnel(?:.|\n)*?mode:\s*([^\s]+)", text)
    if match:
        return str(match.group(1) or "").strip()
    if "binding: tunnel" in text:
        return "enabled"
    return ""


def ensure_router_config_tunnel_mode(config_text: str, tunnel_mode: str) -> str:
    if yaml is None:
        raise RuntimeError("PyYAML 不可用，无法修改 router tunnel 配置")

    parsed = yaml.safe_load(config_text) or {}
    if not isinstance(parsed, dict):
        raise ValueError("router 配置格式异常")

    listeners = parsed.get("listeners")
    if not isinstance(listeners, list):
        listeners = []

    updated_listeners = []
    for listener in listeners:
        if not isinstance(listener, dict):
            continue
        if str(listener.get("binding") or "").strip() == "tunnel":
            continue
        updated_listeners.append(listener)

    normalized_mode = str(tunnel_mode or "").strip().lower()
    if normalized_mode and normalized_mode != "none":
        updated_listeners.append(
            {
                "binding": "tunnel",
                "options": {
                    "mode": normalized_mode,
                },
            }
        )

    parsed["listeners"] = updated_listeners
    return yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True)


def build_workload_info(deployment: Any, service: Any | None = None, config_map: Any | None = None) -> dict[str, Any]:
    metadata = getattr(deployment, "metadata", None)
    spec = getattr(deployment, "spec", None)
    status = getattr(deployment, "status", None)
    labels = getattr(metadata, "labels", None) or {}
    selector = getattr(spec, "selector", None)
    selector_labels = getattr(selector, "match_labels", None) or getattr(selector, "matchLabels", None) or {}
    volumes = read_volume_resource_names(deployment)
    service_spec = getattr(service, "spec", None) if service is not None else None
    ports = getattr(service_spec, "ports", None) or []
    first_port = ports[0] if ports else None
    public_host, advertise_port = parse_router_advertise(config_map) if config_map is not None else ("", None)
    tunnel_mode = parse_router_tunnel_mode(config_map)

    return {
        "deploymentName": str(getattr(metadata, "name", "") or ""),
        "routerId": str(labels.get("openziti.io/edge-router-id") or ""),
        "routerName": str(labels.get("openziti.io/edge-router-name") or read_container_env(deployment, "ZITI_ROUTER_NAME") or ""),
        "managedBy": str(labels.get("openziti.io/managed-by") or labels.get("app.kubernetes.io/managed-by") or ""),
        "selector": selector_labels,
        "readyReplicas": int(getattr(status, "ready_replicas", None) or getattr(status, "readyReplicas", None) or 0),
        "replicas": int(getattr(spec, "replicas", None) or 0),
        "available": int(getattr(status, "ready_replicas", None) or getattr(status, "readyReplicas", None) or 0) > 0,
        "serviceName": str(getattr(getattr(service, "metadata", None), "name", "") or ""),
        "nodePort": int(getattr(first_port, "node_port", None) or getattr(first_port, "nodePort", None) or 0),
        "servicePort": int(getattr(first_port, "port", None) or 0),
        "targetPort": str(getattr(first_port, "target_port", None) or getattr(first_port, "targetPort", None) or ""),
        "configMapName": volumes["configMapName"],
        "pvcName": volumes["pvcName"],
        "secretName": read_secret_name_from_env(deployment, "ZITI_ENROLL_TOKEN"),
        "publicHost": public_host,
        "advertisedPort": advertise_port or int(getattr(first_port, "node_port", None) or getattr(first_port, "nodePort", None) or 0),
        "tunnelEnabled": bool(tunnel_mode),
        "tunnelMode": tunnel_mode or "none",
        "createdAt": str(getattr(metadata, "creation_timestamp", None) or getattr(metadata, "creationTimestamp", None) or ""),
    }


def list_router_workloads(namespace: str = DEFAULT_ZITI_NAMESPACE) -> list[dict[str, Any]]:
    if client is None:
        return []

    apps_api = client.AppsV1Api()
    core_api = client.CoreV1Api()
    try:
        deployments = apps_api.list_namespaced_deployment(namespace).items
    except Exception:
        return []

    items: list[dict[str, Any]] = []
    for deployment in deployments:
        labels = getattr(getattr(deployment, "metadata", None), "labels", None) or {}
        if str(labels.get("app.kubernetes.io/name") or "") != "ziti-router":
            continue
        selector = getattr(getattr(getattr(deployment, "spec", None), "selector", None), "match_labels", None) or {}
        service = read_service_for_selector(core_api, namespace, selector)
        config_map_name = read_volume_resource_names(deployment).get("configMapName") or ""
        config_map = None
        if config_map_name:
            try:
                config_map = core_api.read_namespaced_config_map(config_map_name, namespace)
            except Exception:
                config_map = None
        items.append(build_workload_info(deployment, service, config_map))

    items.sort(key=lambda item: (item.get("routerName", ""), item.get("deploymentName", "")))
    return items


def find_router_workload(namespace: str, router_id: str, router_name: str) -> dict[str, Any] | None:
    normalized_id = str(router_id or "").strip()
    normalized_name = str(router_name or "").strip()
    for item in list_router_workloads(namespace):
        if normalized_id and str(item.get("routerId") or "").strip() == normalized_id:
            return item
        if normalized_name and str(item.get("routerName") or "").strip() == normalized_name:
            return item
    return None


def build_router_config_yaml(
    controller_url: str,
    public_host: str,
    advertised_port: int,
    tunnel_mode: str = "none",
) -> str:
    controller_endpoint = parse_controller_endpoint(controller_url)
    tunnel_listener = ""
    normalized_mode = str(tunnel_mode or "").strip().lower()
    if normalized_mode and normalized_mode != "none":
        tunnel_listener = f"""\
  - binding: tunnel
    options:
        mode: {normalized_mode}
"""
    return f"""\
v: 3

identity:
  cert:        /etc/ziti/config/ziti-router.cert
  server_cert: /etc/ziti/config/ziti-router.server.chain.cert
  key:         /etc/ziti/config/ziti-router.key
  ca:          /etc/ziti/config/ziti-router.cas

ctrl:
  endpointsFile: endpoints.yml
  endpoint:    {controller_endpoint}

link:
  dialers:
    - binding: transport

listeners:
  - binding: edge
    address: tls:0.0.0.0:{DEFAULT_ROUTER_EDGE_LISTENER_PORT}
    options:
      advertise: {public_host}:{advertised_port}
{tunnel_listener}

edge:
  csr:
    sans:
      dns:
        - "localhost"
      ip:
        - "127.0.0.1"
        - "{public_host}"
  heartbeatIntervalSeconds: 60

forwarder:
    latencyProbeInterval: 10
    linkDialQueueLength: 1000
    linkDialWorkerCount: 32
    rateLimitedQueueLength: 5000
    rateLimitedWorkerCount: 64
    xgressDialQueueLength: 1000
    xgressDialWorkerCount: 128
"""


def read_namespaced_resource(read_fn: Any, name: str, namespace: str) -> Any | None:
    try:
        return read_fn(name, namespace)
    except ApiException as exc:
        if getattr(exc, "status", None) == 404:
            return None
        raise


def create_or_patch_core_resource(
    read_fn: Any,
    create_fn: Any,
    patch_fn: Any,
    name: str,
    namespace: str,
    body: dict[str, Any],
) -> Any:
    existing = read_namespaced_resource(read_fn, name, namespace)
    if existing is None:
        return create_fn(namespace, body)
    return patch_fn(name, namespace, body)


def create_or_patch_deployment(namespace: str, body: dict[str, Any]) -> Any:
    if client is None:
        raise RuntimeError("kubernetes client 不可用")
    apps_api = client.AppsV1Api()
    metadata = body.get("metadata", {})
    name = str(metadata.get("name") or "").strip()
    if not name:
        raise ValueError("deployment name 不能为空")
    existing = read_namespaced_resource(apps_api.read_namespaced_deployment, name, namespace)
    if existing is None:
        return apps_api.create_namespaced_deployment(namespace, body)
    return apps_api.patch_namespaced_deployment(name, namespace, body)


def ensure_router_workload(
    *,
    namespace: str,
    router: dict[str, Any],
    controller_url: str,
    enrollment_jwt: str,
    public_host: str = "",
    requested_node_port: int | None = None,
    storage_class_name: str = DEFAULT_ROUTER_STORAGE_CLASS,
    storage_size: str = DEFAULT_ROUTER_STORAGE_SIZE,
    image: str = DEFAULT_ROUTER_IMAGE,
    image_pull_policy: str = DEFAULT_ROUTER_IMAGE_PULL_POLICY,
) -> dict[str, Any]:
    if client is None:
        raise RuntimeError("kubernetes client 不可用")

    router_id = str(router.get("id") or "").strip()
    router_name = str(router.get("name") or "").strip()
    if not router_id or not router_name:
        raise ValueError("router 缺少 id 或 name")

    apps_api = client.AppsV1Api()
    core_api = client.CoreV1Api()
    current_workload = find_router_workload(namespace, router_id, router_name)
    workload_name = current_workload["deploymentName"] if current_workload else sanitize_k8s_name(router_name)
    selector_labels = current_workload.get("selector") if current_workload else None
    if not selector_labels:
        selector_labels = {
            "app.kubernetes.io/name": "ziti-router",
            "app.kubernetes.io/component": "ziti-router",
            "app.kubernetes.io/instance": workload_name,
        }
    labels = {
        **selector_labels,
        "app.kubernetes.io/name": "ziti-router",
        "app.kubernetes.io/component": "ziti-router",
        "app.kubernetes.io/instance": workload_name,
        "openziti.io/managed-by": "k8s-port-audit",
        "openziti.io/edge-router-id": router_id,
        "openziti.io/edge-router-name": router_name,
    }
    effective_public_host = public_host or current_workload.get("publicHost") if current_workload else ""
    if not effective_public_host:
        effective_public_host = detect_node_internal_ip(core_api)
    if not effective_public_host:
        raise ValueError("无法自动识别宿主机 InternalIP，请稍后再试")

    annotations = {
        "openziti.io/public-host": effective_public_host,
        "openziti.io/updated-at": utc_timestamp(),
    }

    service_name = current_workload.get("serviceName") if current_workload else ""
    if not service_name:
        service_name = f"{workload_name}-edge"
    config_map_name = current_workload.get("configMapName") if current_workload else ""
    if not config_map_name:
        config_map_name = f"{workload_name}-config"
    secret_name = current_workload.get("secretName") if current_workload else ""
    if not secret_name:
        secret_name = f"{workload_name}-enrollment"
    pvc_name = current_workload.get("pvcName") if current_workload else ""
    if not pvc_name:
        pvc_name = workload_name

    effective_node_port = requested_node_port or parse_int(current_workload.get("nodePort") if current_workload else None)
    if effective_node_port is not None and not 30000 <= effective_node_port <= 32767:
        raise ValueError("NodePort 必须在 30000-32767 之间")
    if effective_node_port:
        node_port_conflict = find_node_port_conflict(
            core_api,
            effective_node_port,
            exclude_namespace=namespace,
            exclude_service_name=service_name,
        )
        if node_port_conflict is not None:
            raise ValueError(
                "NodePort "
                f"{effective_node_port} 已被 "
                f"{node_port_conflict['namespace']}/{node_port_conflict['serviceName']} "
                f"({node_port_conflict['serviceType'] or 'Service'}) 占用，请换一个端口再部署"
            )

    create_or_patch_core_resource(
        core_api.read_namespaced_secret,
        core_api.create_namespaced_secret,
        core_api.patch_namespaced_secret,
        secret_name,
        namespace,
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": secret_name, "namespace": namespace, "labels": labels, "annotations": annotations},
            "type": "Opaque",
            "stringData": {"enrollmentJwt": enrollment_jwt},
        },
    )

    if read_namespaced_resource(core_api.read_namespaced_persistent_volume_claim, pvc_name, namespace) is None:
        core_api.create_namespaced_persistent_volume_claim(
            namespace,
            {
                "apiVersion": "v1",
                "kind": "PersistentVolumeClaim",
                "metadata": {"name": pvc_name, "namespace": namespace, "labels": labels, "annotations": annotations},
                "spec": {
                    "accessModes": ["ReadWriteOnce"],
                    "resources": {"requests": {"storage": storage_size or DEFAULT_ROUTER_STORAGE_SIZE}},
                    "storageClassName": storage_class_name or DEFAULT_ROUTER_STORAGE_CLASS,
                },
            },
        )

    current_service_port = parse_int(current_workload.get("servicePort") if current_workload else None)
    service_port = current_service_port or DEFAULT_ROUTER_SERVICE_PORT
    service_body = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": service_name, "namespace": namespace, "labels": labels, "annotations": annotations},
        "spec": {
            "type": "NodePort",
            "selector": selector_labels,
            "ports": [
                {
                    "name": "edge",
                    "protocol": "TCP",
                    "port": service_port,
                    "targetPort": DEFAULT_ROUTER_EDGE_LISTENER_PORT,
                }
            ],
        },
    }
    if effective_node_port:
        service_body["spec"]["ports"][0]["nodePort"] = effective_node_port
    create_or_patch_core_resource(
        core_api.read_namespaced_service,
        core_api.create_namespaced_service,
        core_api.patch_namespaced_service,
        service_name,
        namespace,
        service_body,
    )
    service = core_api.read_namespaced_service(service_name, namespace)
    actual_node_port = int(
        getattr(getattr(service.spec, "ports", None)[0], "node_port", None)
        or getattr(getattr(service.spec, "ports", None)[0], "nodePort", None)
        or 0
    )
    if actual_node_port <= 0:
        raise ValueError("router Service 没有拿到可用的 NodePort")

    tunnel_mode = "host" if bool(router.get("isTunnelerEnabled")) else "none"
    config_yaml = build_router_config_yaml(
        controller_url,
        effective_public_host,
        actual_node_port,
        tunnel_mode=tunnel_mode,
    )
    create_or_patch_core_resource(
        core_api.read_namespaced_config_map,
        core_api.create_namespaced_config_map,
        core_api.patch_namespaced_config_map,
        config_map_name,
        namespace,
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": config_map_name, "namespace": namespace, "labels": labels, "annotations": annotations},
            "data": {"ziti-router.yaml": config_yaml},
        },
    )

    deployment_body = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": workload_name, "namespace": namespace, "labels": labels, "annotations": annotations},
        "spec": {
            "replicas": 1,
            "strategy": {"type": "Recreate"},
            "selector": {"matchLabels": selector_labels},
            "template": {
                "metadata": {
                    "labels": labels,
                    "annotations": {
                        "openziti.io/public-host": effective_public_host,
                        "openziti.io/restarted-at": utc_timestamp(),
                    },
                },
                "spec": {
                    "securityContext": {"fsGroup": DEFAULT_ROUTER_FS_GROUP},
                    "containers": [
                        {
                            "name": "ziti-router",
                            "image": image or DEFAULT_ROUTER_IMAGE,
                            "imagePullPolicy": image_pull_policy or DEFAULT_ROUTER_IMAGE_PULL_POLICY,
                            "command": ["/entrypoint.bash"],
                            "args": ["run", "/etc/ziti/config/ziti-router.yaml"],
                            "env": [
                                {
                                    "name": "ZITI_ENROLL_TOKEN",
                                    "valueFrom": {"secretKeyRef": {"name": secret_name, "key": "enrollmentJwt"}},
                                },
                                {"name": "ZITI_BOOTSTRAP", "value": "true"},
                                {"name": "ZITI_BOOTSTRAP_ENROLLMENT", "value": "true"},
                                {"name": "ZITI_BOOTSTRAP_CONFIG", "value": "false"},
                                {"name": "ZITI_AUTO_RENEW_CERTS", "value": "true"},
                                {"name": "ZITI_HOME", "value": "/etc/ziti/config"},
                                {"name": "ZITI_ROUTER_NAME", "value": router_name},
                                # The generated router config always stores identity files as
                                # ziti-router.cert/key/server.chain.cert. If we let the
                                # bootstrap script derive the cert basename from ZITI_ROUTER_NAME,
                                # custom router names will look for <router-name>.cert on every
                                # restart and incorrectly attempt re-enrollment once the original
                                # JWT expires.
                                {"name": "ZITI_ROUTER_IDENTITY_CERT", "value": "ziti-router.cert"},
                            ],
                            "livenessProbe": {
                                "exec": {"command": ["/bin/sh", "-c", "ziti agent stats"]},
                                "failureThreshold": 5,
                                "initialDelaySeconds": 10,
                                "periodSeconds": 10,
                                "successThreshold": 1,
                                "timeoutSeconds": 5,
                            },
                            "readinessProbe": {
                                "exec": {"command": ["/bin/sh", "-c", "ziti agent stats"]},
                                "failureThreshold": 5,
                                "initialDelaySeconds": 10,
                                "periodSeconds": 10,
                                "successThreshold": 1,
                                "timeoutSeconds": 5,
                            },
                            "volumeMounts": [
                                {"name": "config-data", "mountPath": "/etc/ziti/config"},
                                {"name": "ziti-router-config", "mountPath": "/etc/ziti/config/ziti-router.yaml", "subPath": "ziti-router.yaml"},
                            ],
                        }
                    ],
                    "volumes": [
                        {"name": "ziti-router-config", "configMap": {"name": config_map_name, "defaultMode": 292}},
                        {"name": "config-data", "persistentVolumeClaim": {"claimName": pvc_name}},
                    ],
                },
            },
        },
    }
    create_or_patch_deployment(namespace, deployment_body)
    deployment = apps_api.read_namespaced_deployment(workload_name, namespace)
    config_map = core_api.read_namespaced_config_map(config_map_name, namespace)
    return build_workload_info(deployment, service, config_map)


def ensure_router_tunnel_mode(
    namespace: str,
    router_id: str,
    router_name: str,
    *,
    enabled: bool,
) -> dict[str, Any] | None:
    if client is None:
        raise RuntimeError("kubernetes client 不可用")

    current_workload = find_router_workload(namespace, router_id, router_name)
    if current_workload is None:
        return None

    config_map_name = str(current_workload.get("configMapName") or "").strip()
    deployment_name = str(current_workload.get("deploymentName") or "").strip()
    service_name = str(current_workload.get("serviceName") or "").strip()
    if not config_map_name or not deployment_name:
        return current_workload

    apps_api = client.AppsV1Api()
    core_api = client.CoreV1Api()
    config_map = core_api.read_namespaced_config_map(config_map_name, namespace)
    current_text = read_router_config_text(config_map)
    desired_text = ensure_router_config_tunnel_mode(
        current_text,
        "host" if enabled else "none",
    )

    if desired_text != current_text:
        core_api.patch_namespaced_config_map(
            config_map_name,
            namespace,
            {
                "data": {
                    "ziti-router.yaml": desired_text,
                }
            },
        )
        apps_api.patch_namespaced_deployment(
            deployment_name,
            namespace,
            {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "openziti.io/restarted-at": utc_timestamp(),
                            }
                        }
                    }
                }
            },
        )

    deployment = apps_api.read_namespaced_deployment(deployment_name, namespace)
    service = core_api.read_namespaced_service(service_name, namespace) if service_name else None
    config_map = core_api.read_namespaced_config_map(config_map_name, namespace)
    return build_workload_info(deployment, service, config_map)


def delete_router_workload(namespace: str, router_id: str, router_name: str) -> dict[str, Any]:
    if client is None:
        raise RuntimeError("kubernetes client 不可用")

    current_workload = find_router_workload(namespace, router_id, router_name)
    if current_workload is None:
        return {"deleted": False, "reason": "not_found"}

    apps_api = client.AppsV1Api()
    core_api = client.CoreV1Api()
    deleted: dict[str, Any] = {"deleted": True, "workload": current_workload}

    def safe_delete(fn: Any, name: str) -> None:
        if not name:
            return
        try:
            fn(name, namespace)
        except ApiException as exc:
            if getattr(exc, "status", None) != 404:
                raise

    safe_delete(apps_api.delete_namespaced_deployment, str(current_workload.get("deploymentName") or ""))
    safe_delete(core_api.delete_namespaced_service, str(current_workload.get("serviceName") or ""))
    safe_delete(core_api.delete_namespaced_config_map, str(current_workload.get("configMapName") or ""))
    safe_delete(core_api.delete_namespaced_secret, str(current_workload.get("secretName") or ""))
    safe_delete(core_api.delete_namespaced_persistent_volume_claim, str(current_workload.get("pvcName") or ""))

    return deleted
