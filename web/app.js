import {
  applyPlatformVisibility,
  buildExposureState,
  emptyState,
  filterState,
  listTabs,
  typeFilterOptions,
} from "./app-data.js";
import { createRenderer } from "./app-render.js";

const refs = {
  statsPanel: document.querySelector("#stats-panel"),
  filterControls: document.querySelector("#filter-controls"),
  statusFilter: document.querySelector("#status-filter"),
  typeFilter: document.querySelector("#type-filter"),
  searchInput: document.querySelector("#search-input"),
  platformToggleButton: document.querySelector("#platform-toggle-button"),
  emptyStateTemplate: document.querySelector("#empty-state-template"),
  scanNowButton: document.querySelector("#scan-now-button"),
  scanStateNote: document.querySelector("#scan-state-note"),
  serviceControlPanel: document.querySelector("#service-control-panel"),
  serviceControlCountNote: document.querySelector("#service-control-count-note"),
  serviceControlSearchInput: document.querySelector("#service-control-search-input"),
  serviceControlRefreshButton: document.querySelector("#service-control-refresh-button"),
  serviceControlScanNote: document.querySelector("#service-control-scan-note"),
  serviceControlList: document.querySelector("#service-control-list"),
  tabButtons: Array.from(document.querySelectorAll(".view-tab")),
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
  nodeCountNote: document.querySelector("#node-count-note"),
  nodeSurfaceList: document.querySelector("#node-surface-list"),
  groupCountNote: document.querySelector("#group-count-note"),
  resourceGroups: document.querySelector("#resource-groups"),
  exposureSections: document.querySelector("#exposure-sections"),
  resultTableBody: document.querySelector("#result-table-body"),
  resultTableDetails: document.querySelector("#result-table-details"),
  tableToggleNote: document.querySelector("#table-toggle-note"),
};

const renderer = createRenderer(refs);

const state = {
  dashboardPayload: null,
  exposureState: emptyState(),
  refreshTimer: null,
  followupRefreshTimer: null,
  scanRequestInFlight: false,
  serviceControlActionKey: "",
  tableExpanded: true,
  activeTab: "all",
  showPlatformComponents: true,
  serviceControlQuery: "",
};

function readFilters() {
  return {
    status: refs.statusFilter.value,
    typeValue: refs.typeFilter.value,
    query: refs.searchInput.value.trim().toLowerCase(),
  };
}

function currentBaseState() {
  return applyPlatformVisibility(state.exposureState, state.showPlatformComponents);
}

function currentFilteredState() {
  const filters = readFilters();
  return {
    filters,
    baseState: currentBaseState(),
  };
}

function clearFollowupRefresh() {
  if (state.followupRefreshTimer) {
    window.clearTimeout(state.followupRefreshTimer);
    state.followupRefreshTimer = null;
  }
}

function renderTypeFilter(viewState, activeTab) {
  const currentValue = refs.typeFilter.value;
  const options = typeFilterOptions(viewState, activeTab);
  refs.typeFilter.innerHTML = "";

  const allOption = document.createElement("option");
  allOption.value = "all";
  allOption.textContent = "全部";
  refs.typeFilter.appendChild(allOption);

  options.forEach((option) => {
    const node = document.createElement("option");
    node.value = option.value;
    node.textContent = option.label;
    refs.typeFilter.appendChild(node);
  });

  const optionValues = new Set(["all", ...options.map((item) => item.value)]);
  refs.typeFilter.value = optionValues.has(currentValue) ? currentValue : "all";
}

function renderTabs(viewState) {
  const tabs = new Map(listTabs(viewState).map((tab) => [tab.id, tab]));
  tabs.set("controls", {
    id: "controls",
    count: state.dashboardPayload?.service_controls?.service_count || 0,
  });
  refs.tabButtons.forEach((button) => {
    const tabId = button.dataset.tab || "all";
    const tab = tabs.get(tabId);
    const countNode = button.querySelector("strong");
    if (countNode && tab) {
      countNode.textContent = String(tab.count);
    }
    button.classList.toggle("is-active", state.activeTab === tabId);
  });
}

