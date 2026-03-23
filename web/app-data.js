const TYPE_META = {
  ExternalIP: { value: "external_ip", label: "ExternalIP" },
  LoadBalancer: { value: "load_balancer", label: "LoadBalancer" },
  NodePort: { value: "node_port", label: "NodePort" },
  HostPort: { value: "host_port", label: "HostPort" },
  HostNetworkPod: { value: "host_network_pod", label: "HostNetwork" },
  NodeListener: { value: "node_listener", label: "节点监听" },
};

const TYPE_PRIORITY = {
  external_ip: 0,
  load_balancer: 1,
  node_port: 2,
  host_port: 3,
  host_network_pod: 4,
  node_listener: 5,
  other: 6,
};

const STATUS_PRIORITY = {
  open: 0,
  timeout: 1,
  unreachable: 2,
  closed: 3,
  error: 4,
};

// 后端返回的结构偏向报告存储；这里统一转换为前端视图模型。

export function emptyState() {
  return {
    items: [],
    groups: [],
    nodeInventory: [],
    nodeGroups: [],
    filterOptions: [],
    summary: {
      openCount: 0,
      trafficCount: 0,
      resourceCount: 0,
      uniqueAddressCount: 0,
      itemCount: 0,
    },
  };
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function statusClass(status) {
  return `status-pill status-${status || "unknown"}`;
}

export function formatTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

export function formatLatency(value) {
  return value == null ? "-" : `${value} ms`;
}

export function formatScanMode(mode) {
  if (mode === "host_exposure") {
    return "宿主机暴露扫描";
  }
  return "待执行";
}

function typeMeta(typeLabel) {
  return TYPE_META[typeLabel] || { value: "other", label: typeLabel || "Unknown" };
}

function compareItems(left, right) {
  return (
    (STATUS_PRIORITY[left.status] ?? 99) - (STATUS_PRIORITY[right.status] ?? 99) ||
    (TYPE_PRIORITY[left.typeValue] ?? 99) - (TYPE_PRIORITY[right.typeValue] ?? 99) ||
    left.namespace.localeCompare(right.namespace) ||
    left.groupName.localeCompare(right.groupName) ||
    left.resourceName.localeCompare(right.resourceName) ||
    left.address.localeCompare(right.address) ||
    left.port - right.port
  );
}

function comparePortItems(left, right) {
  return (
    (STATUS_PRIORITY[left.status] ?? 99) - (STATUS_PRIORITY[right.status] ?? 99) ||
    left.port - right.port ||
    (TYPE_PRIORITY[left.typeValue] ?? 99) - (TYPE_PRIORITY[right.typeValue] ?? 99)
  );
}

function buildSearchText(item) {
  return [
    item.namespace,
    item.groupName,
    item.resourceName,
    item.typeLabel,
    item.kindLabel,
    item.serviceType,
    item.address,
    item.port,
    item.nodeName,
    item.container,
    item.portName,
    item.targetPort,
    item.note,
    ...(item.discoveryPaths || []),
    ...(item.relatedObjects || []),
    ...(item.observedStates || []),
    item.error,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function buildItemNote(item, includeObjectName = false) {
  const parts = [];

  if (includeObjectName && item.resourceName !== item.groupName) {
    parts.push(item.resourceName);
  }
  if (item.kindLabel) {
    parts.push(item.kindLabel);
  }
  if (item.serviceType) {
    parts.push(item.serviceType);
  }
  if (item.portName) {
    parts.push(`port ${item.portName}`);
  }
  if (item.targetPort) {
    parts.push(`target ${item.targetPort}`);
  }
  if (item.nodeName) {
    parts.push(`node ${item.nodeName}`);
  }
  if (item.container) {
    parts.push(`container ${item.container}`);
  }
  if (item.trafficObserved && item.observedStates.length) {
    parts.push(`流量状态 ${item.observedStates.join(", ")}`);
  } else if (item.listenerObserved) {
    parts.push("发现监听");
  }
  if (item.error) {
    parts.push(item.error);
  }
  if (item.note) {
    parts.push(item.note);
  }

  return parts.join(" / ");
}

function normalizeItems(externalSummary) {
  return (externalSummary?.items || []).map((item) => {
    const meta = typeMeta(item.exposure_type);
    const normalized = {
      namespace: item.namespace || "-",
      groupName: item.group_name || item.resource_name || "-",
      resourceName: item.resource_name || item.group_name || "-",
      kindLabel: item.resource_kind || "Service",
      typeLabel: meta.label,
      typeValue: meta.value,
      address: String(item.address || ""),
      port: Number(item.port || 0),
      status: item.status || "unknown",
      latencyMs: item.latency_ms,
      error: item.error || null,
      nodeName: item.node_name || "",
      container: item.container || "",
      portName: item.port_name || "",
      targetPort: item.target_port || "",
      serviceType: item.service_type || "",
      note: item.note || "",
      discoveryPaths: item.discovery_paths || [],
      relatedObjects: item.related_objects || [],
      trafficObserved: Boolean(item.traffic_observed),
      listenerObserved: Boolean(item.listener_observed),
      observedStates: item.observed_states || [],
      observedSampleCount: Number(item.observed_sample_count || 0),
    };
    normalized.searchText = buildSearchText(normalized);
    return normalized;
  });
}

function normalizeNodeInventory(externalSummary) {
  return (externalSummary?.node_inventory || []).map((node) => ({
    name: node.name || "-",
    addresses: (node.addresses || []).map((addressRecord) => ({
      address: String(addressRecord.address || ""),
      addressType: addressRecord.address_type || "Unknown",
    })),
  }));
}

function buildObjectGroups(items) {
  const grouped = new Map();

  items.forEach((item) => {
    const key = `${item.namespace}|${item.groupName}|${item.kindLabel}`;
    let group = grouped.get(key);
    if (!group) {
      group = {
        namespace: item.namespace,
        name: item.groupName,
        kindLabel: item.kindLabel,
        serviceType: item.serviceType,
        items: [],
        typeLabels: new Set(),
        openTargets: new Set(),
        trafficTargets: new Set(),
        addresses: new Set(),
      };
      grouped.set(key, group);
    }

    group.items.push(item);
    group.typeLabels.add(`${item.typeValue}:::${item.typeLabel}`);
    group.addresses.add(item.address);
    if (item.status === "open") {
      group.openTargets.add(`${item.address}:${item.port}`);
    }
    if (item.trafficObserved || item.listenerObserved) {
      group.trafficTargets.add(`${item.address}:${item.port}`);
    }
  });

  return Array.from(grouped.values())
    .map((group) => ({
      ...group,
      items: [...group.items].sort(compareItems),
      typeLabels: [...group.typeLabels]
        .map((value) => {
          const [typeValue, label] = value.split(":::");
          return { value: typeValue, label };
        })
        .sort(
          (left, right) =>
            (TYPE_PRIORITY[left.value] ?? 99) - (TYPE_PRIORITY[right.value] ?? 99) ||
            left.label.localeCompare(right.label)
        )
        .map((item) => item.label),
      openTargetCount: group.openTargets.size,
      trafficTargetCount: group.trafficTargets.size,
      uniqueAddressCount: group.addresses.size,
      summaryText: [group.kindLabel, group.serviceType].filter(Boolean).join(" · "),
    }))
    .sort(
      (left, right) =>
        right.openTargetCount - left.openTargetCount ||
        right.trafficTargetCount - left.trafficTargetCount ||
        left.namespace.localeCompare(right.namespace) ||
        left.name.localeCompare(right.name)
    );
}

function buildNodeGroups(items, nodeInventory, showEmptyNodes) {
  const itemsByNodeName = new Map();
  const itemsByAddress = new Map();

  items.forEach((item) => {
    if (item.nodeName) {
      if (!itemsByNodeName.has(item.nodeName)) {
        itemsByNodeName.set(item.nodeName, []);
      }
      itemsByNodeName.get(item.nodeName).push(item);
    }

    if (!itemsByAddress.has(item.address)) {
      itemsByAddress.set(item.address, []);
    }
    itemsByAddress.get(item.address).push(item);
  });

  const nodes = nodeInventory.map((node) => {
    const matched = new Map();

    (itemsByNodeName.get(node.name) || []).forEach((item) => {
      matched.set(`${item.address}:${item.port}`, item);
    });
    node.addresses.forEach((addressRecord) => {
      (itemsByAddress.get(addressRecord.address) || []).forEach((item) => {
        matched.set(`${item.address}:${item.port}`, item);
      });
    });

    const matchedItems = [...matched.values()].sort(compareItems);
    const typeLabels = new Set();
    const openTargets = new Set();
    const trafficTargets = new Set();

    matchedItems.forEach((item) => {
      typeLabels.add(`${item.typeValue}:::${item.typeLabel}`);
      if (item.status === "open") {
        openTargets.add(`${item.address}:${item.port}`);
      }
      if (item.trafficObserved || item.listenerObserved) {
        trafficTargets.add(`${item.address}:${item.port}`);
      }
    });

    const addressGroups = node.addresses.map((addressRecord) => {
      const addressItems = matchedItems
        .filter((item) => item.address === addressRecord.address)
        .sort(comparePortItems);
      const openCount = addressItems.filter((item) => item.status === "open").length;
      const trafficCount = addressItems.filter(
        (item) => item.trafficObserved || item.listenerObserved
      ).length;

      return {
        address: addressRecord.address,
        addressType: addressRecord.addressType,
        items: addressItems,
        itemCount: addressItems.length,
        openCount,
        trafficCount,
      };
    });

    const searchText = [
      node.name,
      ...node.addresses.map((item) => `${item.address} ${item.addressType}`),
      ...matchedItems.map((item) => `${item.typeLabel} ${item.address}:${item.port} ${item.status}`),
    ]
      .join(" ")
      .toLowerCase();

    return {
      name: node.name,
      addresses: node.addresses,
      addressGroups,
      items: matchedItems,
      itemCount: matchedItems.length,
      openCount: openTargets.size,
      trafficCount: trafficTargets.size,
      typeLabels: [...typeLabels]
        .map((value) => {
          const [typeValue, label] = value.split(":::");
          return { value: typeValue, label };
        })
        .sort(
          (left, right) =>
            (TYPE_PRIORITY[left.value] ?? 99) - (TYPE_PRIORITY[right.value] ?? 99) ||
            left.label.localeCompare(right.label)
        )
        .map((item) => item.label),
      searchText,
    };
  });

  return nodes
    .filter((node) => showEmptyNodes || node.itemCount > 0)
    .sort(
      (left, right) =>
        right.openCount - left.openCount ||
        right.trafficCount - left.trafficCount ||
        left.name.localeCompare(right.name)
    );
}

function buildState(items, nodeInventory, options = {}) {
  const sortedItems = [...items].sort(compareItems);
  const typeMap = new Map();
  sortedItems.forEach((item) => typeMap.set(item.typeValue, item.typeLabel));

  const groups = buildObjectGroups(sortedItems);
  const nodeGroups = buildNodeGroups(
    sortedItems,
    nodeInventory,
    options.showEmptyNodes !== false,
  );

  return {
    items: sortedItems,
    groups,
    nodeInventory,
    nodeGroups,
    filterOptions: [...typeMap.entries()]
      .map(([value, label]) => ({ value, label }))
      .sort(
        (left, right) =>
          (TYPE_PRIORITY[left.value] ?? 99) - (TYPE_PRIORITY[right.value] ?? 99) ||
          left.label.localeCompare(right.label)
      ),
    summary: {
      openCount: sortedItems.filter((item) => item.status === "open").length,
      trafficCount: sortedItems.filter((item) => item.trafficObserved || item.listenerObserved).length,
      resourceCount: groups.length,
      uniqueAddressCount: new Set(sortedItems.map((item) => item.address)).size,
      itemCount: sortedItems.length,
    },
  };
}

export function buildExposureState(externalSummary) {
  return buildState(normalizeItems(externalSummary), normalizeNodeInventory(externalSummary), {
    showEmptyNodes: true,
  });
}

export function filterState(viewState, filters) {
  const filteredItems = viewState.items.filter((item) => {
    if (filters.status !== "all" && item.status !== filters.status) {
      return false;
    }
    if (filters.typeValue !== "all" && item.typeValue !== filters.typeValue) {
      return false;
    }
    if (!filters.query) {
      return true;
    }
    return item.searchText.includes(filters.query);
  });

  const showEmptyNodes =
    filters.status === "all" &&
    filters.typeValue === "all" &&
    !filters.query;

  return buildState(filteredItems, viewState.nodeInventory, { showEmptyNodes });
}
