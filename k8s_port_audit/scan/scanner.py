from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Iterable

from ..domain import NodeCandidate, ProbeTarget, ScanRequest
from ..report import build_host_exposure_summary, build_methodology_summary, build_scan_summary, utc_now
from ..runtime.dependencies import client
from ..settings.config import ScannerConfig
from .discovery import HostExposureDiscovery
from .probe import merge_probe_results, probe_targets
from .traffic import annotate_results_with_traffic_observations, build_passive_observation_index


class HostExposureScanner:
    """执行一轮完整的宿主机暴露扫描。"""

    def __init__(self, scanner_config: ScannerConfig, connection_mode: str) -> None:
        if client is None:
            raise RuntimeError("缺少 kubernetes 依赖")

        self.scanner_config = scanner_config
        self.connection_mode = connection_mode
        self.core_api = client.CoreV1Api()
        self.version_api = client.VersionApi()
        self.local_node_name = os.getenv("MY_NODE_NAME") or None
        self.discovery = HostExposureDiscovery(self.core_api, scanner_config)

    def get_cluster_info(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "connection_mode": self.connection_mode,
            "local_node_name": self.local_node_name,
        }

        try:
            version = self.version_api.get_code()
        except Exception as exc:
            payload["version_error"] = str(exc)
            return payload

        payload.update(
            {
                "kubernetes_version": getattr(version, "git_version", None),
                "platform": getattr(version, "platform", None),
                "compiler": getattr(version, "compiler", None),
            }
        )
        return payload

    def iter_full_node_targets(self, node_candidates: list[NodeCandidate]) -> Iterable[ProbeTarget]:
        for node in node_candidates:
            # 节点全端口扫描用于发现真实开放端口；Kubernetes 元数据用于归因。
            source = {
                "kind": "node",
                "namespace": "-",
                "name": node.name,
                "node_name": node.name,
                "address_type": node.address_type,
                "reason": "node_full_scan",
            }
            for port in self.scanner_config.full_node_tcp_ports:
                yield ProbeTarget(address=node.address, port=port, sources=[source.copy()])

    @staticmethod
    def new_traffic_observation_summary(
        scanner_config: ScannerConfig,
        local_node_name: str | None,
    ) -> dict[str, Any]:
        return {
            "enabled": scanner_config.traffic_observation_enabled,
            "available": False,
            "scope": "disabled",
            "host_proc_root": scanner_config.traffic_observation_host_proc_root,
            "local_node_name": local_node_name,
            "raw_entry_count": 0,
            "matched_target_count": 0,
            "listener_target_count": 0,
            "active_traffic_target_count": 0,
            "matched_result_count": 0,
            "error": None,
        }

    async def collect_targeted_results(self, discovery_snapshot: Any) -> list[dict[str, Any]]:
        return await probe_targets(
            discovery_snapshot.targets,
            timeout_seconds=self.scanner_config.timeout_seconds,
            concurrency=self.scanner_config.concurrency,
        )

    async def collect_full_node_results(self, discovery_snapshot: Any) -> list[dict[str, Any]]:
        if not self.scanner_config.full_node_tcp_scan:
            return []

        discovery_snapshot.inventory["full_node_scan_nodes"] = len(discovery_snapshot.node_candidates)
        discovery_snapshot.inventory["full_node_scan_ports_per_node"] = len(
            self.scanner_config.full_node_tcp_ports
        )
        discovery_snapshot.inventory["full_node_scan_targets"] = (
            len(discovery_snapshot.node_candidates) * len(self.scanner_config.full_node_tcp_ports)
        )
        return await probe_targets(
            self.iter_full_node_targets(discovery_snapshot.node_candidates),
            timeout_seconds=self.scanner_config.timeout_seconds,
            concurrency=self.scanner_config.concurrency,
            # 节点全扫描量较大，仅保留 open 结果以控制报告体积。
            keep_result=lambda result: result["status"] == "open",
        )

    def annotate_with_traffic_observations(
        self,
        results: list[dict[str, Any]],
        node_candidates: list[NodeCandidate],
    ) -> dict[str, Any]:
        summary = self.new_traffic_observation_summary(self.scanner_config, self.local_node_name)
        if not self.scanner_config.traffic_observation_enabled:
            return summary

        observation_map, summary = build_passive_observation_index(
            host_proc_root=Path(self.scanner_config.traffic_observation_host_proc_root).resolve(),
            node_candidates=node_candidates,
            local_node_name=self.local_node_name,
        )
        summary["enabled"] = True
        summary["matched_result_count"] = annotate_results_with_traffic_observations(
            results,
            observation_map,
        )
        return summary

    def build_scan_execution(
        self,
        scan_request: ScanRequest,
        full_node_results: list[dict[str, Any]],
        traffic_observation_summary: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "mode": "host_exposure",
            "refresh_scope": "full" if scan_request.full_scan else "partial",
            "request_source": scan_request.source,
            "request_reason": scan_request.reason,
            "partial_service_ref_count": len(scan_request.service_refs),
            "partial_pod_ref_count": len(scan_request.pod_refs),
            "partial_node_port_ref_count": len(scan_request.node_port_refs),
            "full_node_tcp_scan": self.scanner_config.full_node_tcp_scan,
            "full_node_tcp_port_spec": self.scanner_config.full_node_tcp_port_spec,
            "full_node_tcp_port_count": len(self.scanner_config.full_node_tcp_ports),
            "full_node_records_open_only": True,
            "full_node_open_result_count": len(full_node_results),
            "traffic_observation": traffic_observation_summary,
        }

    @staticmethod
    def source_matches_request(source: dict[str, Any], scan_request: ScanRequest) -> bool:
        namespace = source.get("namespace")
        name = source.get("name")
        if source.get("kind") == "service":
            service_names = {
                value
                for value in (
                    name,
                    source.get("service_name"),
                    source.get("actual_service_name"),
                )
                if value
            }
            if any((namespace, service_name) in scan_request.service_refs for service_name in service_names):
                return True
        if source.get("kind") == "pod" and (namespace, name) in scan_request.pod_refs:
            return True
        return False

    def strip_request_sources(
        self,
        previous_results: list[dict[str, Any]],
        scan_request: ScanRequest,
        refreshed_node_targets: set[tuple[str, int]] | None = None,
    ) -> list[dict[str, Any]]:
        retained_results: list[dict[str, Any]] = []
        refreshed_node_targets = refreshed_node_targets or set()

        for result in previous_results:
            result_key = (result["address"], result["port"])
            remaining_sources = [
                copy.deepcopy(source)
                for source in result.get("sources", [])
                if not self.source_matches_request(source, scan_request)
                and not (
                    result_key in refreshed_node_targets and source.get("reason") == "node_full_scan"
                )
            ]
            if not remaining_sources:
                continue

            retained_result = copy.deepcopy(result)
            retained_result["sources"] = remaining_sources
            retained_results.append(retained_result)

        return retained_results

    @staticmethod
    def drop_stale_observation_fields(results: list[dict[str, Any]]) -> None:
        for result in results:
            for field_name in (
                "traffic_observed",
                "listener_observed",
                "observed_states",
                "observed_sample_count",
            ):
                result.pop(field_name, None)

    def merge_incremental_results(
        self,
        previous_results: list[dict[str, Any]],
        partial_results: list[dict[str, Any]],
        scan_request: ScanRequest,
    ) -> list[dict[str, Any]]:
        refreshed_node_targets = {
            (result["address"], result["port"])
            for result in partial_results
            if any(source.get("reason") == "node_full_scan" for source in result.get("sources", []))
        }
        retained_results = self.strip_request_sources(
            previous_results,
            scan_request,
            refreshed_node_targets=refreshed_node_targets,
        )
        retained_status_by_target = {
            (result["address"], result["port"]): result.get("status")
            for result in retained_results
        }

        normalized_partial_results: list[dict[str, Any]] = []
        for result in partial_results:
            target_key = (result["address"], result["port"])
            retained_status = retained_status_by_target.get(target_key)
            node_only_refresh = (
                target_key in refreshed_node_targets
                and all(source.get("reason") == "node_full_scan" for source in result.get("sources", []))
            )

            # 业务治理导致的 NodePort 收回后，定点补扫会返回 closed/timeout。
            # 这类结果只用于把旧的 open 记录清掉，不应该继续占据面板里的“记录数”。
            if node_only_refresh and result.get("status") != "open":
                continue

            # 事件局部刷新只负责更新相关对象的归因路径；如果同一地址端口仍被别的路径探测为 open，
            # 不再把本次 closed/timeout 结果重新挂回去，避免页面上出现“节点仍开放，但对象归因还停留在旧路径”。
            if (
                target_key not in refreshed_node_targets
                and retained_status == "open"
                and result.get("status") != "open"
            ):
                continue

            normalized_partial_results.append(result)

        return merge_probe_results(retained_results, normalized_partial_results)

    def build_report(
        self,
        discovery_snapshot: Any,
        results: list[dict[str, Any]],
        full_node_results: list[dict[str, Any]],
        traffic_observation_summary: dict[str, Any],
        scan_request: ScanRequest,
        inventory_override: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        inventory = copy.deepcopy(inventory_override or discovery_snapshot.inventory)
        inventory["unique_targets"] = len(results)
        summary = build_scan_summary(inventory, results)
        external_exposure_summary = build_host_exposure_summary(
            results,
            node_candidates=discovery_snapshot.node_candidates,
        )

        return {
            "generated_at": utc_now(),
            "cluster": self.get_cluster_info(),
            "scanner_config": self.scanner_config.to_report_dict(),
            "scan_execution": self.build_scan_execution(
                scan_request,
                full_node_results,
                traffic_observation_summary,
            ),
            "summary": summary,
            "external_exposure_summary": external_exposure_summary,
            "traffic_observation_summary": traffic_observation_summary,
            "methodology": build_methodology_summary(),
            "results": results,
        }

    async def scan_once(self) -> dict[str, Any]:
        scan_request = ScanRequest(source="startup", reason="启动扫描", full_scan=True)
        discovery_snapshot = self.discovery.discover()
        targeted_results = await self.collect_targeted_results(discovery_snapshot)
        full_node_results = await self.collect_full_node_results(discovery_snapshot)

        # targeted_results 提供路径信息，full_node_results 提供真实开放端口补充。
        results = merge_probe_results(targeted_results, full_node_results)
        self.drop_stale_observation_fields(results)
        traffic_observation_summary = self.annotate_with_traffic_observations(
            results,
            discovery_snapshot.node_candidates,
        )
        return self.build_report(
            discovery_snapshot,
            results,
            full_node_results,
            traffic_observation_summary,
            scan_request,
        )

    async def scan_for_request(
        self,
        scan_request: ScanRequest,
        previous_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if scan_request.full_scan or previous_report is None:
            discovery_snapshot = self.discovery.discover()
            targeted_results = await self.collect_targeted_results(discovery_snapshot)
            full_node_results = await self.collect_full_node_results(discovery_snapshot)
            results = merge_probe_results(targeted_results, full_node_results)
            self.drop_stale_observation_fields(results)
            traffic_observation_summary = self.annotate_with_traffic_observations(
                results,
                discovery_snapshot.node_candidates,
            )
            return self.build_report(
                discovery_snapshot,
                results,
                full_node_results,
                traffic_observation_summary,
                scan_request,
            )

        discovery_snapshot = self.discovery.discover(
            service_refs=scan_request.service_refs,
            pod_refs=scan_request.pod_refs,
            node_port_refs=scan_request.node_port_refs,
        )
        partial_results = await self.collect_targeted_results(discovery_snapshot)
        previous_results = copy.deepcopy(previous_report.get("results") or [])
        results = self.merge_incremental_results(previous_results, partial_results, scan_request)
        self.drop_stale_observation_fields(results)
        traffic_observation_summary = self.annotate_with_traffic_observations(
            results,
            discovery_snapshot.node_candidates,
        )
        previous_inventory = copy.deepcopy(previous_report.get("summary", {}).get("inventory") or {})
        return self.build_report(
            discovery_snapshot,
            results,
            [],
            traffic_observation_summary,
            scan_request,
            inventory_override=previous_inventory or None,
        )
