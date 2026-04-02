import {
  buildMatchedK8sServicePreview,
  buildConfigTypeDocNote,
  classifyConfigType,
  describeConfigReference,
  ensureArray,
  escapeHtml,
  findServicesForConfig,
  formatDate,
  getConfigTypeName,
  getMatchedBindIdentitiesForService,
  getMatchedBindServicesForIdentity,
  getMatchedDialIdentitiesForService,
  getMatchedDialServicesForIdentity,
  getMatchedIdentitiesForPolicy,
  getMatchedIdentitiesForRouter,
  getMatchedRoutersForIdentity,
  getMatchedRoutersForPolicy,
  getMatchedRoutersForService,
  getMatchedServicesForPolicy,
  getMatchedServicesForRouter,
  getEnrollments,
  getLatestIdentityEnrollment,
  getServiceConfigs,
  getServiceMaxIdleDisplay,
  getServicePoliciesForService,
  isDeprecatedConfigType,
  matchK8sServiceReference,
  refs,
  renderJsonBlock,
  renderPillList,
  state,
  tagsToList,
  workspaceGuides,
} from "./shared.js";

export function renderSession() {
  const session = state.session;
  refs.sessionState.textContent = session ? "已登录" : "未登录";
  refs.sessionController.textContent = session?.controller_url || refs.controllerUrl.value || "-";
  refs.sessionIdentity.textContent = session?.identity_name || "-";
  refs.sessionExpiry.textContent = session ? formatDate(session.expires_at) : "-";
  refs.logoutButton.disabled = !session || state.busy;
  refs.refreshButton.disabled = !session || state.busy;
  refs.loginButton.disabled = state.busy;
}

export function renderJwtPanel() {
  if (!state.lastJwt?.jwt) {
    refs.jwtPanel.classList.add("hidden");
    refs.jwtCommandPanel.classList.add("hidden");
    refs.jwtEnrollPanel.classList.add("hidden");
    refs.jwtCommandOutput.textContent = "";
    refs.jwtEnrollOutput.textContent = "";
    refs.jwtOutput.value = "";
    refs.copyJwtButton.disabled = true;
    refs.copyJwtCommandButton.disabled = true;
    refs.copyJwtEnrollButton.disabled = true;
    return;
  }
  refs.jwtPanel.classList.remove("hidden");
  refs.jwtTitle.textContent = `${state.lastJwt.name} 的 Enrollment JWT`;
  refs.jwtNote.textContent = state.lastJwt.note;
  refs.copyJwtButton.disabled = false;
  if (state.lastJwt.command) {
    refs.jwtCommandPanel.classList.remove("hidden");
    refs.jwtCommandOutput.textContent = state.lastJwt.command;
    refs.copyJwtCommandButton.disabled = false;
  } else {
    refs.jwtCommandPanel.classList.add("hidden");
    refs.jwtCommandOutput.textContent = "";
    refs.copyJwtCommandButton.disabled = true;
  }
  if (state.lastJwt.enrollCommand) {
    refs.jwtEnrollPanel.classList.remove("hidden");
    refs.jwtEnrollOutput.textContent = state.lastJwt.enrollCommand;
    refs.copyJwtEnrollButton.disabled = false;
  } else {
    refs.jwtEnrollPanel.classList.add("hidden");
    refs.jwtEnrollOutput.textContent = "";
    refs.copyJwtEnrollButton.disabled = true;
  }
  refs.jwtOutput.value = state.lastJwt.jwt;
}

function statCard(label, value) {
  return `<article class="stat-chip"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`;
}

export function renderStats() {
  if (!state.overview) {
    refs.statsStrip.innerHTML = "";
    return;
  }
  const counts = state.overview.counts || {};
  const pendingRouters = ensureArray(state.overview.edge_routers).filter((item) => item.isVerified === false).length;
  const pendingClientEnrollments = getEnrollments().filter((item) => item.identityId && String(item?.method || "").toLowerCase() === "ott").length;
  const totalPolicies =
    (counts.service_policies || 0) +
    (counts.edge_router_policies || 0) +
    (counts.service_edge_router_policies || 0);

  refs.statsStrip.innerHTML = [
    statCard("在线路由器", counts.alive_edge_routers || 0),
    statCard("已部署 Router", counts.deployed_edge_routers || 0),
    statCard("待重入网", pendingRouters),
    statCard("待客户端入网", pendingClientEnrollments),
    statCard("服务", counts.services || 0),
    statCard("配置", counts.configs || 0),
    statCard("策略总数", totalPolicies),
    statCard("身份", counts.identities || 0),
  ].join("");
}

export function renderWorkspaceGuide() {
  if (!refs.workspaceGuide) {
    return;
  }
  if (!state.session || !state.overview) {
    refs.workspaceGuide.innerHTML = "";
    return;
  }
  const guide = workspaceGuides[state.activeTab];
  if (!guide) {
    refs.workspaceGuide.innerHTML = "";
    return;
  }

  refs.workspaceGuide.innerHTML = `
    <section class="guide-card">
      <div class="guide-header">
        <div>
          <p class="section-kicker">使用提示</p>
          <h3>${escapeHtml(guide.title)}</h3>
          <p>${escapeHtml(guide.summary)}</p>
        </div>
      </div>
      <div class="guide-pills">
        ${ensureArray(guide.pills).map((item) => `<span class="guide-pill">${escapeHtml(item)}</span>`).join("")}
      </div>
      <div class="guide-list">
        ${ensureArray(guide.steps).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
      </div>
      <p class="guide-note">${escapeHtml(guide.note)}</p>
    </section>
  `;
}

