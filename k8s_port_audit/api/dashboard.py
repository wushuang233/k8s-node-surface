from __future__ import annotations

import base64
import json
import mimetypes
import re
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..control import ServiceExposureController
from ..control.service_controls import ServiceControlError
from ..report import utc_now
from ..runtime.dependencies import ApiException, client
from ..runtime.state import ReportStore, ScanCoordinator
from ..settings.config import ScannerConfig
from .ziti_admin import (
    ZITI_RESOURCE_TYPES,
    ZitiApiError,
    ZitiManagementClient,
    ZitiSessionStore,
    default_controller_credentials_configured,
    expired_ziti_cookie_header,
    make_ziti_session,
    resolve_default_controller_password,
    resolve_default_controller_username,
    read_ziti_session_id,
    resolve_default_controller_url,
    ziti_cookie_header,
    parse_iso_datetime,
)
from .ziti_router_k8s import (
    DEFAULT_ROUTER_IMAGE,
    DEFAULT_ROUTER_IMAGE_PULL_POLICY,
    DEFAULT_ROUTER_STORAGE_CLASS,
    DEFAULT_ROUTER_STORAGE_SIZE,
    DEFAULT_ZITI_NAMESPACE,
    delete_router_workload,
    ensure_router_workload,
    find_router_workload,
    list_router_workloads,
)

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"
ZITI_WEB_DIR = Path(__file__).resolve().parent.parent.parent / "ziti"
CORE_WEB_ASSETS = [
    "index.html",
    "styles.css",
    "app.js",
    "app-data.js",
    "app-render.js",
    "render-fragments.js",
]


class DashboardHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        report_store: ReportStore,
        scanner_config: ScannerConfig,
        scan_coordinator: ScanCoordinator,
        service_controller: ServiceExposureController | None,
    ) -> None:
        super().__init__(server_address, DashboardRequestHandler)
        self.report_store = report_store
        self.scanner_config = scanner_config
        self.scan_coordinator = scan_coordinator
        self.service_controller = service_controller
        self.assets_dir = WEB_DIR
        self.ziti_assets_dir = ZITI_WEB_DIR
        self.ziti_sessions = ZitiSessionStore()

    def dashboard_snapshot(self) -> dict[str, Any]:
        payload = self.report_store.snapshot()
        payload["scan_state"] = self.scan_coordinator.snapshot()
        if self.service_controller is not None and self.scanner_config.service_control_enabled:
            try:
                payload["service_controls"] = self.service_controller.list_controls()
            except Exception as exc:
                payload["service_controls"] = {
                    "enabled": True,
                    "error": f"{type(exc).__name__}: {exc}",
                    "items": [],
                    "service_count": 0,
                    "open_port_count": 0,
                    "public_service_type": self.scanner_config.service_control_public_service_type,
                    "node_port_range": self.scanner_config.service_control_node_port_range_spec,
                }
        else:
            payload["service_controls"] = {
                "enabled": False,
                "items": [],
                "service_count": 0,
                "open_port_count": 0,
                "public_service_type": self.scanner_config.service_control_public_service_type,
                "node_port_range": self.scanner_config.service_control_node_port_range_spec,
            }
        return payload


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server: DashboardHTTPServer

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/dashboard":
            self.serve_json(self.server.dashboard_snapshot())
            return
        if path == "/api/ziti/session":
            self.handle_ziti_session()
            return
        if path == "/api/ziti/overview":
            self.handle_ziti_overview()
            return
        if path == "/healthz":
            self.serve_json(
                {
                    "status": "ok",
                    "generated_at": utc_now(),
                    "has_report": self.server.report_store.has_report(),
                }
            )
            return
        if path in {"/ziti", "/ziti/", "/ziti/index.html"}:
            self.serve_ziti_static("index.html")
            return
        if path.startswith("/ziti/"):
            self.serve_ziti_static(path.removeprefix("/ziti/"))
            return
        if path in {"/", "/index.html"}:
            self.serve_static("index.html")
            return
        if path.startswith("/"):
            self.serve_static(path.lstrip("/"))
            return

        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/scan":
            self.server.scan_coordinator.request_scan("manual", reason="用户手动刷新")
            self.serve_json(self.server.dashboard_snapshot(), status_code=202)
            return
        if path == "/api/service-controls/toggle":
            self.handle_service_control_toggle()
            return
        if path == "/api/ziti/login":
            self.handle_ziti_login()
            return
        if path == "/api/ziti/logout":
            self.handle_ziti_logout()
            return
        if path.startswith("/api/ziti/identities/") and path.endswith("/client-jwt"):
            self.handle_ziti_identity_client_jwt()
            return
        if path == "/api/ziti/edge-routers":
            self.handle_ziti_create("edge-routers")
            return
        if path == "/api/ziti/identities":
            self.handle_ziti_create("identities")
            return
        if path == "/api/ziti/service-policies":
            self.handle_ziti_create("service-policies")
            return
        if path == "/api/ziti/edge-router-policies":
            self.handle_ziti_create("edge-router-policies")
            return
        if path == "/api/ziti/services":
            self.handle_ziti_create("services")
            return
        if path == "/api/ziti/configs":
            self.handle_ziti_create("configs")
            return
        if path == "/api/ziti/service-edge-router-policies":
            self.handle_ziti_create("service-edge-router-policies")
            return
        if path.startswith("/api/ziti/edge-routers/") and path.endswith("/deploy-k8s"):
            self.handle_ziti_edge_router_deploy_k8s()
            return
        if path.startswith("/api/ziti/edge-routers/") and path.endswith("/re-enroll"):
            self.handle_ziti_edge_router_reenroll()
            return

        self.send_error(404, "Not Found")

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/ziti/"):
            self.handle_ziti_update()
            return
        self.send_error(404, "Not Found")

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/ziti/edge-routers/") and path.endswith("/deploy-k8s"):
            self.handle_ziti_edge_router_delete_k8s()
            return
        if path.startswith("/api/ziti/"):
            self.handle_ziti_delete()
            return
        self.send_error(404, "Not Found")

    def handle_service_control_toggle(self) -> None:
        if self.server.service_controller is None or not self.server.scanner_config.service_control_enabled:
            self.serve_json(
                {"error": "当前未启用业务 Service 对外治理功能"},
                status_code=404,
            )
            return

        try:
            payload = self.read_json_body()
            namespace = str(payload.get("namespace", "")).strip()
            service_name = str(payload.get("service_name", "")).strip()
            port_key = str(payload.get("port_key", "")).strip()
            public_port = payload.get("public_port")
            expose = self.read_bool(payload.get("expose"))
            if not namespace or not service_name or not port_key:
                raise ValueError("namespace、service_name、port_key 不能为空")

            action = self.server.service_controller.set_port_exposure(
                namespace=namespace,
                service_name=service_name,
                port_key=port_key,
                expose=expose,
                public_port=public_port,
            )
        except json.JSONDecodeError:
            self.serve_json({"error": "请求体不是合法 JSON"}, status_code=400)
            return
        except ValueError as exc:
            self.serve_json({"error": str(exc)}, status_code=400)
            return
        except ServiceControlError as exc:
            self.serve_json({"error": str(exc)}, status_code=409)
            return
        except ApiException as exc:
            self.serve_json(
                {"error": f"Kubernetes API 错误: status={getattr(exc, 'status', 'unknown')} detail={exc}"},
                status_code=502,
            )
            return

        self.server.scan_coordinator.request_scan(
            "service_control",
            reason=f"业务 Service 端口{'打开' if expose else '关闭'}",
            full_scan=False,
            service_refs={
                (namespace, service_name),
                (namespace, action["managed_service_name"]),
            },
            node_port_refs=set(action.get("affected_node_ports") or []),
        )
        response = self.server.dashboard_snapshot()
        response["service_control_action"] = action
        self.serve_json(response, status_code=200)

    def handle_ziti_session(self) -> None:
        session_id = read_ziti_session_id(self.headers.get("Cookie"))
        session = self.server.ziti_sessions.get(session_id)
        payload = {
            "logged_in": session is not None,
            "default_controller_url": resolve_default_controller_url(),
            "default_username": resolve_default_controller_username(),
            "default_credentials_configured": default_controller_credentials_configured(),
        }
        if session is not None:
            payload.update(
                {
                    "controller_url": session.controller_url,
                    "username": session.username,
                    "identity_id": session.identity_id,
                    "identity_name": session.identity_name,
                    "expires_at": session.expires_at,
                }
            )
        self.serve_json(payload)

    def handle_ziti_login(self) -> None:
        try:
            payload = self.read_json_body()
            username = str(payload.get("username", "")).strip() or resolve_default_controller_username()
            password = str(payload.get("password", "")).strip()
            if not password and default_controller_credentials_configured():
                password = resolve_default_controller_password()
            controller_url = str(payload.get("controller_url", "")).strip() or resolve_default_controller_url()
            if not username or not password:
                raise ValueError("username 和 password 不能为空；也可以在 port-audit Pod 里预设默认凭据")

            client = ZitiManagementClient(controller_url)
            auth_payload = client.authenticate(username, password)
            session = make_ziti_session(controller_url, username, auth_payload)
            session_id = self.server.ziti_sessions.create(session)
        except json.JSONDecodeError:
            self.serve_json({"error": "请求体不是合法 JSON"}, status_code=400)
            return
        except ValueError as exc:
            self.serve_json({"error": str(exc)}, status_code=400)
            return
        except ZitiApiError as exc:
            self.serve_json({"error": str(exc)}, status_code=exc.status_code)
            return

        self.serve_json(
            {
                "logged_in": True,
                "controller_url": session.controller_url,
                "username": session.username,
                "identity_id": session.identity_id,
                "identity_name": session.identity_name,
                "expires_at": session.expires_at,
            },
            headers={"Set-Cookie": ziti_cookie_header(session_id)},
        )

    def handle_ziti_logout(self) -> None:
        session_id = read_ziti_session_id(self.headers.get("Cookie"))
        self.server.ziti_sessions.delete(session_id)
        self.serve_json(
            {"logged_in": False},
            headers={"Set-Cookie": expired_ziti_cookie_header()},
        )

    def handle_ziti_overview(self) -> None:
        try:
            session_id, session, _client = self.require_ziti_client()
            routers = self.ziti_request_json("GET", "/edge/management/v1/edge-routers", query={"limit": "500"}).get(
                "data",
            [],
            )
            services = self.ziti_request_json("GET", "/edge/management/v1/services", query={"limit": "500"}).get(
                "data",
                [],
            )
            configs = self.ziti_request_json("GET", "/edge/management/v1/configs", query={"limit": "500"}).get(
                "data",
                [],
            )
            config_types = self.ziti_request_json(
                "GET",
                "/edge/management/v1/config-types",
                query={"limit": "500"},
            ).get("data", [])
            service_policies = self.ziti_request_json(
                "GET",
                "/edge/management/v1/service-policies",
                query={"limit": "500"},
            ).get("data", [])
            edge_router_policies = self.ziti_request_json(
                "GET",
                "/edge/management/v1/edge-router-policies",
                query={"limit": "500"},
            ).get("data", [])
            service_edge_router_policies = self.ziti_request_json(
                "GET",
                "/edge/management/v1/service-edge-router-policies",
                query={"limit": "500"},
            ).get("data", [])
            identities = self.ziti_request_json(
                "GET",
                "/edge/management/v1/identities",
                query={"limit": "500"},
            ).get("data", [])
            for identity in identities if isinstance(identities, list) else []:
                if not isinstance(identity, dict):
                    continue
                enrollment = identity.get("enrollment")
                if not isinstance(enrollment, dict):
                    continue
                for method_payload in enrollment.values():
                    if isinstance(method_payload, dict):
                        method_payload.pop("jwt", None)
                        method_payload.pop("token", None)
            posture_checks = self.ziti_request_json(
                "GET",
                "/edge/management/v1/posture-checks",
                query={"limit": "500"},
            ).get("data", [])
            auth_policies = self.ziti_request_json(
                "GET",
                "/edge/management/v1/auth-policies",
                query={"limit": "500"},
            ).get("data", [])
            raw_enrollments = self.ziti_request_json(
                "GET",
                "/edge/management/v1/enrollments",
                query={"limit": "500"},
            ).get("data", [])
            enrollments = [
                {key: value for key, value in item.items() if key not in {"jwt", "token"}}
                for item in raw_enrollments
                if isinstance(item, dict)
            ]
            k8s_services = self.list_k8s_services()
            router_workloads = list_router_workloads(DEFAULT_ZITI_NAMESPACE)
        except ZitiApiError as exc:
            headers = {"Set-Cookie": expired_ziti_cookie_header()} if exc.status_code == 401 else None
            self.serve_json({"error": str(exc)}, status_code=exc.status_code, headers=headers)
            return

        workload_by_router_id = {
            str(item.get("routerId") or "").strip(): item
            for item in router_workloads
            if str(item.get("routerId") or "").strip()
        }
        workload_by_router_name = {
            str(item.get("routerName") or "").strip(): item
            for item in router_workloads
            if str(item.get("routerName") or "").strip()
        }
        for router in routers if isinstance(routers, list) else []:
            if not isinstance(router, dict):
                continue
            router_id = str(router.get("id") or "").strip()
            router_name = str(router.get("name") or "").strip()
            router["k8sWorkload"] = workload_by_router_id.get(router_id) or workload_by_router_name.get(router_name)

        self.serve_json(
            {
                "edge_routers": routers,
                "edge_router_workloads": router_workloads,
                "services": services,
                "configs": configs,
                "config_types": config_types,
                "service_policies": service_policies,
                "edge_router_policies": edge_router_policies,
                "service_edge_router_policies": service_edge_router_policies,
                "identities": identities,
                "posture_checks": posture_checks,
                "auth_policies": auth_policies,
                "enrollments": enrollments,
                "k8s_services": k8s_services,
                "counts": {
                    "edge_routers": len(routers),
                    "alive_edge_routers": sum(1 for item in routers if item.get("isOnline")),
                    "deployed_edge_routers": sum(1 for item in routers if item.get("k8sWorkload")),
                    "services": len(services),
                    "configs": len(configs),
                    "config_types": len(config_types),
                    "service_policies": len(service_policies),
                    "edge_router_policies": len(edge_router_policies),
                    "service_edge_router_policies": len(service_edge_router_policies),
                    "identities": len(identities),
                    "posture_checks": len(posture_checks),
                    "auth_policies": len(auth_policies),
                    "enrollments": len(enrollments),
                },
            }
        )

    def list_k8s_services(self) -> list[dict[str, Any]]:
        if client is None:
            return []

        try:
            api = self.server.service_controller.core_api if self.server.service_controller is not None else client.CoreV1Api()
            services = api.list_service_for_all_namespaces(watch=False).items
        except Exception:
            return []

        items: list[dict[str, Any]] = []
        for service in services:
            namespace = str(getattr(service.metadata, "namespace", "") or "").strip()
            name = str(getattr(service.metadata, "name", "") or "").strip()
            spec = getattr(service, "spec", None)
            cluster_ip = str(
                getattr(spec, "cluster_ip", None) or getattr(spec, "clusterIP", None) or ""
            ).strip()
            service_type = str(getattr(spec, "type", None) or "ClusterIP")
            ports = []
            for port_def in getattr(spec, "ports", None) or []:
                port_value = getattr(port_def, "port", None)
                if port_value in {None, ""}:
                    continue
                ports.append(
                    {
                        "name": str(getattr(port_def, "name", None) or ""),
                        "protocol": str(getattr(port_def, "protocol", None) or "TCP"),
                        "port": int(port_value),
                        "target_port": (
                            str(getattr(port_def, "target_port", None))
                            if getattr(port_def, "target_port", None) is not None
                            else ""
                        ),
                    }
                )
            items.append(
                {
                    "namespace": namespace,
                    "name": name,
                    "type": service_type,
                    "cluster_ip": cluster_ip,
                    "fqdn": f"{name}.{namespace}.svc.cluster.local" if name and namespace else "",
                    "ports": ports,
                }
            )

        items.sort(key=lambda item: (item.get("namespace", ""), item.get("name", "")))
        return items

    def handle_ziti_create(self, resource_type: str) -> None:
        try:
            payload = self.read_json_body()
            body = self.build_ziti_payload(resource_type, payload, is_create=True)
            response = self.ziti_request_json(
                "POST",
                f"/edge/management/v1/{resource_type}",
                json_body=body,
            )
            data = response.get("data") or {}
            if isinstance(data, dict) and data.get("id"):
                response = self.ziti_request_json(
                    "GET",
                    f"/edge/management/v1/{resource_type}/{data['id']}",
                )
        except json.JSONDecodeError:
            self.serve_json({"error": "请求体不是合法 JSON"}, status_code=400)
            return
        except ValueError as exc:
            self.serve_json({"error": str(exc)}, status_code=400)
            return
        except ZitiApiError as exc:
            headers = {"Set-Cookie": expired_ziti_cookie_header()} if exc.status_code == 401 else None
            self.serve_json({"error": str(exc)}, status_code=exc.status_code, headers=headers)
            return

        self.serve_json({"data": response.get("data") or {}}, status_code=201)

    def handle_ziti_update(self) -> None:
        path = urlparse(self.path).path
        segments = self.path_segments(path)
        if len(segments) != 4 or segments[:2] != ["api", "ziti"] or segments[2] not in ZITI_RESOURCE_TYPES:
            self.send_error(404, "Not Found")
            return

        resource_type = segments[2]
        entity_id = segments[3]
        try:
            payload = self.read_json_body()
            body = self.build_ziti_payload(resource_type, payload, is_create=False)
            self.ziti_request_json(
                "PATCH",
                f"/edge/management/v1/{resource_type}/{entity_id}",
                json_body=body,
            )
            response = self.ziti_request_json("GET", f"/edge/management/v1/{resource_type}/{entity_id}")
        except json.JSONDecodeError:
            self.serve_json({"error": "请求体不是合法 JSON"}, status_code=400)
            return
        except ValueError as exc:
            self.serve_json({"error": str(exc)}, status_code=400)
            return
        except ZitiApiError as exc:
            headers = {"Set-Cookie": expired_ziti_cookie_header()} if exc.status_code == 401 else None
            self.serve_json({"error": str(exc)}, status_code=exc.status_code, headers=headers)
            return

        self.serve_json({"data": response.get("data") or {}}, status_code=200)

    def handle_ziti_delete(self) -> None:
        path = urlparse(self.path).path
        segments = self.path_segments(path)
        if len(segments) != 4 or segments[:2] != ["api", "ziti"] or segments[2] not in ZITI_RESOURCE_TYPES:
            self.send_error(404, "Not Found")
            return

        resource_type = segments[2]
        entity_id = segments[3]
        try:
            if resource_type == "edge-routers":
                router = self.ziti_request_json("GET", f"/edge/management/v1/edge-routers/{entity_id}").get("data") or {}
                delete_router_workload(
                    DEFAULT_ZITI_NAMESPACE,
                    str(router.get("id") or entity_id),
                    str(router.get("name") or ""),
                )
            self.ziti_request_json("DELETE", f"/edge/management/v1/{resource_type}/{entity_id}")
        except ZitiApiError as exc:
            headers = {"Set-Cookie": expired_ziti_cookie_header()} if exc.status_code == 401 else None
            self.serve_json({"error": str(exc)}, status_code=exc.status_code, headers=headers)
            return

        self.serve_json({"deleted": True, "id": entity_id})

    def handle_ziti_edge_router_reenroll(self) -> None:
        path = urlparse(self.path).path
        segments = self.path_segments(path)
        if len(segments) != 5 or segments[:3] != ["api", "ziti", "edge-routers"] or segments[4] != "re-enroll":
            self.send_error(404, "Not Found")
            return

        entity_id = segments[3]
        try:
            self.ziti_request_json("POST", f"/edge/management/v1/edge-routers/{entity_id}/re-enroll")
            response = self.ziti_request_json("GET", f"/edge/management/v1/edge-routers/{entity_id}")
        except ZitiApiError as exc:
            headers = {"Set-Cookie": expired_ziti_cookie_header()} if exc.status_code == 401 else None
            self.serve_json({"error": str(exc)}, status_code=exc.status_code, headers=headers)
            return

        self.serve_json({"data": response.get("data") or {}}, status_code=200)

    def handle_ziti_edge_router_deploy_k8s(self) -> None:
        path = urlparse(self.path).path
        segments = self.path_segments(path)
        if len(segments) != 5 or segments[:3] != ["api", "ziti", "edge-routers"] or segments[4] != "deploy-k8s":
            self.send_error(404, "Not Found")
            return

        entity_id = segments[3]
        try:
            payload = self.read_json_body()
            _session_id, session, _client = self.require_ziti_client()
            router = self.ziti_request_json("GET", f"/edge/management/v1/edge-routers/{entity_id}").get("data") or {}
            if not isinstance(router, dict) or not router.get("id"):
                raise ValueError("找不到对应的 edge router")

            enrollment_jwt = str(router.get("enrollmentJwt") or "").strip()
            enrollment_expires_at = parse_iso_datetime(str(router.get("enrollmentExpiresAt") or ""))
            needs_reenroll = (
                not enrollment_jwt
                or enrollment_expires_at is None
                or enrollment_expires_at <= datetime.now(timezone.utc).timestamp() + 60
            )
            if needs_reenroll:
                self.ziti_request_json("POST", f"/edge/management/v1/edge-routers/{entity_id}/re-enroll")
                router = self.ziti_request_json("GET", f"/edge/management/v1/edge-routers/{entity_id}").get("data") or {}
                enrollment_jwt = str(router.get("enrollmentJwt") or "").strip()
            if not enrollment_jwt:
                raise ValueError("controller 没有返回可用的 router enrollment JWT")

            workload = ensure_router_workload(
                namespace=DEFAULT_ZITI_NAMESPACE,
                router=router,
                controller_url=session.controller_url,
                enrollment_jwt=enrollment_jwt,
                public_host=str(payload.get("publicHost") or "").strip(),
                requested_node_port=self.read_int(payload.get("nodePort"), "nodePort", 0) or None,
                storage_class_name=str(payload.get("storageClassName") or DEFAULT_ROUTER_STORAGE_CLASS).strip() or DEFAULT_ROUTER_STORAGE_CLASS,
                storage_size=str(payload.get("storageSize") or DEFAULT_ROUTER_STORAGE_SIZE).strip() or DEFAULT_ROUTER_STORAGE_SIZE,
                image=str(payload.get("image") or DEFAULT_ROUTER_IMAGE).strip() or DEFAULT_ROUTER_IMAGE,
                image_pull_policy=str(payload.get("imagePullPolicy") or DEFAULT_ROUTER_IMAGE_PULL_POLICY).strip()
                or DEFAULT_ROUTER_IMAGE_PULL_POLICY,
            )
            response = self.ziti_request_json("GET", f"/edge/management/v1/edge-routers/{entity_id}")
            router = response.get("data") or {}
            router["k8sWorkload"] = workload
        except json.JSONDecodeError:
            self.serve_json({"error": "请求体不是合法 JSON"}, status_code=400)
            return
        except ValueError as exc:
            self.serve_json({"error": str(exc)}, status_code=400)
            return
        except ZitiApiError as exc:
            headers = {"Set-Cookie": expired_ziti_cookie_header()} if exc.status_code == 401 else None
            self.serve_json({"error": str(exc)}, status_code=exc.status_code, headers=headers)
            return
        except ApiException as exc:
            self.serve_json({"error": f"Kubernetes API 调用失败: {exc}"}, status_code=500)
            return
        except Exception as exc:
            self.serve_json({"error": f"部署 router 到 K8s 失败: {type(exc).__name__}: {exc}"}, status_code=500)
            return

        self.serve_json({"data": router, "workload": workload}, status_code=200)

    def handle_ziti_edge_router_delete_k8s(self) -> None:
        path = urlparse(self.path).path
        segments = self.path_segments(path)
        if len(segments) != 5 or segments[:3] != ["api", "ziti", "edge-routers"] or segments[4] != "deploy-k8s":
            self.send_error(404, "Not Found")
            return

        entity_id = segments[3]
        try:
            router = self.ziti_request_json("GET", f"/edge/management/v1/edge-routers/{entity_id}").get("data") or {}
            deleted = delete_router_workload(
                DEFAULT_ZITI_NAMESPACE,
                str(router.get("id") or entity_id),
                str(router.get("name") or ""),
            )
        except ZitiApiError as exc:
            headers = {"Set-Cookie": expired_ziti_cookie_header()} if exc.status_code == 401 else None
            self.serve_json({"error": str(exc)}, status_code=exc.status_code, headers=headers)
            return
        except ApiException as exc:
            self.serve_json({"error": f"Kubernetes API 调用失败: {exc}"}, status_code=500)
            return
        except Exception as exc:
            self.serve_json({"error": f"删除 router K8s 工作负载失败: {type(exc).__name__}: {exc}"}, status_code=500)
            return

        self.serve_json(deleted, status_code=200)

    def handle_ziti_identity_client_jwt(self) -> None:
        path = urlparse(self.path).path
        segments = self.path_segments(path)
        if len(segments) != 5 or segments[:3] != ["api", "ziti", "identities"] or segments[4] != "client-jwt":
            self.send_error(404, "Not Found")
            return

        identity_id = segments[3]
        try:
            payload = self.read_json_body()
            _session_id, session, _client = self.require_ziti_client()
            rotate = self.read_optional_bool(payload.get("rotate"), default=False)
            duration_minutes = self.read_positive_int(payload.get("durationMinutes"), "durationMinutes", default=30)
            identity = self.ziti_request_json("GET", f"/edge/management/v1/identities/{identity_id}").get("data") or {}
            enrollments = self.ziti_request_json("GET", f"/edge/management/v1/identities/{identity_id}/enrollments").get("data", [])
            current = self.pick_latest_enrollment(enrollments, method="ott")
            created = False
            reused = False

            if rotate and current and current.get("id"):
                self.ziti_request_json("DELETE", f"/edge/management/v1/enrollments/{current['id']}")
                current = None

            if current and not self.enrollment_matches_controller(current, session.controller_url):
                enrollment_id = str(current.get("id") or "").strip()
                if enrollment_id:
                    self.ziti_request_json("DELETE", f"/edge/management/v1/enrollments/{enrollment_id}")
                current = None

            if current is None:
                try:
                    create_response = self.ziti_request_json(
                        "POST",
                        "/edge/management/v1/enrollments",
                        json_body={
                            "identityId": identity_id,
                            "method": "ott",
                            "expiresAt": self.build_enrollment_expiry(duration_minutes),
                        },
                    )
                    created_id = str((create_response.get("data") or {}).get("id") or "").strip()
                    enrollments = self.ziti_request_json("GET", f"/edge/management/v1/identities/{identity_id}/enrollments").get(
                        "data",
                        [],
                    )
                    current = (
                        next(
                            (
                                item
                                for item in enrollments
                                if created_id and str(item.get("id") or "").strip() == created_id
                            ),
                            None,
                        )
                        or self.pick_latest_enrollment(enrollments, method="ott")
                    )
                    created = True
                except ZitiApiError as exc:
                    if exc.status_code != 409:
                        raise
                    enrollments = self.ziti_request_json("GET", f"/edge/management/v1/identities/{identity_id}/enrollments").get(
                        "data",
                        [],
                    )
                    current = self.pick_latest_enrollment(enrollments, method="ott")
                    reused = current is not None
            else:
                reused = True

            if not isinstance(current, dict) or not current.get("jwt"):
                raise ValueError("controller 没有返回可用的客户端 enrollment JWT")
        except json.JSONDecodeError:
            self.serve_json({"error": "请求体不是合法 JSON"}, status_code=400)
            return
        except ValueError as exc:
            self.serve_json({"error": str(exc)}, status_code=400)
            return
        except ZitiApiError as exc:
            headers = {"Set-Cookie": expired_ziti_cookie_header()} if exc.status_code == 401 else None
            self.serve_json({"error": str(exc)}, status_code=exc.status_code, headers=headers)
            return

        self.serve_json(
            {
                "data": {
                    "identity": identity,
                    "enrollment": current,
                    "created": created,
                    "reused": reused,
                    "rotated": rotate,
                }
            },
            status_code=200,
        )

    def serve_static(self, file_name: str) -> None:
        self.serve_static_from(self.server.assets_dir, file_name)

    def serve_ziti_static(self, file_name: str) -> None:
        self.serve_static_from(self.server.ziti_assets_dir, file_name)

    def serve_static_from(self, base_dir: Path, file_name: str) -> None:
        assets_dir = base_dir.resolve()
        asset_path = (assets_dir / file_name).resolve()

        try:
            asset_path.relative_to(assets_dir)
        except ValueError:
            self.send_error(404, "Not Found")
            return

        if asset_path.is_dir():
            asset_path = asset_path / "index.html"

        if not asset_path.exists() or not asset_path.is_file():
            self.send_error(404, "Not Found")
            return

        content_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
        payload = asset_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def serve_json(
        self,
        payload: dict[str, Any],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        payload = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return payload

    @staticmethod
    def read_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        raise ValueError("字段必须是布尔值")

    @staticmethod
    def read_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        raise ValueError("列表字段必须是字符串或数组")

    @staticmethod
    def read_int(value: Any, field_name: str, default: int = 0) -> int:
        if value in {None, ""}:
            return default
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} 必须是整数") from exc

    @classmethod
    def read_positive_int(cls, value: Any, field_name: str, default: int = 30) -> int:
        parsed = cls.read_int(value, field_name, default)
        if parsed <= 0:
            raise ValueError(f"{field_name} 必须大于 0")
        return parsed

    @staticmethod
    def read_optional_bool(value: Any, default: bool = False) -> bool:
        if value in {None, ""}:
            return default
        return DashboardRequestHandler.read_bool(value)

    @staticmethod
    def read_duration_millis(value: Any, field_name: str) -> int | None:
        if value in {None, ""}:
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)

        text = str(value).strip().lower()
        if not text:
            return None
        if text.isdigit():
            return int(text)

        match = re.fullmatch(r"(\d+)(ms|s|m|h)", text)
        if not match:
            raise ValueError(f"{field_name} 必须是整数毫秒，或类似 500ms / 30s / 5m / 1h 的时长")

        amount = int(match.group(1))
        unit = match.group(2)
        scale = {"ms": 1, "s": 1000, "m": 60_000, "h": 3_600_000}[unit]
        return amount * scale

    @staticmethod
    def read_dict(value: Any, field_name: str) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"{field_name} 必须是 JSON 对象")
        return value

    @staticmethod
    def path_segments(path: str) -> list[str]:
        return [segment for segment in path.split("/") if segment]

    @staticmethod
    def pick_latest_enrollment(items: list[dict[str, Any]] | Any, method: str | None = None) -> dict[str, Any] | None:
        candidates = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            if method and str(item.get("method") or "").strip().lower() != method.lower():
                continue
            candidates.append(item)
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                str(item.get("expiresAt") or ""),
                str(item.get("createdAt") or ""),
                str(item.get("id") or ""),
            ),
            reverse=True,
        )
        return candidates[0]

    @staticmethod
    def build_enrollment_expiry(duration_minutes: int) -> str:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
        return expires_at.isoformat().replace("+00:00", "Z")

    @staticmethod
    def decode_jwt_claims(token: str | None) -> dict[str, Any]:
        if not token or not isinstance(token, str):
            return {}

        parts = token.split(".")
        if len(parts) < 2:
            return {}

        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        try:
            decoded = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
            claims = json.loads(decoded)
        except Exception:
            return {}

        return claims if isinstance(claims, dict) else {}

    @staticmethod
    def controller_url_to_enrollment_ctrl(controller_url: str) -> str:
        parsed = urlparse(controller_url)
        host = (parsed.hostname or "").strip()
        if not host:
            return ""

        if parsed.port:
            port = parsed.port
        elif parsed.scheme == "https":
            port = 443
        else:
            port = 80
        return f"tls:{host}:{port}"

    def enrollment_matches_controller(self, enrollment: dict[str, Any], controller_url: str) -> bool:
        claims = self.decode_jwt_claims(str(enrollment.get("jwt") or ""))
        if not claims:
            return False

        if str(claims.get("iss") or "").strip() != str(controller_url).strip():
            return False

        expected_ctrl = self.controller_url_to_enrollment_ctrl(controller_url)
        ctrls = claims.get("ctrls")
        if expected_ctrl and isinstance(ctrls, list):
            return expected_ctrl in {str(item).strip() for item in ctrls}
        return False

    def require_ziti_client(self) -> tuple[str, Any, ZitiManagementClient]:
        session_id = read_ziti_session_id(self.headers.get("Cookie"))
        session = self.server.ziti_sessions.get(session_id)
        if session is None:
            raise ZitiApiError("请先登录 Ziti controller", status_code=401)
        return session_id or "", session, ZitiManagementClient(session.controller_url)

    def ziti_request_json(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        session_id, session, client = self.require_ziti_client()
        try:
            return client.request_json(
                method=method,
                path=path,
                json_body=json_body,
                query=query,
                session_token=session.token,
            )
        except ZitiApiError as exc:
            if exc.status_code == 401:
                self.server.ziti_sessions.delete(session_id)
            raise

    def build_ziti_payload(
        self,
        resource_type: str,
        payload: dict[str, Any],
        *,
        is_create: bool,
    ) -> dict[str, Any]:
        if resource_type == "identities":
            return self.build_identity_payload(payload, is_create=is_create)
        if resource_type == "service-policies":
            return self.build_service_policy_payload(payload, is_create=is_create)
        if resource_type == "edge-router-policies":
            return self.build_edge_router_policy_payload(payload, is_create=is_create)
        if resource_type == "services":
            return self.build_service_payload(payload, is_create=is_create)
        if resource_type == "configs":
            return self.build_config_payload(payload, is_create=is_create)
        if resource_type == "service-edge-router-policies":
            return self.build_service_edge_router_policy_payload(payload, is_create=is_create)
        if resource_type == "edge-routers":
            return self.build_edge_router_payload(payload, is_create=is_create)
        raise ValueError(f"不支持的资源类型: {resource_type}")

    def build_identity_payload(self, payload: dict[str, Any], *, is_create: bool) -> dict[str, Any]:
        body: dict[str, Any] = {}
        name = str(payload.get("name", "")).strip()
        if is_create and not name:
            raise ValueError("identity name 不能为空")
        if name:
            body["name"] = name

        auth_policy_id = str(payload.get("authPolicyId", "")).strip()
        if auth_policy_id:
            body["authPolicyId"] = auth_policy_id
        elif is_create:
            body["authPolicyId"] = "default"

        role_attributes = self.read_str_list(payload.get("roleAttributes"))
        if role_attributes or payload.get("roleAttributes") == "":
            body["roleAttributes"] = role_attributes if role_attributes else None

        external_id = payload.get("externalId")
        if external_id is not None:
            external_id_text = str(external_id).strip()
            body["externalId"] = external_id_text or None

        if is_create:
            body["type"] = str(payload.get("type", "Default")).strip() or "Default"
            body["isAdmin"] = bool(payload.get("isAdmin", False))
            body["defaultHostingCost"] = self.read_int(
                payload.get("defaultHostingCost"),
                "defaultHostingCost",
                0,
            )
            body["defaultHostingPrecedence"] = (
                str(payload.get("defaultHostingPrecedence", "default")).strip() or "default"
            )
            body["serviceHostingCosts"] = {}
            body["serviceHostingPrecedences"] = {}
            body["tags"] = payload.get("tags") if isinstance(payload.get("tags"), dict) else {}
            updb_username = str(payload.get("updbUsername", "")).strip()
            if updb_username:
                body["enrollment"] = {"updb": updb_username}
        else:
            if "isAdmin" in payload:
                body["isAdmin"] = bool(payload.get("isAdmin"))
            if "defaultHostingCost" in payload:
                body["defaultHostingCost"] = self.read_int(
                    payload.get("defaultHostingCost"),
                    "defaultHostingCost",
                    0,
                )
            if payload.get("defaultHostingPrecedence") is not None:
                body["defaultHostingPrecedence"] = (
                    str(payload.get("defaultHostingPrecedence", "default")).strip() or "default"
                )
            if isinstance(payload.get("tags"), dict):
                body["tags"] = payload["tags"]

        if not body:
            raise ValueError("没有可提交的 identity 字段")
        return body

    def build_service_policy_payload(self, payload: dict[str, Any], *, is_create: bool) -> dict[str, Any]:
        body: dict[str, Any] = {}
        name = str(payload.get("name", "")).strip()
        if is_create and not name:
            raise ValueError("service policy name 不能为空")
        if name:
            body["name"] = name
        if is_create:
            policy_type = str(payload.get("type", "")).strip()
            if not policy_type:
                raise ValueError("service policy type 不能为空")
            body["type"] = policy_type
            body["semantic"] = str(payload.get("semantic", "AnyOf")).strip() or "AnyOf"
            body["tags"] = payload.get("tags") if isinstance(payload.get("tags"), dict) else {}
            body["identityRoles"] = self.read_str_list(payload.get("identityRoles"))
            body["serviceRoles"] = self.read_str_list(payload.get("serviceRoles"))
            body["postureCheckRoles"] = self.read_str_list(payload.get("postureCheckRoles"))
        else:
            if payload.get("semantic") is not None:
                body["semantic"] = str(payload.get("semantic", "AnyOf")).strip() or "AnyOf"
            if "identityRoles" in payload:
                body["identityRoles"] = self.read_str_list(payload.get("identityRoles"))
            if "serviceRoles" in payload:
                body["serviceRoles"] = self.read_str_list(payload.get("serviceRoles"))
            if "postureCheckRoles" in payload:
                body["postureCheckRoles"] = self.read_str_list(payload.get("postureCheckRoles"))
            if isinstance(payload.get("tags"), dict):
                body["tags"] = payload["tags"]
        if not body:
            raise ValueError("没有可提交的 service policy 字段")
        return body

    def build_edge_router_policy_payload(
        self,
        payload: dict[str, Any],
        *,
        is_create: bool,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        name = str(payload.get("name", "")).strip()
        if is_create and not name:
            raise ValueError("edge router policy name 不能为空")
        if name:
            body["name"] = name
        if is_create:
            body["semantic"] = str(payload.get("semantic", "AnyOf")).strip() or "AnyOf"
            body["tags"] = payload.get("tags") if isinstance(payload.get("tags"), dict) else {}
            body["identityRoles"] = self.read_str_list(payload.get("identityRoles"))
            body["edgeRouterRoles"] = self.read_str_list(payload.get("edgeRouterRoles"))
        else:
            if payload.get("semantic") is not None:
                body["semantic"] = str(payload.get("semantic", "AnyOf")).strip() or "AnyOf"
            if "identityRoles" in payload:
                body["identityRoles"] = self.read_str_list(payload.get("identityRoles"))
            if "edgeRouterRoles" in payload:
                body["edgeRouterRoles"] = self.read_str_list(payload.get("edgeRouterRoles"))
            if isinstance(payload.get("tags"), dict):
                body["tags"] = payload["tags"]
        if not body:
            raise ValueError("没有可提交的 edge router policy 字段")
        return body

    def build_edge_router_payload(self, payload: dict[str, Any], *, is_create: bool) -> dict[str, Any]:
        body: dict[str, Any] = {}
        name = str(payload.get("name", "")).strip()
        if is_create and not name:
            raise ValueError("edge router name 不能为空")
        if name:
            body["name"] = name
        if "cost" in payload or is_create:
            body["cost"] = self.read_int(payload.get("cost"), "cost", 0)
        if "disabled" in payload or is_create:
            body["disabled"] = bool(payload.get("disabled", False))
        if "noTraversal" in payload or is_create:
            body["noTraversal"] = bool(payload.get("noTraversal", False))
        if "isTunnelerEnabled" in payload or is_create:
            body["isTunnelerEnabled"] = bool(payload.get("isTunnelerEnabled", False))
        role_attributes = self.read_str_list(payload.get("roleAttributes"))
        if role_attributes or payload.get("roleAttributes") == "" or is_create:
            body["roleAttributes"] = role_attributes if role_attributes else []
        if isinstance(payload.get("tags"), dict) or is_create:
            body["tags"] = payload.get("tags") if isinstance(payload.get("tags"), dict) else {}
        if not body:
            raise ValueError("没有可提交的 edge router 字段")
        return body

    def build_service_payload(self, payload: dict[str, Any], *, is_create: bool) -> dict[str, Any]:
        body: dict[str, Any] = {}
        name = str(payload.get("name", "")).strip()
        if is_create and not name:
            raise ValueError("service name 不能为空")
        if name:
            body["name"] = name

        if is_create:
            body["encryptionRequired"] = bool(payload.get("encryptionRequired", True))

        if "configs" in payload or is_create:
            body["configs"] = self.read_str_list(payload.get("configs"))

        role_attributes = self.read_str_list(payload.get("roleAttributes"))
        if role_attributes or payload.get("roleAttributes") == "" or is_create:
            body["roleAttributes"] = role_attributes if role_attributes else []

        if payload.get("terminatorStrategy") is not None or is_create:
            terminator_strategy = str(payload.get("terminatorStrategy", "smartrouting")).strip()
            body["terminatorStrategy"] = terminator_strategy or "smartrouting"

        if payload.get("maxIdleTime") is not None or payload.get("maxIdleTimeMillis") is not None:
            max_idle_time_millis = self.read_duration_millis(
                payload.get("maxIdleTimeMillis", payload.get("maxIdleTime")),
                "maxIdleTime",
            )
            if max_idle_time_millis is not None:
                body["maxIdleTimeMillis"] = max_idle_time_millis

        if isinstance(payload.get("tags"), dict) or is_create:
            body["tags"] = payload.get("tags") if isinstance(payload.get("tags"), dict) else {}

        if not body:
            raise ValueError("没有可提交的 service 字段")
        return body

    def build_config_payload(self, payload: dict[str, Any], *, is_create: bool) -> dict[str, Any]:
        body: dict[str, Any] = {}
        name = str(payload.get("name", "")).strip()
        if is_create and not name:
            raise ValueError("config name 不能为空")
        if name:
            body["name"] = name

        if is_create:
            config_type_id = str(payload.get("configTypeId", "")).strip()
            if not config_type_id:
                raise ValueError("configTypeId 不能为空")
            body["configTypeId"] = config_type_id

        if "data" in payload or is_create:
            body["data"] = self.read_dict(payload.get("data"), "data")

        if isinstance(payload.get("tags"), dict) or is_create:
            body["tags"] = payload.get("tags") if isinstance(payload.get("tags"), dict) else {}

        if not body:
            raise ValueError("没有可提交的 config 字段")
        return body

    def build_service_edge_router_policy_payload(
        self,
        payload: dict[str, Any],
        *,
        is_create: bool,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        name = str(payload.get("name", "")).strip()
        if is_create and not name:
            raise ValueError("service edge router policy name 不能为空")
        if name:
            body["name"] = name

        if is_create:
            body["semantic"] = str(payload.get("semantic", "AnyOf")).strip() or "AnyOf"
            body["serviceRoles"] = self.read_str_list(payload.get("serviceRoles"))
            body["edgeRouterRoles"] = self.read_str_list(payload.get("edgeRouterRoles"))
            body["tags"] = payload.get("tags") if isinstance(payload.get("tags"), dict) else {}
        else:
            if payload.get("semantic") is not None:
                body["semantic"] = str(payload.get("semantic", "AnyOf")).strip() or "AnyOf"
            if "serviceRoles" in payload:
                body["serviceRoles"] = self.read_str_list(payload.get("serviceRoles"))
            if "edgeRouterRoles" in payload:
                body["edgeRouterRoles"] = self.read_str_list(payload.get("edgeRouterRoles"))
            if isinstance(payload.get("tags"), dict):
                body["tags"] = payload["tags"]

        if not body:
            raise ValueError("没有可提交的 service edge router policy 字段")
        return body

    def log_message(self, format: str, *args: Any) -> None:
        return


def start_dashboard_server(
    scanner_config: ScannerConfig,
    report_store: ReportStore,
    scan_coordinator: ScanCoordinator,
    service_controller: ServiceExposureController | None = None,
) -> DashboardHTTPServer | None:
    if not scanner_config.web_enabled:
        return None

    missing_assets = [name for name in CORE_WEB_ASSETS if not (WEB_DIR / name).exists()]
    if missing_assets:
        raise RuntimeError(f"缺少前端资源文件: {', '.join(missing_assets)}")

    server = DashboardHTTPServer(
        (scanner_config.web_host, scanner_config.web_port),
        report_store,
        scanner_config,
        scan_coordinator,
        service_controller,
    )
    thread = threading.Thread(
        target=server.serve_forever,
        name="dashboard-server",
        daemon=True,
    )
    thread.start()
    print(
        f"宿主机暴露面板已启动: http://{scanner_config.web_host}:{scanner_config.web_port}",
        flush=True,
    )
    return server


def stop_dashboard_server(server: DashboardHTTPServer | None) -> None:
    if server is None:
        return

    server.shutdown()
    server.server_close()
