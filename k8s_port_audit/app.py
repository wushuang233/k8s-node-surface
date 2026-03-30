from __future__ import annotations

"""程序入口与扫描调度。"""

import argparse
import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable

from .api.dashboard import start_dashboard_server, stop_dashboard_server
from .control import ServiceExposureController
from .domain import ScanRequest
from .report.reporting import emit_report
from .runtime.dependencies import ApiException, load_kubernetes_config
from .runtime.state import ReportStore, ScanCoordinator
from .runtime.watcher import KubernetesEventWatcher
from .scan.scanner import HostExposureScanner
from .settings.config import ScannerConfig, load_scanner_config


def is_transient_kubernetes_api_error(error: Exception) -> bool:
    if isinstance(error, ApiException) and getattr(error, "status", None) in {429, 500, 502, 503, 504}:
        return True

    message = str(error).lower()
    transient_markers = (
        "maxretryerror",
        "newconnectionerror",
        "failed to establish a new connection",
        "connection refused",
        "connection aborted",
        "temporarily unavailable",
        "temporary failure",
        "timed out",
        "tls handshake timeout",
    )
    return any(marker in message for marker in transient_markers)


async def scan_once_with_retries(
    scan_callable: Callable[[], Awaitable[dict[str, Any]]],
    report_store: ReportStore,
    retry_label: str,
) -> dict[str, Any]:
    # 将启动阶段的短暂 API 抖动与持续性配置错误区分处理。
    max_attempts = 8
    base_delay_seconds = 2.0

    for attempt in range(1, max_attempts + 1):
        try:
            return await scan_callable()
        except Exception as exc:
            if not is_transient_kubernetes_api_error(exc) or attempt >= max_attempts:
                raise

            delay_seconds = min(base_delay_seconds * (2 ** (attempt - 1)), 20.0)
            message = (
                f"{retry_label}前连接 Kubernetes API 失败，{delay_seconds:.0f} 秒后自动重试 "
                f"({attempt}/{max_attempts})：{type(exc).__name__}: {exc}"
            )
            report_store.update_error(message)
            print(message, flush=True)
            await asyncio.sleep(delay_seconds)

    raise RuntimeError("扫描重试逻辑异常退出")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="扫描 Kubernetes 中暴露到宿主机地址的 TCP 端口"
    )
    parser.add_argument(
        "--config",
        default="config/scanner-config.yaml",
        help="扫描配置文件路径，默认 config/scanner-config.yaml",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="强制只执行一次扫描，忽略配置文件里的 interval_seconds",
    )
    parser.add_argument(
        "--output",
        help="覆盖配置文件中的 output_path，把 JSON 结果写到指定文件",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="禁用内置前端面板",
    )
    parser.add_argument(
        "--web-host",
        help="覆盖配置文件中的 web.host",
    )
    parser.add_argument(
        "--web-port",
        type=int,
        help="覆盖配置文件中的 web.port",
    )
    return parser.parse_args()


async def run_scan_loop(
    scanner: HostExposureScanner,
    scanner_config: ScannerConfig,
    report_store: ReportStore,
    scan_coordinator: ScanCoordinator,
) -> int:
    next_request = ScanRequest(source="startup", reason="启动扫描", full_scan=True)

    while True:
        scan_coordinator.mark_scan_started()
        try:
            previous_report = report_store.latest_report()
            report = await scan_once_with_retries(
                lambda: scanner.scan_for_request(next_request, previous_report),
                report_store,
                retry_label="扫描",
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            report_store.update_error(message)
            print(f"扫描失败: {message}", flush=True)
            if scanner_config.interval_seconds == 0 and not scanner_config.watch_kubernetes_events:
                raise
        else:
            report_store.update_report(report)
            emit_report(report, scanner_config.output_path, scanner_config.pretty_json)
            if scanner_config.interval_seconds == 0 and not scanner_config.watch_kubernetes_events:
                return 0
        finally:
            scan_coordinator.mark_scan_finished()

        # 周期扫描、手动刷新与 Kubernetes 事件触发共用一个等待入口，避免状态竞争。
        refresh_requested = await scan_coordinator.wait_for_next_scan(
            scanner_config.interval_seconds,
            allow_event_only=scanner_config.watch_kubernetes_events,
        )
        if refresh_requested is None:
            next_request = ScanRequest(source="interval", reason="定时刷新", full_scan=True)
            continue

        next_request = refresh_requested
        if next_request.full_scan:
            print("收到新的完整刷新请求，立即开始下一轮扫描。", flush=True)
        else:
            print("收到新的局部刷新请求，立即更新受影响的暴露面。", flush=True)


async def run() -> int:
    args = parse_args()
    scanner_config = load_scanner_config(Path(args.config))
    if args.once:
        scanner_config.interval_seconds = 0
    if args.output:
        scanner_config.output_path = args.output
    if args.no_web:
        scanner_config.web_enabled = False
    if args.web_host:
        scanner_config.web_host = args.web_host
    if args.web_port:
        scanner_config.web_port = args.web_port
    scanner_config.validate()

    connection_mode = load_kubernetes_config()
    scanner = HostExposureScanner(scanner_config, connection_mode)
    report_store = ReportStore(scanner_config)
    scan_coordinator = ScanCoordinator(scanner_config)
    scan_coordinator.bind_loop(asyncio.get_running_loop())
    service_controller = (
        ServiceExposureController(scanner_config) if scanner_config.service_control_enabled else None
    )
    dashboard_server = start_dashboard_server(
        scanner_config,
        report_store,
        scan_coordinator,
        service_controller=service_controller,
    )
    event_watcher = KubernetesEventWatcher(scanner_config, scan_coordinator)
    event_watcher.start()

    try:
        return await run_scan_loop(scanner, scanner_config, report_store, scan_coordinator)
    finally:
        event_watcher.stop()
        stop_dashboard_server(dashboard_server)


def main() -> int:
    try:
        return asyncio.run(run())
    except FileNotFoundError as exc:
        print(f"配置错误: {exc}")
        return 2
    except ValueError as exc:
        print(f"参数错误: {exc}")
        return 2
    except RuntimeError as exc:
        print(f"运行错误: {exc}")
        return 2
    except ApiException as exc:
        print(f"Kubernetes API 错误: status={getattr(exc, 'status', 'unknown')} detail={exc}")
        return 3
    except KeyboardInterrupt:
        print("\n扫描已取消。")
        return 130
    except Exception as exc:
        print(f"未预期错误: {exc}")
        return 3
