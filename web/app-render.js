import { formatScanMode, formatTime } from "./app-data.js";
import {
  renderGroupCard,
  renderNodeCard,
  renderServiceControlNamespaceGroup,
  renderTableRow,
} from "./render-fragments.js";

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
      notes.push("扫描中");
    } else if (scanState.last_completed_mode) {
      notes.push("已完成");
    }

    if (scanState.pending_scan) {
      notes.push(
        scanState.pending_request_source === "manual"
          ? "手动已排队"
          : "变更待刷新"
      );
    }

    if (scanState.full_node_tcp_scan) {
      notes.push(`节点 ${scanState.full_node_tcp_port_spec}`);
    }

    if (trafficObservation.available) {
      notes.push(`流量 ${trafficObservation.matched_result_count || 0}/${trafficObservation.active_traffic_target_count || 0}`);
    } else if (scanState.traffic_observation_enabled && trafficObservation.error) {
      notes.push("流量不可用");
    }

    const noteText = notes.join(" · ") || "等待状态更新";
    refs.scanStateNote.textContent = noteText;
    if (refs.serviceControlScanNote) {
      refs.serviceControlScanNote.textContent = noteText;
    }

    const buttonLabel = scanRequestInFlight
      ? "提交中"
      : scanState.scan_in_progress
        ? "扫描中"
        : scanState.pending_scan && scanState.pending_request_source === "manual"
          ? "手动刷新已排队"
          : scanState.pending_scan
            ? "等待自动刷新"
            : "立即刷新";

    refs.scanNowButton.textContent = buttonLabel;
    if (refs.serviceControlRefreshButton) {
      refs.serviceControlRefreshButton.textContent = buttonLabel;
    }
    if (scanRequestInFlight) {
      refs.scanNowButton.disabled = true;
      if (refs.serviceControlRefreshButton) {
        refs.serviceControlRefreshButton.disabled = true;
      }
    } else {
      refs.scanNowButton.disabled = false;
      if (refs.serviceControlRefreshButton) {
        refs.serviceControlRefreshButton.disabled = false;
      }
    }
  }

  function renderServiceControls(serviceControls, options = {}) {
    const controlState = serviceControls || {};
    const items = controlState.items || [];
    const query = (options.query || "").trim().toLowerCase();
    const filteredItems = query
      ? items.filter((item) =>
          [item.namespace, item.service_name, ...(item.ports || []).map((port) => `${port.service_port} ${port.port_name}`)]
            .filter(Boolean)
            .join(" ")
            .toLowerCase()
            .includes(query)
        )
      : items;
    const filteredOpenPortCount = filteredItems.reduce(
      (count, item) => count + Number(item.open_port_count || 0),
      0
    );

    refs.serviceControlList.innerHTML = "";
    const groupedItems = groupServiceControls(filteredItems);
    refs.serviceControlCountNote.textContent = `命名空间 ${groupedItems.length} 个 · 服务 ${filteredItems.length} 个 · 已开放 ${filteredOpenPortCount} 个端口`;

    if (!controlState.enabled) {
      const emptyState = cloneEmptyState();
      emptyState.querySelector("h3").textContent = "功能未启用";
      emptyState.querySelector("p").textContent = "当前配置没有启用业务 Service 对外治理。";
      refs.serviceControlList.appendChild(emptyState);
      return;
    }

    if (controlState.error) {
      const emptyState = cloneEmptyState();
      emptyState.querySelector("h3").textContent = "读取失败";
      emptyState.querySelector("p").textContent = controlState.error;
      refs.serviceControlList.appendChild(emptyState);
      return;
    }

    if (!filteredItems.length) {
      refs.serviceControlList.appendChild(cloneEmptyState());
      return;
    }

    groupedItems.forEach((group) => {
      const section = document.createElement("section");
      section.innerHTML = renderServiceControlNamespaceGroup(group, {
        activeActionKey: options.activeActionKey || "",
      });
      refs.serviceControlList.appendChild(section.firstElementChild);
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
      cell.colSpan = 6;
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
    renderServiceControls,
    renderNodes,
    renderGroups,
    renderTable,
  };
}

function groupServiceControls(items) {
  const collator = new Intl.Collator("zh-CN");
  const groups = new Map();

  items
    .slice()
    .sort(
      (left, right) =>
        collator.compare(left.namespace, right.namespace) ||
        collator.compare(left.service_name, right.service_name)
    )
    .forEach((item) => {
      const groupKey = item.namespace || "-";
      if (!groups.has(groupKey)) {
        groups.set(groupKey, {
          namespace: groupKey,
          services: [],
          openPortCount: 0,
          portCount: 0,
        });
      }
      const group = groups.get(groupKey);
      group.services.push(item);
      group.openPortCount += Number(item.open_port_count || 0);
      group.portCount += Number((item.ports || []).length);
    });

  return [...groups.values()];
}