function renderPlatformToggle() {
  const hidingEnabled = !state.showPlatformComponents;
  refs.platformToggleButton.classList.toggle("is-active", hidingEnabled);
  refs.platformToggleButton.setAttribute("aria-pressed", String(hidingEnabled));
  refs.platformToggleButton.textContent = hidingEnabled
    ? "隐藏 K8s 系统组件：开"
    : "隐藏 K8s 系统组件：关";
}

function renderPage() {
  if (!state.dashboardPayload) {
    return;
  }

  const { filters, baseState } = currentFilteredState();
  const controlsTabActive = state.activeTab === "controls";
  const filteredState = controlsTabActive
    ? baseState
    : filterState(baseState, filters, state.activeTab, {
        showEmptyNodesOnAll: state.showPlatformComponents,
      });

  renderer.renderHero(state.dashboardPayload);
  renderer.renderError(state.dashboardPayload);
  renderer.renderScanState(state.dashboardPayload, state.scanRequestInFlight);
  renderer.renderServiceControls(state.dashboardPayload.service_controls, {
    query: state.serviceControlQuery,
    activeActionKey: state.serviceControlActionKey,
  });
  refs.statsPanel.classList.toggle("hidden", controlsTabActive);
  refs.filterControls.classList.toggle("hidden", controlsTabActive);
  refs.serviceControlPanel.classList.toggle("hidden", !controlsTabActive);
  refs.exposureSections.classList.toggle("hidden", controlsTabActive);
  refs.statusFilter.disabled = controlsTabActive;
  refs.typeFilter.disabled = controlsTabActive;
  refs.serviceControlSearchInput.disabled = !controlsTabActive;
  refs.serviceControlRefreshButton.disabled = !controlsTabActive || state.scanRequestInFlight;
  renderTypeFilter(baseState, state.activeTab);
  renderTabs(baseState);
  renderPlatformToggle();
  renderer.renderSummary(filteredState.summary);
  renderer.renderNodes(filteredState.nodeGroups);
  renderer.renderGroups(filteredState.groups);
  renderer.renderTable(filteredState.items, state.tableExpanded);
}

function applyDashboardPayload(payload) {
  state.dashboardPayload = payload;
  state.exposureState = buildExposureState(payload.external_exposure_summary || {});
  ensureRefreshTimer(payload);
}

function ensureRefreshTimer(payload) {
  if (state.refreshTimer) {
    return;
  }

  const refreshSeconds = payload.service?.refresh_seconds || 15;
  state.refreshTimer = setInterval(() => {
    fetchDashboard().catch((error) => {
      renderer.showPageError(`刷新页面失败: ${error.message}`);
    });
  }, refreshSeconds * 1000);
}

async function fetchJson(url, init, fallbackLabel) {
  const response = await fetch(url, init);
  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    payload = null;
  }
  if (!response.ok) {
    const errorText = payload?.error || `${fallbackLabel}: ${response.status}`;
    throw new Error(errorText);
  }
  return payload;
}

function scheduleDashboardRefresh(options = {}) {
  const {
    delayMs = 1000,
    errorLabel = "刷新页面失败",
    maxAttempts = 20,
    attempt = 1,
  } = options;

  clearFollowupRefresh();
  state.followupRefreshTimer = window.setTimeout(async () => {
    try {
      const payload = await fetchJson(
        "/api/dashboard",
        { cache: "no-store" },
        "dashboard request failed"
      );
      applyDashboardPayload(payload);
      renderPage();

      const scanState = payload.scan_state || {};
      if ((scanState.scan_in_progress || scanState.pending_scan) && attempt < maxAttempts) {
        scheduleDashboardRefresh({
          delayMs: 1200,
          errorLabel,
          maxAttempts,
          attempt: attempt + 1,
        });
      } else {
        clearFollowupRefresh();
      }
    } catch (error) {
      clearFollowupRefresh();
      renderer.showPageError(`${errorLabel}: ${error.message}`);
    }
  }, delayMs);
}