function renderEmpty(message) {
  refs.contentPanel.innerHTML = `
    <div class="empty-state">
      <h3>暂无数据</h3>
      <p>${escapeHtml(message)}</p>
    </div>
  `;
}

function sortByName(items = []) {
  return [...ensureArray(items)].sort((left, right) => {
    const leftKey = String(left?.name || left?.id || "");
    const rightKey = String(right?.name || right?.id || "");
    const order = leftKey.localeCompare(rightKey, "zh-CN");
    if (order !== 0) {
      return order;
    }
    return String(left?.id || "").localeCompare(String(right?.id || ""), "zh-CN");
  });
}

function getEntityLabel(item) {
  return String(item?.name || item?.id || "-");
}

function renderEntityPills(items, emptyText) {
  return renderPillList(ensureArray(items).map((item) => getEntityLabel(item)), emptyText);
}

function renderContentSection(title, kicker, summary, bodyMarkup) {
  return `
    <section class="content-section">
      <div class="content-section-head">
        <div>
          <p class="section-kicker">${escapeHtml(kicker)}</p>
          <h3>${escapeHtml(title)}</h3>
          ${summary ? `<p>${escapeHtml(summary)}</p>` : ""}
        </div>
      </div>
      ${bodyMarkup}
    </section>
  `;
}

function renderSectionEmpty(message) {
  return `
    <div class="empty-state compact-empty">
      <h3>暂无匹配资源</h3>
      <p>${escapeHtml(message)}</p>
    </div>
  `;
}

function renderResourceSection(title, kicker, summary, cardMarkupList, emptyMessage) {
  const cards = ensureArray(cardMarkupList).filter(Boolean);
  return renderContentSection(
    title,
    kicker,
    summary,
    cards.length ? `<div class="resource-grid">${cards.join("")}</div>` : renderSectionEmpty(emptyMessage),
  );
}

function configPortSummary(configData) {
  const firstRange = ensureArray(configData?.portRanges)[0] || {};
  const low = firstRange?.low ?? configData?.port ?? "-";
  const high = firstRange?.high ?? low;
  if (low === "-" && high === "-") {
    return "-";
  }
  return low === high ? String(low) : `${low}-${high}`;
}

function configProtocolSummary(configData) {
  const protocols = ensureArray(configData?.protocols);
  if (protocols.length) {
    return protocols.map((item) => String(item || "").toLowerCase()).join(", ");
  }
  return String(configData?.protocol || "tcp").toLowerCase();
}

function renderConfigUsage(config) {
  const configTypeName = getConfigTypeName(config);
  const relatedServices = findServicesForConfig(config?.id);
  const usageType = classifyConfigType(configTypeName);

  if (usageType === "intercept") {
    const addresses = ensureArray(config?.data?.addresses);
    return `
      <div class="relation-stack">
        <div class="relation-block">
          <span class="relation-kicker">客户端入口 / Dial 侧</span>
          <strong>${escapeHtml(addresses.join(", ") || "-")}</strong>
          <p>${escapeHtml(`${configProtocolSummary(config?.data)} / ${configPortSummary(config?.data)}`)}</p>
          <div class="pill-row">
            ${renderEntityPills(relatedServices, "暂未绑定 service")}
          </div>
        </div>
      </div>
    `;
  }

  if (usageType === "host") {
    const targetAddress = String(config?.data?.address || "").trim();
    const matchedService = matchK8sServiceReference(targetAddress);
    return `
      <div class="relation-stack">
        <div class="relation-block">
          <span class="relation-kicker">服务托管 / Bind 侧</span>
          <strong class="mono">${escapeHtml(targetAddress || "-")}</strong>
          <p>${escapeHtml(`${configProtocolSummary(config?.data)} / ${configPortSummary(config?.data)}`)}</p>
          <div class="pill-row">
            ${renderEntityPills(relatedServices, "暂未绑定 service")}
          </div>
        </div>
        ${matchedService ? buildMatchedK8sServicePreview(matchedService.namespace, matchedService.name) : ""}
      </div>
    `;
  }

  return `
    <div class="relation-stack">
      <div class="relation-block">
        <span class="relation-kicker">其他配置</span>
        <strong>${escapeHtml(configTypeName)}</strong>
        <p>建议先看下面的原始 JSON，再决定是否和 service 绑定。</p>
        <div class="pill-row">
          ${renderEntityPills(relatedServices, "暂未绑定 service")}
        </div>
      </div>
    </div>
  `;
}

