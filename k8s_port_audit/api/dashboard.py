from __future__ import annotations

import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..report import utc_now
from ..runtime import ReportStore, ScanCoordinator
from ..settings import ScannerConfig

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
    ) -> None:
        super().__init__(server_address, DashboardRequestHandler)
        self.report_store = report_store
        self.scanner_config = scanner_config
        self.scan_coordinator = scan_coordinator
        self.assets_dir = WEB_DIR

    def dashboard_snapshot(self) -> dict[str, Any]:
        payload = self.report_store.snapshot()
        payload["scan_state"] = self.scan_coordinator.snapshot()
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
            self.server.scan_coordinator.request_scan("dashboard")
            self.serve_json(self.server.dashboard_snapshot(), status_code=202)
            return

        self.send_error(404, "Not Found")

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
        # HTML 保持 no-store，避免页面骨架与静态资源版本错位。
        cache_control = "no-store" if asset_path.name == "index.html" else "public, max-age=300"
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

    def log_message(self, format: str, *args: Any) -> None:
        return


def start_dashboard_server(
    scanner_config: ScannerConfig,
    report_store: ReportStore,
    scan_coordinator: ScanCoordinator,
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
