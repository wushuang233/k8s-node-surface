import { buildExposureState, emptyState, filterState } from "./app-data.js";
import { createRenderer } from "./app-render.js";

const refs = {
  statusFilter: document.querySelector("#status-filter"),
  typeFilter: document.querySelector("#type-filter"),
  searchInput: document.querySelector("#search-input"),
  emptyStateTemplate: document.querySelector("#empty-state-template"),
  scanNowButton: document.querySelector("#scan-now-button"),
  scanStateNote: document.querySelector("#scan-state-note"),
  errorBanner: document.querySelector("#error-banner"),
  clusterConnection: document.querySelector("#cluster-connection"),
  scanMode: document.querySelector("#scan-mode"),
  clusterVersion: document.querySelector("#cluster-version"),
  generatedAt: document.querySelector("#generated-at"),
  localNodeName: document.querySelector("#local-node-name"),
  statOpenCount: document.querySelector("#stat-open-count"),
  statTrafficCount: document.querySelector("#stat-traffic-count"),
  statResourceCount: document.querySelector("#stat-resource-count"),
  statAddressCount: document.querySelector("#stat-address-count"),
  statItemCount: document.querySelector("#stat-item-count"),
  methodFocus: document.querySelector("#method-focus"),
  methodSteps: document.querySelector("#method-steps"),
  methodLimits: document.querySelector("#method-limits"),
  nodeCountNote: document.querySelector("#node-count-note"),
  nodeSurfaceList: document.querySelector("#node-surface-list"),
  groupCountNote: document.querySelector("#group-count-note"),
  resourceGroups: document.querySelector("#resource-groups"),
  resultTableBody: document.querySelector("#result-table-body"),
  resultTableDetails: document.querySelector("#result-table-details"),
  tableToggleNote: document.querySelector("#table-toggle-note"),
};

const renderer = createRenderer(refs);

const state = {
  dashboardPayload: null,
  exposureState: emptyState(),
  refreshTimer: null,
  scanRequestInFlight: false,
  tableExpanded: true,
};

function readFilters() {
  return {
    status: refs.statusFilter.value,
    typeValue: refs.typeFilter.value,
    query: refs.searchInput.value.trim().toLowerCase(),
  };
}

function renderTypeFilter(viewState) {
  const currentValue = refs.typeFilter.value;
  refs.typeFilter.innerHTML = "";

  const allOption = document.createElement("option");
  allOption.value = "all";
  allOption.textContent = "全部";
  refs.typeFilter.appendChild(allOption);

  viewState.filterOptions.forEach((option) => {
    const node = document.createElement("option");
    node.value = option.value;
    node.textContent = option.label;
    refs.typeFilter.appendChild(node);
  });

  const optionValues = new Set(["all", ...viewState.filterOptions.map((item) => item.value)]);
  refs.typeFilter.value = optionValues.has(currentValue) ? currentValue : "all";
}

function renderPage() {
  if (!state.dashboardPayload) {
    return;
  }

  const filteredState = filterState(state.exposureState, readFilters());
  renderer.renderHero(state.dashboardPayload);
  renderer.renderError(state.dashboardPayload);
  renderer.renderScanState(state.dashboardPayload, state.scanRequestInFlight);
  renderer.renderMethodology(state.dashboardPayload);
  renderTypeFilter(state.exposureState);
  renderer.renderSummary(filteredState.summary);
  renderer.renderNodes(filteredState.nodeGroups);
  renderer.renderGroups(filteredState.groups);
  renderer.renderTable(filteredState.items, state.tableExpanded);
}

async function fetchDashboard() {
  const response = await fetch("/api/dashboard", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`dashboard request failed: ${response.status}`);
  }

  const payload = await response.json();
  state.dashboardPayload = payload;
  state.exposureState = buildExposureState(payload.external_exposure_summary || {});
  renderPage();

  if (!state.refreshTimer) {
    // 刷新周期以服务端配置为准。
    const refreshSeconds = payload.service?.refresh_seconds || 15;
    state.refreshTimer = setInterval(fetchDashboard, refreshSeconds * 1000);
  }
}

async function triggerScan() {
  if (state.scanRequestInFlight) {
    return;
  }

  state.scanRequestInFlight = true;
  renderPage();

  try {
    const response = await fetch("/api/scan", {
      method: "POST",
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`scan request failed: ${response.status}`);
    }

    state.dashboardPayload = await response.json();
    state.exposureState = buildExposureState(state.dashboardPayload.external_exposure_summary || {});
    renderPage();
    window.setTimeout(() => {
      fetchDashboard().catch((error) => {
        renderer.showPageError(`刷新扫描状态失败: ${error.message}`);
      });
    }, 800);
  } catch (error) {
    renderer.showPageError(`触发扫描失败: ${error.message}`);
  } finally {
    state.scanRequestInFlight = false;
    renderPage();
  }
}

function rerender() {
  renderPage();
}

refs.statusFilter.addEventListener("change", rerender);
refs.typeFilter.addEventListener("change", rerender);
refs.searchInput.addEventListener("input", rerender);
refs.scanNowButton.addEventListener("click", triggerScan);
refs.resultTableDetails.addEventListener("toggle", () => {
  state.tableExpanded = refs.resultTableDetails.open;
});

fetchDashboard().catch((error) => {
  renderer.showPageError(`页面初始化失败: ${error.message}`);
});