function renderServiceFlow(item) {
  const serviceConfigs = getServiceConfigs(item);
  const interceptConfigs = serviceConfigs.filter((config) => classifyConfigType(getConfigTypeName(config)) === "intercept");
  const hostConfigs = serviceConfigs.filter((config) => classifyConfigType(getConfigTypeName(config)) === "host");
  const otherConfigs = serviceConfigs.filter((config) => classifyConfigType(getConfigTypeName(config)) === "other");
  const dialPolicies = getServicePoliciesForService(item, "Dial");
  const bindPolicies = getServicePoliciesForService(item, "Bind");
  const dialIdentities = getMatchedDialIdentitiesForService(item);
  const bindIdentities = getMatchedBindIdentitiesForService(item);
  const routers = getMatchedRoutersForService(item);
  const firstHostConfig = hostConfigs[0];
  const matchedK8sService = matchK8sServiceReference(firstHostConfig?.data?.address);

  const interceptTargets = interceptConfigs.map((config) => {
    const addresses = ensureArray(config?.data?.addresses).filter(Boolean);
    return `${addresses.join(", ") || config.name} · ${configProtocolSummary(config?.data)}:${configPortSummary(config?.data)}`;
  });

  const hostTargets = hostConfigs.map((config) => {
    const address = String(config?.data?.address || "").trim();
    return `${address || config.name} · ${configProtocolSummary(config?.data)}:${configPortSummary(config?.data)}`;
  });

  return `
    <article class="resource-card service-card">
      <div class="card-header">
        <div>
          <div class="card-title">${escapeHtml(item.name || item.id)}</div>
          <div class="card-subtitle mono">${escapeHtml(item.id)}</div>
        </div>
        <span class="pill ${item.encryptionRequired ? "" : "warn"}">${item.encryptionRequired ? "强制加密" : "允许明文"}</span>
      </div>
      <div class="flow-strip">
        <div class="flow-node">
          <span class="flow-kicker">客户端入口</span>
          <strong>${escapeHtml(interceptTargets[0] || "未绑定 intercept")}</strong>
          <small>${escapeHtml(`${dialIdentities.length} 个可 Dial 身份`)}</small>
        </div>
        <div class="flow-arrow">→</div>
        <div class="flow-node flow-node-center">
          <span class="flow-kicker">Ziti Service</span>
          <strong>${escapeHtml(item.name || item.id)}</strong>
          <small>${escapeHtml(`${routers.length} 台可用 router`)}</small>
        </div>
        <div class="flow-arrow">→</div>
        <div class="flow-node">
          <span class="flow-kicker">托管出口</span>
          <strong>${escapeHtml(hostTargets[0] || "未绑定 host")}</strong>
          <small>${escapeHtml(`${bindIdentities.length} 个可 Bind 身份`)}</small>
        </div>
      </div>
      <div class="relation-grid">
        <section class="relation-block">
          <span class="relation-kicker">Dial 策略</span>
          <strong>谁能访问这个服务</strong>
          <div class="pill-row">
            ${renderEntityPills(dialPolicies, "未配置 Dial 策略")}
          </div>
          <div class="pill-row">
            ${renderEntityPills(dialIdentities, "没有匹配到客户端身份")}
          </div>
          <div class="pill-row">
            ${renderPillList(interceptTargets, "没有 intercept 入口")}
          </div>
        </section>
        <section class="relation-block">
          <span class="relation-kicker">Bind 策略</span>
          <strong>谁来托管这个服务</strong>
          <div class="pill-row">
            ${renderEntityPills(bindPolicies, "未配置 Bind 策略")}
          </div>
          <div class="pill-row">
            ${renderEntityPills(bindIdentities, "没有匹配到托管身份")}
          </div>
          <div class="pill-row">
            ${renderPillList(hostTargets, "没有 host 目标")}
          </div>
        </section>
        <section class="relation-block">
          <span class="relation-kicker">Router 与后端</span>
          <strong>服务最终走哪台 router、落到哪个后端</strong>
          <div class="pill-row">
            ${renderEntityPills(routers, "未配置服务接入 router")}
          </div>
          <div class="pill-row">
            ${renderPillList(otherConfigs.map((config) => describeConfigReference(config.id)), "没有其他 configs")}
          </div>
          ${matchedK8sService ? buildMatchedK8sServicePreview(matchedK8sService.namespace, matchedK8sService.name) : ""}
        </section>
      </div>
      <div class="meta-row">
        <span class="meta-label">终结器策略</span>
        <strong>${escapeHtml(item.terminatorStrategy || "-")}</strong>
      </div>
      <div class="meta-row">
        <span class="meta-label">空闲回收时间</span>
        <strong>${escapeHtml(getServiceMaxIdleDisplay(item))}</strong>
      </div>
      <div class="pill-row">
        ${renderPillList(ensureArray(item.roleAttributes), "无角色属性")}
      </div>
      <div class="pill-row">
        ${renderPillList(serviceConfigs.map((config) => describeConfigReference(config.id)), "未绑定 config")}
      </div>
      <div class="pill-row">
        ${renderPillList(tagsToList(item.tags), "无 tags")}
      </div>
      <div class="card-actions">
        <button class="button-muted" data-action="edit" data-type="services" data-id="${escapeHtml(item.id)}">编辑</button>
        <button class="button-muted" data-action="delete" data-type="services" data-id="${escapeHtml(item.id)}">删除</button>
      </div>
    </article>
  `;
}

