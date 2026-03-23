import { buildItemNote, escapeHtml, formatLatency, statusClass } from "./app-data.js";

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
    return '<span class="badge badge-muted">无流量证据</span>';
  }
  return `<span class="badge badge-alert">流量 ${escapeHtml(count)}</span>`;
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
  const typeBadges = node.typeLabels.length
    ? node.typeLabels.map((label) => `<span class="badge">${escapeHtml(label)}</span>`).join("")
    : '<span class="badge badge-muted">无记录</span>';

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
        <div class="service-meta">${escapeHtml(note || "-")}</div>
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
        ${
          item.nodeName
            ? `<span class="badge badge-muted">${escapeHtml(item.nodeName)}</span>`
            : item.container
              ? `<span class="badge badge-muted">${escapeHtml(item.container)}</span>`
              : ""
        }
        <span class="badge badge-muted">${escapeHtml(formatLatency(item.latencyMs))}</span>
        <span class="${statusClass(item.status)}">${escapeHtml(item.status)}</span>
      </div>
    </div>
  `;
}

export function renderGroupCard(group) {
  const typeBadges = group.typeLabels
    .map((label) => `<span class="badge">${escapeHtml(label)}</span>`)
    .join("");
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
  const evidence = item.trafficObserved
    ? `流量 ${item.observedStates.join(", ") || item.observedSampleCount}`
    : item.listenerObserved
      ? "监听"
      : "-";
  const objectLabel = item.namespace === "-" ? item.resourceName : `${item.namespace}/${item.resourceName}`;

  return `
    <td class="compact-cell">${escapeHtml(objectLabel)}</td>
    <td class="compact-cell">${escapeHtml(item.nodeName || "-")}</td>
    <td class="compact-cell">${escapeHtml(item.typeLabel)}</td>
    <td class="compact-cell"><span class="item-target">${escapeHtml(item.address)}:${escapeHtml(item.port)}</span></td>
    <td class="compact-cell"><span class="${statusClass(item.status)}">${escapeHtml(item.status)}</span></td>
    <td class="compact-cell">${escapeHtml(evidence)}</td>
    <td class="compact-cell note-cell">${escapeHtml(buildItemNote(item, false) || "-")}</td>
  `;
}
