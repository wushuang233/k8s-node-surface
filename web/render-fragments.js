import {
  buildItemNote,
  buildTableSupplement,
  escapeHtml,
  formatLatency,
  statusClass,
} from "./app-data.js";

function evidenceKeyword(item) {
  if (item.trafficObserved) {
    return "流量";
  }
  if (item.listenerObserved) {
    return "监听";
  }
  return "";
}

function renderTrafficBadge(count) {
  if (!count) {
    return "";
  }
  return `<span class="badge badge-alert">流量 ${escapeHtml(count)}</span>`;
}

function renderLabelBadges(labels, maxVisible = 3) {
  if (!labels.length) {
    return '<span class="badge badge-muted">无归因</span>';
  }

  const visible = labels.slice(0, maxVisible);
  const rest = labels.length - visible.length;
  const badges = visible.map((label) => `<span class="badge">${escapeHtml(label)}</span>`);
  if (rest > 0) {
    badges.push(`<span class="badge badge-muted">+${escapeHtml(rest)}</span>`);
  }
  return badges.join("");
}

function renderPortChip(item) {
  const evidence = evidenceKeyword(item);
  return `
    <span class="port-chip port-chip-${escapeHtml(item.status)}">
      <span class="port-chip-value">${escapeHtml(item.port)}</span>
      <span class="port-chip-meta">${escapeHtml(item.typeLabel)}</span>
      ${evidence ? `<span class="port-chip-evidence">${escapeHtml(evidence)}</span>` : ""}
    </span>
  `;
}

function renderAddressGroup(addressGroup) {
  const chips = addressGroup.items.map(renderPortChip).join("");
  return `
    <div class="address-card">
      <div class="address-card-head">
        <div>
          <div class="item-target">${escapeHtml(addressGroup.address)}</div>
          <div class="service-meta">${escapeHtml(addressGroup.addressType)} · 记录 ${escapeHtml(
    addressGroup.itemCount
  )} 条 · open ${escapeHtml(addressGroup.openCount)}</div>
        </div>
        <div class="badge-row">
          ${renderTrafficBadge(addressGroup.trafficCount)}
        </div>
      </div>
      <div class="port-chip-list">
        ${chips || '<span class="badge badge-muted">当前筛选条件无匹配结果</span>'}
      </div>
    </div>
  `;
}

export function renderNodeCard(node) {
  const typeBadges = renderLabelBadges(node.typeLabels);

  const addressBlocks = node.addressGroups.map(renderAddressGroup).join("");

  return `
    <summary class="node-card-summary details-summary">
      <div>
        <p class="section-kicker">节点</p>
        <h3 class="service-name">${escapeHtml(node.name)}</h3>
        <p class="service-meta">地址 ${escapeHtml(node.addresses.length)} 个 · 记录 ${escapeHtml(
    node.itemCount
  )} 条 · open ${escapeHtml(node.openCount)}</p>
      </div>
      <div class="badge-row">
        ${typeBadges}
        ${node.trafficCount ? `<span class="badge badge-alert">流量 ${escapeHtml(node.trafficCount)}</span>` : ""}
      </div>
    </summary>
    <div class="node-card-body">${addressBlocks}</div>
  `;
}

function renderGroupItem(item) {
  const note = buildItemNote(item, true);
  return `
    <div class="item-row compact-row">
      <div class="item-row-main">
        <div class="item-target">${escapeHtml(item.address)}:${escapeHtml(item.port)}</div>
        <div class="service-meta">${escapeHtml(note || item.nodeName || "-")}</div>
      </div>
      <div class="badge-row compact-badges">
        <span class="badge">${escapeHtml(item.typeLabel)}</span>
        ${
          item.trafficObserved
            ? '<span class="badge badge-alert">流量</span>'
            : item.listenerObserved
              ? '<span class="badge badge-muted">监听</span>'
              : ""
        }
        <span class="${statusClass(item.status)}">${escapeHtml(item.status)}</span>
      </div>
    </div>
  `;
}

export function renderGroupCard(group) {
  const typeBadges = renderLabelBadges(group.typeLabels);
  const evidenceBadge = renderTrafficBadge(group.trafficTargetCount);
  const itemRows = group.items.map(renderGroupItem).join("");

  return `
    <summary class="result-card-summary details-summary">
      <div>
        <p class="section-kicker">${escapeHtml(group.namespace)}</p>
        <h3 class="service-name">${escapeHtml(group.name)}</h3>
        <p class="service-meta">${escapeHtml(group.summaryText)} · 记录 ${escapeHtml(
    group.items.length
  )} 条 · 地址 ${escapeHtml(group.uniqueAddressCount)} 个</p>
      </div>
      <div class="badge-row">
        ${typeBadges}
        ${evidenceBadge}
        <span class="badge badge-primary">open ${escapeHtml(group.openTargetCount)}</span>
      </div>
    </summary>
    <div class="service-items">${itemRows}</div>
  `;
}

export function renderTableRow(item) {
  const evidenceBadges = [
    `<span class="badge">${escapeHtml(item.typeLabel)}</span>`,
    item.trafficObserved
      ? `<span class="badge badge-alert">流量 ${escapeHtml(
          item.observedStates.join(", ") || item.observedSampleCount || "-"
        )}</span>`
      : item.listenerObserved
        ? '<span class="badge badge-muted">监听</span>'
        : '<span class="badge badge-muted">主动探测</span>',
  ].join("");
  const objectLabel = item.namespace === "-" ? item.resourceName : `${item.namespace}/${item.resourceName}`;
  const objectMeta = [item.kindLabel, item.serviceType].filter(Boolean).join(" · ") || item.typeLabel;
  const supplement = buildTableSupplement(item) || "-";

  return `
    <td class="compact-cell target-cell">
      <div class="cell-primary item-target">${escapeHtml(item.address)}:${escapeHtml(item.port)}</div>
      <div class="cell-secondary">${escapeHtml(item.portName || "-")}</div>
    </td>
    <td class="compact-cell object-cell">
      <div class="cell-primary">${escapeHtml(objectLabel)}</div>
      <div class="cell-secondary">${escapeHtml(objectMeta)}</div>
    </td>
    <td class="compact-cell node-cell">
      <div class="cell-primary">${escapeHtml(item.nodeName || "-")}</div>
      <div class="cell-secondary">${escapeHtml(item.container || "-")}</div>
    </td>
    <td class="compact-cell status-cell">
      <span class="${statusClass(item.status)}">${escapeHtml(item.status)}</span>
      <div class="cell-secondary">${escapeHtml(formatLatency(item.latencyMs))}</div>
    </td>
    <td class="compact-cell evidence-cell">
      <div class="badge-row table-badges">${evidenceBadges}</div>
    </td>
    <td class="compact-cell note-cell">
      <div class="cell-secondary">${escapeHtml(supplement)}</div>
    </td>
  `;
}
