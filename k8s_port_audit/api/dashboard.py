from __future__ import annotations

import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..control import ServiceExposureController
from ..control.service_controls import ServiceControlError
from ..report import utc_now
from ..runtime.dependencies import ApiException
from ..runtime.state import ReportStore, ScanCoordinator
from ..settings.config import ScannerConfig

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"
CORE_WEB_ASSETS = ["index.html", "styles.css", "app.js", "app-data.js", "app-render.js", "render-fragments.js"]


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
        if path == "/healthz":
            self.serve_json(
                {
                    "status": "ok",
                    "generated_at": utc_now(),
                    "has_report": self.server.report_store.has_report(),
                }
            )
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

    def serve_static(self, file_name: str) -> None:
        assets_dir = self.server.assets_dir.resolve()
        asset_path = (assets_dir / file_name).resolve()

        try:
            asset_path.relative_to(assets_dir)
        except ValueError:
            self.send_error(404, "Not Found")
            return

        if not asset_path.exists() or not asset_path.is_file():
            self.send_error(404, "Not Found")
            return

        content_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
        payload = asset_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        # 面板资源更新频繁，统一关闭缓存，避免 HTML、CSS、JS 版本错位。
        cache_control = "no-store"
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def serve_json(self, payload: dict[str, Any], status_code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
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
        raise ValueError("expose 必须是布尔值")

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
