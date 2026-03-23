import {
  formatScanMode,
  formatTime,
} from "./app-data.js";
import { renderGroupCard, renderNodeCard, renderTableRow } from "./render-fragments.js";

export function createRenderer(refs) {
  function cloneEmptyState() {
    return refs.emptyStateTemplate.content.firstElementChild.cloneNode(true);
  }

  function setText(element, value) {
    if (element) {
      element.textContent = value;
    }
  }

  function renderSummary(summary) {
    setText(refs.statOpenCount, String(summary.openCount || 0));
    setText(refs.statTrafficCount, String(summary.trafficCount || 0));
    setText(refs.statResourceCount, String(summary.resourceCount || 0));
    setText(refs.statAddressCount, String(summary.uniqueAddressCount || 0));
    setText(refs.statItemCount, String(summary.itemCount || 0));
  }

  function renderHero(payload) {
    const report = payload.latest_report;
    const cluster = report?.cluster || {};
    const execution = report?.scan_execution || {};
    const scanState = payload.scan_state || {};
    const mode = scanState.scan_in_progress ? scanState.current_mode : execution.mode || scanState.last_completed_mode;

    setText(refs.clusterConnection, cluster.connection_mode || "待执行");
    setText(refs.scanMode, formatScanMode(mode));
    setText(refs.clusterVersion, cluster.kubernetes_version || "-");
    setText(refs.generatedAt, formatTime(report?.generated_at));
    setText(refs.localNodeName, cluster.local_node_name || "未提供");
  }

  function renderError(payload) {
    const error = payload.latest_error;
    if (!error) {
      refs.errorBanner.classList.add("hidden");
      refs.errorBanner.textContent = "";
      return;
    }

    refs.errorBanner.classList.remove("hidden");
    refs.errorBanner.textContent = `最近一次扫描失败：${error.message}（${formatTime(error.updated_at)}）`;
  }

  function showPageError(message) {
    refs.errorBanner.classList.remove("hidden");
    refs.errorBanner.textContent = message;
  }

  function renderScanState(payload, scanRequestInFlight) {
    const scanState = payload.scan_state || {};
    const execution = payload.latest_report?.scan_execution || {};
    const trafficObservation = execution.traffic_observation || {};
    const notes = [];

    if (scanState.scan_in_progress) {
      notes.push(`执行中：${formatScanMode(scanState.current_mode)}`);
    } else if (scanState.last_completed_mode) {
      notes.push(`最近完成：${formatScanMode(scanState.last_completed_mode)}`);
    }

    if (scanState.pending_manual_scan) {
      notes.push("已加入刷新队列");
    }

    if (scanState.full_node_tcp_scan) {
      notes.push(`节点全端口范围：${scanState.full_node_tcp_port_spec}`);
    }

    const enabledSources = [];
    if (scanState.scan_service_external_ips) {
      enabledSources.push("ExternalIP/LoadBalancer");
    }
    if (scanState.scan_node_ports) {
      enabledSources.push("NodePort");
    }
    if (scanState.scan_host_ports) {
      enabledSources.push("HostPort");
    }
    if (scanState.scan_host_network_ports) {
      enabledSources.push("HostNetwork");
    }
    if (enabledSources.length) {
      notes.push(`归因来源：${enabledSources.join(" + ")}`);
    }

    if (trafficObservation.available) {
      notes.push(
        `被动 TCP 证据：命中 ${trafficObservation.matched_result_count || 0} 条，活跃 ${trafficObservation.active_traffic_target_count || 0} 条`
      );
    } else if (scanState.traffic_observation_enabled && trafficObservation.error) {
      notes.push(`被动 TCP 证据不可用：${trafficObservation.error}`);
    }

    refs.scanStateNote.textContent = notes.join(" · ") || "等待状态更新";

    if (scanRequestInFlight) {
      refs.scanNowButton.textContent = "提交中";
    } else if (scanState.pending_manual_scan) {
      refs.scanNowButton.textContent = "已加入队列";
    } else if (scanState.scan_in_progress) {
      refs.scanNowButton.textContent = "扫描中";
    } else {
      refs.scanNowButton.textContent = "立即刷新";
    }
    refs.scanNowButton.disabled = scanRequestInFlight;
  }

  function renderMethodology(payload) {
    const methodology = payload.methodology || payload.latest_report?.methodology || {};
    const execution = payload.latest_report?.scan_execution || {};
    const trafficObservation = execution.traffic_observation || {};

    refs.methodSteps.innerHTML = "";
    refs.methodLimits.innerHTML = "";
    refs.methodFocus.textContent = methodology.focus || "仅保留宿主机地址上的 TCP 暴露面。";

    (methodology.steps || []).forEach((step) => {
      const item = document.createElement("li");
      item.textContent = step;
      refs.methodSteps.appendChild(item);
    });

    const limits = [...(methodology.limitations || [])];
    if (trafficObservation.scope === "local_node_only") {
      limits.unshift("被动 TCP 证据仅覆盖当前运行节点。");
    }

    limits.forEach((limit) => {
      const item = document.createElement("li");
      item.textContent = limit;
      refs.methodLimits.appendChild(item);
    });
  }

  function renderNodes(nodeGroups) {
    refs.nodeSurfaceList.innerHTML = "";
    refs.nodeCountNote.textContent = `节点 ${nodeGroups.length} 个`;

    if (!nodeGroups.length) {
      refs.nodeSurfaceList.appendChild(cloneEmptyState());
      return;
    }

    nodeGroups.forEach((node) => {
      const details = document.createElement("details");
      details.className = "node-card";
      details.open = true;
      details.innerHTML = renderNodeCard(node);

      refs.nodeSurfaceList.appendChild(details);
    });
  }

  function renderGroups(groups) {
    refs.resourceGroups.innerHTML = "";
    refs.groupCountNote.textContent = `对象 ${groups.length} 个`;

    if (!groups.length) {
      refs.resourceGroups.appendChild(cloneEmptyState());
      return;
    }

    groups.forEach((group) => {
      const details = document.createElement("details");
      details.className = "result-card";
      details.open = true;
      details.innerHTML = renderGroupCard(group);

      refs.resourceGroups.appendChild(details);
    });
  }

  function renderTable(items, tableExpanded) {
    refs.resultTableBody.innerHTML = "";

    if (!items.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 7;
      cell.appendChild(cloneEmptyState());
      row.appendChild(cell);
      refs.resultTableBody.appendChild(row);
    } else {
      items.forEach((item) => {
        const row = document.createElement("tr");
        row.innerHTML = renderTableRow(item);
        refs.resultTableBody.appendChild(row);
      });
    }

    const shouldOpen = tableExpanded == null ? true : tableExpanded;
    refs.resultTableDetails.open = shouldOpen;
    refs.tableToggleNote.textContent = shouldOpen
      ? `记录 ${items.length} 条`
      : `记录 ${items.length} 条，点击展开`;
  }

  return {
    renderSummary,
    renderHero,
    renderError,
    showPageError,
    renderScanState,
    renderMethodology,
    renderNodes,
    renderGroups,
    renderTable,
  };
}