async function fetchDashboard() {
  const payload = await fetchJson(
    "/api/dashboard",
    { cache: "no-store" },
    "dashboard request failed"
  );
  applyDashboardPayload(payload);
  renderPage();
}

async function triggerScan() {
  if (state.scanRequestInFlight) {
    return;
  }

  state.scanRequestInFlight = true;
  renderPage();

  try {
    const payload = await fetchJson(
      "/api/scan",
      {
        method: "POST",
        cache: "no-store",
      },
      "scan request failed"
    );
    applyDashboardPayload(payload);
    renderPage();
    scheduleDashboardRefresh({
      delayMs: 800,
      errorLabel: "刷新扫描状态失败",
      maxAttempts: 30,
    });
  } catch (error) {
    renderer.showPageError(`触发扫描失败: ${error.message}`);
  } finally {
    state.scanRequestInFlight = false;
    renderPage();
  }
}

function servicePortActionKey(namespace, serviceName, portKey, expose) {
  return `${namespace}/${serviceName}/${portKey}/${expose ? "open" : "close"}`;
}

function publicPortValueFromButton(button) {
  const row = button.closest(".service-port-row");
  const input = row?.querySelector('[data-role="public-port-input"]');
  return input ? input.value.trim() : "";
}

async function toggleServicePort(button) {
  if (state.serviceControlActionKey) {
    return;
  }

  const namespace = button.dataset.namespace || "";
  const serviceName = button.dataset.service || "";
  const portKey = button.dataset.portKey || "";
  const expose = button.dataset.expose === "true";
  const publicPort = publicPortValueFromButton(button);

  state.serviceControlActionKey = servicePortActionKey(namespace, serviceName, portKey, expose);
  renderPage();

  try {
    const payload = await fetchJson(
      "/api/service-controls/toggle",
      {
        method: "POST",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          namespace,
          service_name: serviceName,
          port_key: portKey,
          expose,
          public_port: publicPort || null,
        }),
      },
      "toggle request failed"
    );
    applyDashboardPayload(payload);
    renderPage();
    scheduleDashboardRefresh({
      delayMs: 900,
      errorLabel: "刷新暴露结果失败",
      maxAttempts: 30,
    });
  } catch (error) {
    renderer.showPageError(`调整业务 Service 端口治理失败: ${error.message}`);
  } finally {
    state.serviceControlActionKey = "";
    renderPage();
  }
}

function rerender() {
  renderPage();
}

refs.statusFilter.addEventListener("change", rerender);
refs.typeFilter.addEventListener("change", rerender);
refs.searchInput.addEventListener("input", rerender);
refs.serviceControlSearchInput.addEventListener("input", () => {
  state.serviceControlQuery = refs.serviceControlSearchInput.value.trim().toLowerCase();
  renderPage();
});
refs.platformToggleButton.addEventListener("click", () => {
  state.showPlatformComponents = !state.showPlatformComponents;
  renderPage();
});
refs.scanNowButton.addEventListener("click", triggerScan);
refs.serviceControlRefreshButton.addEventListener("click", triggerScan);
refs.serviceControlList.addEventListener("click", (event) => {
  const button = event.target.closest('[data-action="toggle-service-port"]');
  if (!button) {
    return;
  }
  toggleServicePort(button);
});
refs.tabButtons.forEach((button) => {
  button.addEventListener("click", () => {
    state.activeTab = button.dataset.tab || "all";
    renderPage();
  });
});
refs.resultTableDetails.addEventListener("toggle", () => {
  state.tableExpanded = refs.resultTableDetails.open;
});

fetchDashboard().catch((error) => {
  renderer.showPageError(`页面初始化失败: ${error.message}`);
});
