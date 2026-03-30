from __future__ import annotations

import asyncio
import copy
import threading
import time
from typing import Any

from ..domain import ScanRequest
from ..report import utc_now
from ..settings.config import ScannerConfig


class ReportStore:
    """同时保存完整报告和轻量面板快照。

    浏览器轮询只需要摘要和主面板数据，不需要整份 results。
    """

    def __init__(self, scanner_config: ScannerConfig) -> None:
        self.scanner_config = scanner_config
        self.started_at = utc_now()
        self._latest_report: dict[str, Any] | None = None
        self._latest_dashboard_report: dict[str, Any] | None = None
        self._latest_error: dict[str, Any] | None = None
        self._lock = threading.Lock()

    def update_report(self, report: dict[str, Any]) -> None:
        dashboard_report = {
            "generated_at": report.get("generated_at"),
            "cluster": copy.deepcopy(report.get("cluster")),
            "scanner_config": copy.deepcopy(report.get("scanner_config")),
            "scan_execution": copy.deepcopy(report.get("scan_execution")),
            "summary": copy.deepcopy(report.get("summary")),
            "external_exposure_summary": copy.deepcopy(report.get("external_exposure_summary")),
            "methodology": copy.deepcopy(report.get("methodology")),
        }
        with self._lock:
            self._latest_report = copy.deepcopy(report)
            self._latest_dashboard_report = dashboard_report
            self._latest_error = None

    def update_error(self, message: str) -> None:
        with self._lock:
            self._latest_error = {
                "message": message,
                "updated_at": utc_now(),
            }

    def latest_report(self) -> dict[str, Any] | None:
        with self._lock:
            return copy.deepcopy(self._latest_report)

    def has_report(self) -> bool:
        with self._lock:
            return self._latest_report is not None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latest_report = copy.deepcopy(self._latest_dashboard_report)
            latest_error = copy.deepcopy(self._latest_error)

        return {
            "service": {
                "started_at": self.started_at,
                "web_enabled": self.scanner_config.web_enabled,
                "web_host": self.scanner_config.web_host,
                "web_port": self.scanner_config.web_port,
                "refresh_seconds": self.scanner_config.web_refresh_seconds,
                "has_report": latest_report is not None,
            },
            "latest_error": latest_error,
            "latest_report": latest_report,
            "external_exposure_summary": (
                latest_report.get("external_exposure_summary") if latest_report else None
            ),
            "methodology": latest_report.get("methodology") if latest_report else None,
        }


class ScanCoordinator:
    """协调完整扫描与事件触发的局部刷新请求。"""

    def __init__(self, scanner_config: ScannerConfig) -> None:
        self.scanner_config = scanner_config
        self._lock = threading.Lock()
        self._pending_request: ScanRequest | None = None
        self._scan_in_progress = False
        self._last_scan_started_at: str | None = None
        self._last_scan_completed_at: str | None = None
        self._last_request_at: str | None = None
        self._last_request_source: str | None = None
        self._last_request_reason: str | None = None
        self._last_request_monotonic = 0.0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._event: asyncio.Event | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._event = asyncio.Event()

    def request_scan(
        self,
        source: str = "manual",
        reason: str | None = None,
        *,
        full_scan: bool = True,
        service_refs: set[tuple[str, str]] | None = None,
        pod_refs: set[tuple[str, str]] | None = None,
        node_port_refs: set[int] | None = None,
    ) -> None:
        request = ScanRequest(
            source=source,
            reason=reason,
            full_scan=full_scan,
            service_refs=set(service_refs or ()),
            pod_refs=set(pod_refs or ()),
            node_port_refs={int(port) for port in (node_port_refs or ()) if int(port) > 0},
        )

        with self._lock:
            self._pending_request = (
                request
                if self._pending_request is None
                else self._pending_request.merged_with(request)
            )
            self._last_request_at = utc_now()
            self._last_request_source = source
            self._last_request_reason = reason
            self._last_request_monotonic = time.monotonic()

        if self._loop is not None and self._event is not None:
            self._loop.call_soon_threadsafe(self._event.set)

    def mark_scan_started(self) -> None:
        with self._lock:
            self._scan_in_progress = True
            self._last_scan_started_at = utc_now()

    def mark_scan_finished(self) -> None:
        with self._lock:
            self._scan_in_progress = False
            self._last_scan_completed_at = utc_now()

    async def wait_for_next_scan(
        self,
        interval_seconds: int,
        allow_event_only: bool = False,
    ) -> ScanRequest | None:
        event = self._event
        if event is None:
            if interval_seconds <= 0:
                return None
            await asyncio.sleep(interval_seconds)
            return None

        if interval_seconds <= 0 and not allow_event_only:
            return None

        while True:
            with self._lock:
                pending_request = self._pending_request
                last_request_monotonic = self._last_request_monotonic

            if pending_request is not None:
                remaining_debounce = 0.0
                if pending_request.source == "k8s_watch":
                    remaining_debounce = self.scanner_config.event_debounce_seconds - (
                        time.monotonic() - last_request_monotonic
                    )

                if remaining_debounce > 0:
                    event.clear()
                    try:
                        await asyncio.wait_for(event.wait(), timeout=remaining_debounce)
                    except asyncio.TimeoutError:
                        pass
                    continue

                with self._lock:
                    pending_request = self._pending_request
                    self._pending_request = None
                return pending_request

            if interval_seconds <= 0:
                event.clear()
                await event.wait()
                continue

            event.clear()
            try:
                await asyncio.wait_for(event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                return None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            pending_request = copy.deepcopy(self._pending_request)
            return {
                "scan_in_progress": self._scan_in_progress,
                "pending_scan": pending_request is not None,
                "pending_request_source": pending_request.source if pending_request else None,
                "pending_request_reason": pending_request.reason if pending_request else None,
                "pending_request_full_scan": pending_request.full_scan if pending_request else False,
                "pending_service_ref_count": len(pending_request.service_refs) if pending_request else 0,
                "pending_pod_ref_count": len(pending_request.pod_refs) if pending_request else 0,
                "pending_node_port_ref_count": len(pending_request.node_port_refs) if pending_request else 0,
                "current_mode": "host_exposure" if self._scan_in_progress else None,
                "last_completed_mode": "host_exposure" if self._last_scan_completed_at else None,
                "last_scan_started_at": self._last_scan_started_at,
                "last_scan_completed_at": self._last_scan_completed_at,
                "last_request_at": self._last_request_at,
                "last_request_source": self._last_request_source,
                "last_request_reason": self._last_request_reason,
                "full_node_tcp_scan": self.scanner_config.full_node_tcp_scan,
                "full_node_tcp_port_spec": self.scanner_config.full_node_tcp_port_spec,
                "full_node_tcp_port_count": len(self.scanner_config.full_node_tcp_ports),
                "watch_kubernetes_events": self.scanner_config.watch_kubernetes_events,
                "event_watch_timeout_seconds": self.scanner_config.event_watch_timeout_seconds,
                "event_debounce_seconds": self.scanner_config.event_debounce_seconds,
                "scan_service_external_ips": self.scanner_config.scan_service_external_ips,
                "scan_node_ports": self.scanner_config.scan_node_ports,
                "scan_host_ports": self.scanner_config.scan_host_ports,
                "scan_host_network_ports": self.scanner_config.scan_host_network_ports,
                "traffic_observation_enabled": self.scanner_config.traffic_observation_enabled,
                "traffic_observation_host_proc_root": self.scanner_config.traffic_observation_host_proc_root,
            }