function renderRouters() {
  let items = [...ensureArray(state.overview.edge_routers)].sort((left, right) => Number(Boolean(right.isOnline)) - Number(Boolean(left.isOnline)));
  if (state.aliveOnly) {
    items = items.filter((item) => item.isOnline);
  }
  if (!items.length) {
    renderEmpty(state.aliveOnly ? "当前没有在线路由器。" : "当前没有路由器。");
    return;
  }
  refs.contentPanel.innerHTML = `
    <div class="resource-grid">
      ${items
        .map((item) => {
          const roleAttributes = ensureArray(item.roleAttributes);
          const mappedServices = getMatchedServicesForRouter(item);
          const mappedIdentities = getMatchedIdentitiesForRouter(item);
          const workload = item.k8sWorkload || null;
          const workloadReady = Boolean(workload?.available);
          return `
            <article class="resource-card">
              <div class="card-header">
                <div>
                  <div class="card-title">${escapeHtml(item.name || item.id)}</div>
                  <div class="card-subtitle mono">${escapeHtml(item.id)}</div>
                </div>
                <div class="pill-row">
                  <span class="pill ${item.isOnline ? "" : "offline"}">${item.isOnline ? "在线" : "离线"}</span>
                  <span class="pill ${item.disabled ? "warn" : ""}">${item.disabled ? "禁用" : "启用"}</span>
                  ${item.isVerified === false ? '<span class="pill warn">待重新入网</span>' : ""}
                </div>
              </div>
              <div class="meta-row">
                <span class="meta-label">主机名</span>
                <strong>${escapeHtml(item.hostname || "-")}</strong>
              </div>
              <div class="meta-row">
                <span class="meta-label">同步状态</span>
                <strong>${escapeHtml(item.syncStatus || "-")}</strong>
              </div>
              <div class="meta-row">
                <span class="meta-label">验证状态</span>
                <strong>${escapeHtml(item.isVerified === false ? "未验证" : item.isVerified === true ? "已验证" : "-")}</strong>
              </div>
              <div class="meta-row">
                <span class="meta-label">Enrollment 过期</span>
                <strong>${escapeHtml(formatDate(item.enrollmentExpiresAt))}</strong>
              </div>
              <div class="meta-row">
                <span class="meta-label">成本</span>
                <strong>${escapeHtml(item.cost ?? 0)}</strong>
              </div>
              <div class="relation-stack">
                <section class="relation-block">
                  <span class="relation-kicker">K8s 工作负载</span>
                  <strong>${escapeHtml(workload ? `${workload.deploymentName || "-"} / ${workload.serviceName || "-"}` : "当前只存在 controller 记录")}</strong>
                  <div class="pill-row">
                    ${
                      workload
                        ? `
                          <span class="pill ${workloadReady ? "" : "offline"}">${workloadReady ? "K8s 已就绪" : "K8s 未就绪"}</span>
                          <span class="pill">${escapeHtml(`NodePort ${workload.nodePort || "-"}`)}</span>
                          <span class="pill">${escapeHtml(`Host ${workload.publicHost || "-"}`)}</span>
                        `
                        : '<span class="pill warn">尚未部署到 K8s</span>'
                    }
                  </div>
                  <p>${escapeHtml(workload ? `Deployment ${workload.deploymentName || "-"}，${workload.readyReplicas || 0}/${workload.replicas || 0} Ready` : "点“部署到 K8s”后，页面会自动创建 Secret、ConfigMap、PVC、Service 和 Deployment。")}</p>
                </section>
              </div>
              <div class="relation-stack">
                <section class="relation-block">
                  <span class="relation-kicker">可承载服务</span>
                  <strong>${escapeHtml(mappedServices.length ? `${mappedServices.length} 个 service` : "当前没有 service 命中")}</strong>
                  <div class="pill-row">
                    ${renderEntityPills(mappedServices, "没有命中的 service")}
                  </div>
                </section>
                <section class="relation-block">
                  <span class="relation-kicker">可通行身份</span>
                  <strong>${escapeHtml(mappedIdentities.length ? `${mappedIdentities.length} 个 identity` : "当前没有 identity 命中")}</strong>
                  <div class="pill-row">
                    ${renderEntityPills(mappedIdentities, "没有命中的 identity")}
                  </div>
                </section>
              </div>
              <div class="pill-row">
                ${renderPillList(roleAttributes, "无角色属性")}
              </div>
              <div class="card-actions">
                <button class="button-muted" data-action="deploy-k8s-router" data-type="edge-routers" data-id="${escapeHtml(item.id)}">${workload ? "重新部署 K8s" : "部署到 K8s"}</button>
                ${
                  workload
                    ? `<button class="button-muted" data-action="undeploy-k8s-router" data-type="edge-routers" data-id="${escapeHtml(item.id)}">删除 K8s 部署</button>`
                    : ""
                }
                <button class="button-muted" data-action="re-enroll" data-type="edge-routers" data-id="${escapeHtml(item.id)}">重签 JWT</button>
                <button class="button-muted" data-action="edit" data-type="edge-routers" data-id="${escapeHtml(item.id)}">编辑</button>
                <button class="button-muted" data-action="delete" data-type="edge-routers" data-id="${escapeHtml(item.id)}">删除</button>
              </div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderServices() {
  const items = sortByName(state.overview.services);
  if (!items.length) {
    renderEmpty("当前还没有服务。");
    return;
  }
  refs.contentPanel.innerHTML = renderContentSection(
    "服务关系总览",
    "Service Map",
    "每张卡片都按“客户端入口 → Ziti service → 托管出口”来展开，方便一眼看懂到底是谁在访问谁、谁在托管谁、最终落到哪个后端。",
    `<div class="resource-grid">${items.map((item) => renderServiceFlow(item)).join("")}</div>`,
  );
}

function renderConfigs() {
  const items = sortByName(state.overview.configs);
  if (!items.length) {
    renderEmpty("当前还没有配置。");
    return;
  }
  const interceptConfigs = items.filter((item) => classifyConfigType(getConfigTypeName(item)) === "intercept");
  const hostConfigs = items.filter((item) => classifyConfigType(getConfigTypeName(item)) === "host");
  const otherConfigs = items.filter((item) => classifyConfigType(getConfigTypeName(item)) === "other");

  const renderConfigCard = (item) => {
    const configTypeName = getConfigTypeName(item);
    const usageType = classifyConfigType(configTypeName);
    const usagePill =
      usageType === "intercept" ? '<span class="pill">Dial 侧</span>' : usageType === "host" ? '<span class="pill">Bind 侧</span>' : "";
    return `
      <article class="resource-card">
        <div class="card-header">
          <div>
            <div class="card-title">${escapeHtml(item.name || item.id)}</div>
            <div class="card-subtitle mono">${escapeHtml(item.id)}</div>
          </div>
          <div class="pill-row">
            ${usagePill}
            <span class="pill ${isDeprecatedConfigType(configTypeName) ? "warn" : ""}">${escapeHtml(configTypeName)}</span>
          </div>
        </div>
        <div class="meta-row">
          <span class="meta-label">Config Type ID</span>
          <strong class="mono">${escapeHtml(item.configTypeId || "-")}</strong>
        </div>
        ${buildConfigTypeDocNote(configTypeName)}
        ${renderConfigUsage(item)}
        ${renderJsonBlock(item.data || {})}
        <div class="pill-row">
          ${renderPillList(tagsToList(item.tags), "无 tags")}
        </div>
        <div class="card-actions">
          <button class="button-muted" data-action="edit" data-type="configs" data-id="${escapeHtml(item.id)}">编辑</button>
          <button class="button-muted" data-action="delete" data-type="configs" data-id="${escapeHtml(item.id)}">删除</button>
        </div>
      </article>
    `;
  };

  refs.contentPanel.innerHTML = `
    <div class="content-stack">
      ${renderResourceSection(
        "客户端拦截 / Dial 侧",
        "Intercept",
        "这些配置决定客户端会拦截哪些 Ziti 域名和端口，也就是“用户看见什么地址”。",
        interceptConfigs.map((item) => renderConfigCard(item)),
        "还没有 intercept.v1 配置。",
      )}
      ${renderResourceSection(
        "服务托管 / Bind 侧",
        "Host",
        "这些配置决定服务最终转发到哪里，通常会落到某个 k8s Service 或内部地址。",
        hostConfigs.map((item) => renderConfigCard(item)),
        "还没有 host.v1 / host.v2 配置。",
      )}
      ${renderResourceSection(
        "其他配置",
        "Other",
        "这里保留自定义或较少使用的 config type，适合直接结合原始 JSON 查看。",
        otherConfigs.map((item) => renderConfigCard(item)),
        "当前没有其他配置。",
      )}
    </div>
  `;
}

function renderServicePolicies() {
  const items = sortByName(state.overview.service_policies);
  if (!items.length) {
    renderEmpty("当前还没有服务策略。");
    return;
  }
  const renderPolicyCard = (item) => {
    const matchedIdentities = getMatchedIdentitiesForPolicy(item);
    const matchedServices = getMatchedServicesForPolicy(item);
    const summary =
      String(item.type || "") === "Bind" ? "这些身份可以托管这些服务。" : "这些身份可以访问这些服务。";
    return `
      <article class="resource-card">
        <div class="card-header">
          <div>
            <div class="card-title">${escapeHtml(item.name)}</div>
            <div class="card-subtitle mono">${escapeHtml(item.id)}</div>
          </div>
          <span class="pill">${escapeHtml(item.type || "-")}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">Semantic</span>
          <strong>${escapeHtml(item.semantic || "-")}</strong>
        </div>
        <p class="text-helper">${escapeHtml(summary)}</p>
        <div class="relation-stack">
          <section class="relation-block">
            <span class="relation-kicker">Role 表达式</span>
            <strong>原始身份 / 服务匹配条件</strong>
            <div class="pill-row">
              ${renderPillList(item.identityRoles, "无 identity roles")}
            </div>
            <div class="pill-row">
              ${renderPillList(item.serviceRoles, "无 service roles")}
            </div>
          </section>
          <section class="relation-block">
            <span class="relation-kicker">当前命中</span>
            <strong>按现有 controller 资源计算后的匹配结果</strong>
            <div class="pill-row">
              ${renderEntityPills(matchedIdentities, "当前没有命中的身份")}
            </div>
            <div class="pill-row">
              ${renderEntityPills(matchedServices, "当前没有命中的服务")}
            </div>
          </section>
        </div>
        <div class="card-actions">
          <button class="button-muted" data-action="edit" data-type="service-policies" data-id="${escapeHtml(item.id)}">编辑</button>
          <button class="button-muted" data-action="delete" data-type="service-policies" data-id="${escapeHtml(item.id)}">删除</button>
        </div>
      </article>
    `;
  };

  const dialPolicies = items.filter((item) => String(item.type || "").trim() === "Dial");
  const bindPolicies = items.filter((item) => String(item.type || "").trim() === "Bind");

  refs.contentPanel.innerHTML = `
    <div class="content-stack">
      ${renderResourceSection(
        "Dial 策略",
        "Dial",
        "客户端访问服务的权限。这里会同时展示原始 role 表达式和当前命中的身份 / 服务。",
        dialPolicies.map((item) => renderPolicyCard(item)),
        "还没有 Dial 类型的服务策略。",
      )}
      ${renderResourceSection(
        "Bind 策略",
        "Bind",
        "托管端发布服务的权限。适合快速看出是谁在负责托管哪个服务。",
        bindPolicies.map((item) => renderPolicyCard(item)),
        "还没有 Bind 类型的服务策略。",
      )}
    </div>
  `;
}

function renderEdgeRouterPolicies() {
  const items = sortByName(state.overview.edge_router_policies);
  if (!items.length) {
    renderEmpty("当前还没有路由器策略。");
    return;
  }
  refs.contentPanel.innerHTML = `
    <div class="resource-grid">
      ${items
        .map((item) => {
          const matchedIdentities = getMatchedIdentitiesForPolicy(item);
          const matchedRouters = getMatchedRoutersForPolicy(item);
          return `
            <article class="resource-card">
              <div class="card-header">
                <div>
                  <div class="card-title">${escapeHtml(item.name)}</div>
                  <div class="card-subtitle mono">${escapeHtml(item.id)}</div>
                </div>
                <span class="pill">${escapeHtml(item.semantic || "-")}</span>
              </div>
              <div class="pill-row">
                ${renderPillList(item.identityRoles, "无 identity roles")}
              </div>
              <div class="pill-row">
                ${renderPillList(item.edgeRouterRoles, "无 router roles")}
              </div>
              <div class="relation-stack">
                <section class="relation-block">
                  <span class="relation-kicker">当前命中身份</span>
                  <strong>${escapeHtml(matchedIdentities.length ? `${matchedIdentities.length} 个 identity` : "没有命中的身份")}</strong>
                  <div class="pill-row">
                    ${renderEntityPills(matchedIdentities, "没有命中的身份")}
                  </div>
                </section>
                <section class="relation-block">
                  <span class="relation-kicker">当前命中路由器</span>
                  <strong>${escapeHtml(matchedRouters.length ? `${matchedRouters.length} 台 router` : "没有命中的 router")}</strong>
                  <div class="pill-row">
                    ${renderEntityPills(matchedRouters, "没有命中的 router")}
                  </div>
                </section>
              </div>
              <div class="card-actions">
                <button class="button-muted" data-action="edit" data-type="edge-router-policies" data-id="${escapeHtml(item.id)}">编辑</button>
                <button class="button-muted" data-action="delete" data-type="edge-router-policies" data-id="${escapeHtml(item.id)}">删除</button>
              </div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderServiceEdgeRouterPolicies() {
  const items = sortByName(state.overview.service_edge_router_policies);
  if (!items.length) {
    renderEmpty("当前还没有服务接入策略。");
    return;
  }
  refs.contentPanel.innerHTML = `
    <div class="resource-grid">
      ${items
        .map((item) => {
          const matchedServices = getMatchedServicesForPolicy(item);
          const matchedRouters = getMatchedRoutersForPolicy(item);
          return `
            <article class="resource-card">
              <div class="card-header">
                <div>
                  <div class="card-title">${escapeHtml(item.name)}</div>
                  <div class="card-subtitle mono">${escapeHtml(item.id)}</div>
                </div>
                <span class="pill">${escapeHtml(item.semantic || "-")}</span>
              </div>
              <div class="pill-row">
                ${renderPillList(item.serviceRoles, "无 service roles")}
              </div>
              <div class="pill-row">
                ${renderPillList(item.edgeRouterRoles, "无 router roles")}
              </div>
              <div class="pill-row">
                ${renderPillList(tagsToList(item.tags), "无 tags")}
              </div>
              <div class="relation-stack">
                <section class="relation-block">
                  <span class="relation-kicker">当前命中服务</span>
                  <strong>${escapeHtml(matchedServices.length ? `${matchedServices.length} 个 service` : "没有命中的 service")}</strong>
                  <div class="pill-row">
                    ${renderEntityPills(matchedServices, "没有命中的 service")}
                  </div>
                </section>
                <section class="relation-block">
                  <span class="relation-kicker">当前命中路由器</span>
                  <strong>${escapeHtml(matchedRouters.length ? `${matchedRouters.length} 台 router` : "没有命中的 router")}</strong>
                  <div class="pill-row">
                    ${renderEntityPills(matchedRouters, "没有命中的 router")}
                  </div>
                </section>
              </div>
              <div class="card-actions">
                <button class="button-muted" data-action="edit" data-type="service-edge-router-policies" data-id="${escapeHtml(item.id)}">编辑</button>
                <button class="button-muted" data-action="delete" data-type="service-edge-router-policies" data-id="${escapeHtml(item.id)}">删除</button>
              </div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function getIdentityProfile(item, dialServices, bindServices) {
  const isAdmin = Boolean(item?.isAdmin);
  if (dialServices.length && bindServices.length) {
    return {
      bucket: "dual",
      title: isAdmin ? "双角色管理员" : "双角色身份",
      summary: "既能作为客户端访问服务，也能作为托管端对外发布服务。",
      pillClass: "",
    };
  }
  if (dialServices.length) {
    return {
      bucket: "client",
      title: isAdmin ? "客户端管理员" : "客户端身份",
      summary: "主要拿来访问服务，常见用法是签发客户端 JWT 然后入网。",
      pillClass: "",
    };
  }
  if (bindServices.length) {
    return {
      bucket: "host",
      title: isAdmin ? "托管管理员" : "托管身份",
      summary: "主要拿来托管服务，把 Ziti 流量转到后端。",
      pillClass: "",
    };
  }
  return {
    bucket: "other",
    title: isAdmin ? "管理员身份" : "普通身份",
    summary: "当前还没有命中任何 Dial / Bind 服务，通常需要再补策略或角色属性。",
    pillClass: isAdmin ? "" : "offline",
  };
}

function renderIdentityCard(item) {
  const roleAttributes = ensureArray(item.roleAttributes);
  const updb = item.authenticators?.updb?.username || "-";
  const ottEnrollment = getLatestIdentityEnrollment(item.id, "ott");
  const dialServices = getMatchedDialServicesForIdentity(item);
  const bindServices = getMatchedBindServicesForIdentity(item);
  const routers = getMatchedRoutersForIdentity(item);
  const profile = getIdentityProfile(item, dialServices, bindServices);

  return `
    <article class="resource-card identity-card">
      <div class="card-header card-header-top">
        <div class="card-header-copy">
          <div class="card-title">${escapeHtml(item.name)}</div>
          <div class="card-subtitle mono">${escapeHtml(item.id)}</div>
        </div>
        <div class="pill-row">
          <span class="pill ${profile.pillClass}">${escapeHtml(profile.title)}</span>
          <span class="pill ${item.isAdmin ? "" : "offline"}">${item.isAdmin ? "管理员" : "普通权限"}</span>
          <span class="pill ${item.disabled ? "warn" : ""}">${item.disabled ? "禁用" : "启用"}</span>
        </div>
      </div>
      <div class="identity-hero">
        <div>
          <span class="relation-kicker">身份定位</span>
          <strong>${escapeHtml(profile.title)}</strong>
        </div>
        <p>${escapeHtml(profile.summary)}</p>
      </div>
      <div class="identity-summary-grid">
        <div class="identity-summary-card">
          <span>可 Dial</span>
          <strong>${escapeHtml(String(dialServices.length))}</strong>
          <small>当前可访问的服务</small>
        </div>
        <div class="identity-summary-card">
          <span>可 Bind</span>
          <strong>${escapeHtml(String(bindServices.length))}</strong>
          <small>当前可托管的服务</small>
        </div>
        <div class="identity-summary-card">
          <span>可用 Router</span>
          <strong>${escapeHtml(String(routers.length))}</strong>
          <small>当前可以连接的路由器</small>
        </div>
      </div>
      <div class="meta-grid">
        <div class="meta-card">
          <span class="meta-label">UPDB 用户名</span>
          <strong>${escapeHtml(updb)}</strong>
        </div>
        <div class="meta-card">
          <span class="meta-label">认证策略</span>
          <strong>${escapeHtml(item.authPolicy?.name || item.authPolicyId || "-")}</strong>
        </div>
        <div class="meta-card">
          <span class="meta-label">客户端 Enrollment</span>
          <strong>${escapeHtml(ottEnrollment ? `ott · ${formatDate(ottEnrollment.expiresAt)}` : "-")}</strong>
        </div>
      </div>
      <div class="relation-grid">
        <section class="relation-block">
          <span class="relation-kicker">客户端侧 / Dial</span>
          <strong>${escapeHtml(dialServices.length ? `${dialServices.length} 个 service` : "当前没有 Dial 权限")}</strong>
          <div class="pill-row">
            ${renderEntityPills(dialServices, "当前没有可访问的 service")}
          </div>
        </section>
        <section class="relation-block">
          <span class="relation-kicker">托管侧 / Bind</span>
          <strong>${escapeHtml(bindServices.length ? `${bindServices.length} 个 service` : "当前没有 Bind 权限")}</strong>
          <div class="pill-row">
            ${renderEntityPills(bindServices, "当前没有可托管的 service")}
          </div>
        </section>
        <section class="relation-block">
          <span class="relation-kicker">Router</span>
          <strong>${escapeHtml(routers.length ? `${routers.length} 台 router` : "当前没有可用 router")}</strong>
          <div class="pill-row">
            ${renderEntityPills(routers, "当前没有可用的 router")}
          </div>
        </section>
      </div>
      <div class="pill-row">
        ${renderPillList(roleAttributes, "无角色属性")}
      </div>
      ${ottEnrollment ? '<div class="pill-row"><span class="pill warn">有待使用的客户端 JWT</span></div>' : ""}
      <div class="card-actions">
        <button class="button-muted" data-action="identity-jwt" data-type="identities" data-id="${escapeHtml(item.id)}">客户端 JWT</button>
        <button class="button-muted" data-action="identity-jwt-rotate" data-type="identities" data-id="${escapeHtml(item.id)}">重签 JWT</button>
        <button class="button-muted" data-action="edit" data-type="identities" data-id="${escapeHtml(item.id)}">编辑</button>
        <button class="button-muted" data-action="delete" data-type="identities" data-id="${escapeHtml(item.id)}">删除</button>
      </div>
    </article>
  `;
}

function renderIdentities() {
  const items = sortByName(state.overview.identities);
  if (!items.length) {
    renderEmpty("当前还没有身份。");
    return;
  }
  const clientItems = [];
  const hostItems = [];
  const dualItems = [];
  const otherItems = [];

  items.forEach((item) => {
    const dialServices = getMatchedDialServicesForIdentity(item);
    const bindServices = getMatchedBindServicesForIdentity(item);
    const profile = getIdentityProfile(item, dialServices, bindServices);
    if (profile.bucket === "client") {
      clientItems.push(item);
      return;
    }
    if (profile.bucket === "host") {
      hostItems.push(item);
      return;
    }
    if (profile.bucket === "dual") {
      dualItems.push(item);
      return;
    }
    otherItems.push(item);
  });

  refs.contentPanel.innerHTML = `
    <div class="content-stack">
      ${renderResourceSection(
        "客户端身份",
        "Dial Identity",
        "这些身份主要负责访问服务。最常见的动作是签发客户端 JWT，再在客户端执行 enroll 生成 JSON 身份。",
        clientItems.map((item) => renderIdentityCard(item)),
        "当前没有只负责 Dial 的身份。",
      )}
      ${renderResourceSection(
        "托管身份",
        "Bind Identity",
        "这些身份主要负责托管服务，也就是把 Ziti 流量真正转发到后端。",
        hostItems.map((item) => renderIdentityCard(item)),
        "当前没有只负责 Bind 的身份。",
      )}
      ${renderResourceSection(
        "双角色身份",
        "Dial + Bind",
        "这些身份同时能访问服务，也能托管服务，适合测试或一体化节点。",
        dualItems.map((item) => renderIdentityCard(item)),
        "当前没有双角色身份。",
      )}
      ${renderResourceSection(
        "其他身份",
        "Other",
        "这里通常是管理员身份，或者暂时还没有命中任何策略的普通身份。",
        otherItems.map((item) => renderIdentityCard(item)),
        "当前没有其他身份。",
      )}
    </div>
  `;
}

export function renderWorkspace() {
  renderSession();
  renderJwtPanel();
  renderStats();
  renderWorkspaceGuide();

  refs.tabButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tab === state.activeTab);
  });

  const showAliveToggle = state.activeTab === "edge-routers";
  refs.aliveOnlyLabel.classList.toggle("hidden", !showAliveToggle);
  refs.aliveOnlyCheckbox.checked = state.aliveOnly;

  if (!state.session) {
    refs.addEntityButton.disabled = true;
    refs.workspaceGuide.innerHTML = "";
    refs.contentPanel.innerHTML = `
      <div class="empty-state">
        <h3>先登录 controller</h3>
        <p>输入 controller 地址、用户名和密码后，页面会加载路由器、服务、配置、策略和身份数据。</p>
      </div>
    `;
    return;
  }

  refs.addEntityButton.disabled = state.busy;

  if (!state.overview) {
    refs.workspaceGuide.innerHTML = "";
    refs.contentPanel.innerHTML = `
      <div class="empty-state">
        <h3>正在读取数据</h3>
        <p>controller 会话已建立，正在拉取资源列表。</p>
      </div>
    `;
    return;
  }

  const addButtonLabels = {
    configs: "新增配置",
    "edge-routers": "新增路由器",
    "edge-router-policies": "新增路由器策略",
    identities: "新增身份",
    "service-edge-router-policies": "新增服务接入策略",
    "service-policies": "新增服务策略",
    services: "新增服务",
  };
  refs.addEntityButton.textContent = addButtonLabels[state.activeTab] || "新增";

  if (state.activeTab === "edge-routers") {
    renderRouters();
    return;
  }
  if (state.activeTab === "services") {
    renderServices();
    return;
  }
  if (state.activeTab === "configs") {
    renderConfigs();
    return;
  }
  if (state.activeTab === "service-policies") {
    renderServicePolicies();
    return;
  }
  if (state.activeTab === "edge-router-policies") {
    renderEdgeRouterPolicies();
    return;
  }
  if (state.activeTab === "service-edge-router-policies") {
    renderServiceEdgeRouterPolicies();
    return;
  }
  renderIdentities();
}
