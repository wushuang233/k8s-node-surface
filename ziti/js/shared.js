export const refs = {
  errorBanner: document.querySelector("#error-banner"),
  loginForm: document.querySelector("#login-form"),
  controllerUrl: document.querySelector("#controller-url"),
  username: document.querySelector("#username"),
  password: document.querySelector("#password"),
  loginButton: document.querySelector("#login-button"),
  logoutButton: document.querySelector("#logout-button"),
  refreshButton: document.querySelector("#refresh-button"),
  sessionState: document.querySelector("#session-state"),
  sessionController: document.querySelector("#session-controller"),
  sessionIdentity: document.querySelector("#session-identity"),
  sessionExpiry: document.querySelector("#session-expiry"),
  jwtPanel: document.querySelector("#jwt-panel"),
  jwtTitle: document.querySelector("#jwt-title"),
  jwtNote: document.querySelector("#jwt-note"),
  jwtCommandPanel: document.querySelector("#jwt-command-panel"),
  jwtCommandOutput: document.querySelector("#jwt-command-output"),
  jwtEnrollPanel: document.querySelector("#jwt-enroll-panel"),
  jwtEnrollOutput: document.querySelector("#jwt-enroll-output"),
  jwtOutput: document.querySelector("#jwt-output"),
  copyJwtCommandButton: document.querySelector("#copy-jwt-command-button"),
  copyJwtEnrollButton: document.querySelector("#copy-jwt-enroll-button"),
  copyJwtButton: document.querySelector("#copy-jwt-button"),
  clearJwtButton: document.querySelector("#clear-jwt-button"),
  tabButtons: Array.from(document.querySelectorAll(".tab-button")),
  aliveOnlyLabel: document.querySelector("#alive-only-label"),
  aliveOnlyCheckbox: document.querySelector("#alive-only-checkbox"),
  addEntityButton: document.querySelector("#add-entity-button"),
  workspaceGuide: document.querySelector("#workspace-guide"),
  statsStrip: document.querySelector("#stats-strip"),
  contentPanel: document.querySelector("#content-panel"),
  dialog: document.querySelector("#entity-dialog"),
  dialogKicker: document.querySelector("#dialog-kicker"),
  dialogTitle: document.querySelector("#dialog-title"),
  dialogBody: document.querySelector("#dialog-body"),
  dialogCommandPreview: document.querySelector("#dialog-command-preview"),
  dialogSubmitButton: document.querySelector("#dialog-submit-button"),
  dialogCloseButton: document.querySelector("#dialog-close-button"),
  dialogCancelButton: document.querySelector("#dialog-cancel-button"),
  entityForm: document.querySelector("#entity-form"),
};

export const state = {
  session: null,
  overview: null,
  activeTab: "configs",
  aliveOnly: true,
  busy: false,
  lastJwt: null,
  modal: null,
};

export const resourceLabels = {
  configs: "配置",
  "edge-routers": "路由器",
  "edge-router-policies": "路由器策略",
  identities: "身份",
  "service-edge-router-policies": "服务接入策略",
  "service-policies": "服务策略",
  services: "服务",
};

export const workspaceGuides = {
  configs: {
    title: "先定义客户端看到什么，再定义流量真正转到哪里",
    summary: "大多数新服务都先建两条配置：intercept.v1 负责客户端要访问的域名，host.v1 负责路由器最终转发到哪个后端。",
    pills: ["推荐顺序 1/7", "先做配置最省心", "JSON 入口在弹窗顶部"],
    steps: [
      "intercept.v1：告诉客户端拦截哪个 Ziti 域名和端口。",
      "host.v1：默认优先代理到 Kubernetes Service，也保留自定义地址写法。",
      "原始 Data JSON 在配置弹窗里的“查看原始 JSON / 复制 JSON”。",
    ],
    note: "如果你是发布一个 k8s 里的 Web 服务，通常先建一个 intercept.v1，再建一个 host.v1，下一步去“服务”标签把它们绑到同一个 service 上。",
  },
  services: {
    title: "把前面建好的 config 绑成一个可发布的 Ziti service",
    summary: "service 本身不负责访问权限，它更像服务对象本体。常见做法是绑定一个 intercept.v1 和一个 host.v1。",
    pills: ["推荐顺序 2/7", "先绑 config 再配策略", "页面直接创建"],
    steps: [
      "至少选中一个 intercept 配置和一个 host 配置。",
      "Terminator Strategy 大多数情况保留 smartrouting 即可。",
      "如果不确定参数，先只填名称和 configs，其余字段保持默认；点击创建后页面会直接提交到 controller。",
    ],
    note: "完成 service 后，先别急着让用户访问，接下来去“身份”和“服务策略”把客户端、托管端、访问权限补齐。",
  },
  identities: {
    title: "给客户端和托管端分别创建 identity",
    summary: "普通客户端通常用客户端 JWT 入网；如果你要用用户名密码登录，再额外填写 UPDB 用户名。页面现在把客户端 JWT 做成了显式按钮。",
    pills: ["推荐顺序 3/7", "客户端 JWT 在身份卡片上", "创建时也可立即生成"],
    steps: [
      "创建客户端身份后，点身份卡片里的“客户端 JWT”即可查看或生成 JWT。",
      "如果要换一条新的 JWT，用“重签 JWT”；旧的未完成 enrollment 会失效。",
      "Auth Policy、Hosting Cost 这些字段不熟就先保留默认值；页面会直接完成创建，不需要你手敲命令。",
    ],
    note: "如果你只是想先让一个客户端能访问服务，最小路径就是：创建 identity -> 生成客户端 JWT -> 去“服务策略”里给它 Dial 权限。",
  },
  "service-policies": {
    title: "决定谁能访问服务，谁能托管服务",
    summary: "Service Policy 最常见就是两类：Dial 表示谁能访问服务，Bind 表示谁能托管服务。",
    pills: ["推荐顺序 4/7", "Dial 给客户端", "Bind 给托管端"],
    steps: [
      "身份、服务字段都支持从现有资源里下拉追加，也保留原始 role 语法。",
      "大多数简单场景保持 semantic=AnyOf 就够了。",
      "看不懂某个参数时，先点字段右侧 Help；下方命令只是参考，真正的创建 / 编辑 / 删除都由页面直接执行。",
    ],
    note: "常见发布路径里，客户端身份一般放到 Dial，托管端身份一般放到 Bind。",
  },
  "service-edge-router-policies": {
    title: "决定哪些服务可以走哪些 edge router",
    summary: "如果你的服务需要明确绑定到某些 router，这里就是最直接的入口。大多数情况下只要选中 service 和 router 即可。",
    pills: ["推荐顺序 5/7", "服务到 router 的映射", "不会替代 service policy"],
    steps: [
      "服务角色和路由器角色都可以直接下拉现有资源。",
      "如果只是单 router 场景，通常选中那台 router 就够了。",
      "这一层关注的是服务和 router 的连通关系，不是客户端权限。",
    ],
    note: "如果你当前只有一台 router，最简单的写法就是把目标 service 和这台 router 连起来。",
  },
  "edge-router-policies": {
    title: "决定哪些身份能通过哪些 edge router",
    summary: "这一层是身份到 router 的使用权限。多 router 网络里会更常用；单 router 网络通常也建议显式配一条，后面排障更直观。",
    pills: ["推荐顺序 6/7", "身份到 router 的权限", "角色语法可直接下拉"],
    steps: [
      "Identity Roles 选身份，Edge Router Roles 选 router。",
      "如果你只想让一组客户端走指定 router，可以优先用角色属性 #attr 来批量匹配。",
      "和服务接入策略不同，这里控制的是“谁能走这台 router”。",
    ],
    note: "如果用户已经能拿到 JWT 但就是连不上 router，这里通常是第一批要检查的地方之一。",
  },
  "edge-routers": {
    title: "最后把 router 真的跑起来，并确认它已经在线",
    summary: "这里不只看 controller 里的 router 记录，还会直接显示它有没有在 K8s 里跑成 Deployment，以及当前 NodePort 和宿主机地址。",
    pills: ["推荐顺序 7/7", "直接部署到 K8s", "重签 JWT 也在这里"],
    steps: [
      "在线 + 已验证 + SYNC_DONE，通常说明 router 自身没问题。",
      "如果某条 router 只是 controller 记录、还没跑起来，直接点“部署到 K8s”。",
      "如果 router 换实例或重新入网，可以点“重新部署 K8s”或“重签 JWT”。",
    ],
    note: "如果你觉得服务配置都对但还是不通，先回到这里看 router 有没有 K8s 工作负载、有没有在线，通常能最快缩小范围。",
  },
};

const deprecatedConfigTypeNotes = {
  "ziti-tunneler-server.v1": "官方文档已标记 Deprecated，新的服务托管配置优先使用 host.v1 或 host.v2。",
  "ziti-tunneler-client.v1": "官方文档已标记 Deprecated，新的拦截配置优先使用 intercept.v1。",
  "ziti-tunneler-client-v1": "官方文档已标记 Deprecated，新的拦截配置优先使用 intercept.v1。",
};

const fieldHelpContent = {
  "common.name": ["资源的展示名称。大多数 Ziti CLI 的 create/update 命令都会直接用这个名字作为目标。"],
  "common.tags": ["给资源打上自定义标签，方便后续筛选或做额外标记。不是必填项。"],
  "common.roleAttributes": ["角色属性会被 #attr 这类 role 表达式引用，常用于策略批量匹配。多个值用逗号分隔。"],
  "common.semantic": [
    "官方文档里的策略 semantic 主要有 AnyOf 和 AllOf 两种。",
    "AnyOf 表示命中任意一条角色规则即可；AllOf 表示所有规则都要同时命中。",
  ],
  "router.cost": ["路由成本用于终结点选择。数字越小越容易被优先使用，默认 0 即可。"],
  "router.disabled": ["禁用后这台路由器不会再承接新的 Ziti 流量。"],
  "router.noTraversal": ["打开后，路由器不会作为 traversal 节点帮助其他路由器转发。私有路由器通常可以保持默认关闭。"],
  "router.tunneler": ["启用后，这台 edge router 还能作为 tunneler 类型的托管节点使用。"],
  "service.configs": [
    "服务通常至少会关联一个 intercept 配置和一个 host 配置。",
    "常见组合是 intercept.v1 + host.v1，或者 intercept.v1 + host.v2。",
  ],
  "service.terminatorStrategy": ["决定 controller 在多个 terminator 之间如何选路。官方默认值是 smartrouting，通常不用改。"],
  "service.maxIdleTime": ["连接空闲多久后由 controller 清理。页面允许你按 CLI 习惯填 30s、5m、1h，也会自动换成 API 需要的毫秒。"],
  "service.encryptionRequired": [
    "创建服务时默认要求端到端加密。",
    "官方 Edge Management API 里这个字段是创建时设置、更新时只读。",
  ],
  "config.type": [
    "Config Type 决定这条配置描述的是拦截规则还是托管目标。",
    "官方当前推荐 intercept.v1、host.v1、host.v2；ziti-tunneler-* 已经 deprecated。",
  ],
  "config.hostMode": [
    "host.v1 用来告诉路由器把流量真正转发到哪里。",
    "Kubernetes Service 模式会自动拼出 service.namespace.svc.cluster.local，而不是直接把 ClusterIP 写进配置里。",
    "如果托管端本身也运行了 Ziti 客户端并接管 DNS，个别环境里可能还需要给 hosting pod 增加同名 hostAliases，避免 *.svc.cluster.local 被错误拦截。",
    "自定义地址模式则直接使用你输入的域名或 IP。",
  ],
  "config.namespace": ["优先从当前集群里已有的 namespace 中选择，也可以继续手输。"],
  "config.serviceName": ["这里建议直接选 k8s Service 名称。面板会额外展示它所在 namespace、Service 类型和端口信息。"],
  "config.port": ["目标服务端口。选中某个 k8s Service 后，面板会优先给出它真实暴露的端口建议。"],
  "config.protocol": ["host/intercept 配置常见是 tcp；只有你的后端服务本身就是 UDP 时才改成 udp。"],
  "config.address": ["自定义模式下填真实后端地址，可以是集群外域名、IP，或者你自己维护的内部域名。"],
  "config.interceptAddresses": [
    "这是客户端要拦截的 Ziti 域名或地址列表。",
    "常见场景先填一个如 port-audit.ziti 即可，也支持一行一个或逗号分隔多个地址。",
  ],
  "policy.type": ["Service Policy 的类型通常是 Dial 或 Bind。Dial 控制谁能访问服务，Bind 控制谁能托管服务。"],
  "policy.identityRoles": ["支持 @名称、@ID、#角色属性、#all。服务策略和路由器策略都是通过它来选中身份集合。"],
  "policy.serviceRoles": ["支持 @服务名、@服务ID、#角色属性、#all，用来决定策略作用到哪些服务。"],
  "policy.edgeRouterRoles": ["支持 @路由器名、@路由器ID、#角色属性、#all，用来决定策略作用到哪些路由器。"],
  "policy.postureCheckRoles": ["只有当你需要姿态校验时再配置。默认留空即可，#all 表示套用所有 posture checks。"],
  "identity.updbUsername": ["创建 identity 时，如果要顺手创建一个 UPDB 登录名，就在这里填。编辑已有 identity 时留空表示不变。"],
  "identity.isAdmin": ["管理员身份可以管理整个 edge 网络资源。普通业务身份一般不要勾选。"],
  "identity.authPolicyId": ["身份使用哪条认证策略。默认通常是 default，也可以选 controller 里现有的 auth policy。"],
  "identity.externalId": ["如果要把 identity 和外部系统主键做映射，可以在这里保存 externalId。"],
  "identity.defaultHostingCost": ["当这个 identity 作为服务托管方时使用的默认成本，默认 0 即可。"],
  "identity.defaultHostingPrecedence": ["当同一个服务有多个托管节点时，用它控制优先级。大多数情况保留 default。"],
  "identity.generateClientJwt": ["勾选后，页面会在创建 identity 成功后立刻补一条 OTT enrollment，并把客户端 JWT 直接展示在顶部面板。"],
};

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function showError(message) {
  refs.errorBanner.textContent = message;
  refs.errorBanner.classList.remove("hidden");
}

export function clearError() {
  refs.errorBanner.textContent = "";
  refs.errorBanner.classList.add("hidden");
}

export function formatDate(value) {
  if (!value) {
    return "-";
  }
  if (typeof value === "string" && value.startsWith("0001-01-01")) {
    return "-";
  }
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

export function formatJson(value) {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch (_error) {
    return "{}";
  }
}

export function ensureArray(value) {
  return Array.isArray(value) ? value.filter(Boolean) : [];
}

export function tagsToList(tags) {
  if (!tags || typeof tags !== "object") {
    return [];
  }
  return Object.entries(tags).map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`);
}

export function renderPillList(values, emptyText, extraClass = "") {
  const items = ensureArray(values);
  if (!items.length) {
    return `<span class="pill ${extraClass}">${escapeHtml(emptyText)}</span>`;
  }
  return items.map((value) => `<span class="pill ${extraClass}">${escapeHtml(value)}</span>`).join("");
}

export function renderJsonBlock(value) {
  return `<pre class="json-block mono">${escapeHtml(formatJson(value))}</pre>`;
}

export function flashButtonText(button, successText = "已复制", durationMs = 1400) {
  if (!(button instanceof HTMLElement)) {
    return;
  }
  const originalText = button.dataset.originalText || button.textContent || "";
  button.dataset.originalText = originalText;
  button.textContent = successText;
  window.setTimeout(() => {
    if (button.isConnected) {
      button.textContent = originalText;
    }
  }, durationMs);
}

export async function copyText(text, button = null, failureMessage = "复制失败，请手动复制。") {
  const normalized = String(text ?? "");
  if (!normalized) {
    return false;
  }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(normalized);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = normalized;
      textarea.setAttribute("readonly", "readonly");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    flashButtonText(button);
    return true;
  } catch (_error) {
    showError(failureMessage);
    return false;
  }
}

export function getConfigs() {
  return ensureArray(state.overview?.configs);
}

export function getServices() {
  return ensureArray(state.overview?.services);
}

export function getServicePolicies() {
  return ensureArray(state.overview?.service_policies);
}

export function getEdgeRouterPolicies() {
  return ensureArray(state.overview?.edge_router_policies);
}

export function getServiceEdgeRouterPolicies() {
  return ensureArray(state.overview?.service_edge_router_policies);
}

export function getConfigTypes() {
  return ensureArray(state.overview?.config_types);
}

export function getIdentities() {
  return ensureArray(state.overview?.identities);
}

export function getPostureChecks() {
  return ensureArray(state.overview?.posture_checks);
}

export function getAuthPolicies() {
  return ensureArray(state.overview?.auth_policies);
}

export function getEdgeRouters() {
  return ensureArray(state.overview?.edge_routers);
}

export function getEnrollments() {
  return ensureArray(state.overview?.enrollments);
}

export function getK8sServices() {
  return ensureArray(state.overview?.k8s_services);
}

export function getLatestIdentityEnrollment(identityId, method = "ott") {
  const targetIdentityId = String(identityId || "").trim();
  if (!targetIdentityId) {
    return null;
  }
  return (
    getEnrollments()
      .filter((item) => String(item?.identityId || "").trim() === targetIdentityId)
      .filter((item) => String(item?.method || "").trim().toLowerCase() === String(method).toLowerCase())
      .sort((left, right) => String(right?.expiresAt || "").localeCompare(String(left?.expiresAt || "")))[0] || null
  );
}

export function getConfigMap() {
  return new Map(getConfigs().map((item) => [item.id, item]));
}

export function getConfigTypeName(config) {
  return config?.configType?.name || config?.configTypeId || "-";
}

export function describeConfigReference(configId) {
  const config = getConfigMap().get(configId);
  if (!config) {
    return configId;
  }
  return `${config.name} (${getConfigTypeName(config)})`;
}

export function configOptionsHtml(selectedIds = []) {
  const selected = new Set(ensureArray(selectedIds));
  const configs = getConfigs();
  if (!configs.length) {
    return '<option value="" disabled>当前没有可用 config</option>';
  }
  return configs
    .map((config) => {
      const label = `${config.name} (${getConfigTypeName(config)})`;
      return `<option value="${escapeHtml(config.id)}" ${selected.has(config.id) ? "selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
}

export function configTypeOptionsHtml(selectedId) {
  const configTypes = getConfigTypes();
  return configTypes
    .map((configType, index) => {
      const isSelected = selectedId ? configType.id === selectedId : index === 0;
      const suffix = isDeprecatedConfigType(configType.name) ? " · Deprecated" : configType.name === "host.v2" ? " · 推荐" : "";
      return `<option value="${escapeHtml(configType.id)}" ${isSelected ? "selected" : ""}>${escapeHtml(configType.name)}${escapeHtml(suffix)} (${escapeHtml(configType.id)})</option>`;
    })
    .join("");
}

export function cloneJson(value) {
  if (!value || typeof value !== "object") {
    return {};
  }
  try {
    return JSON.parse(JSON.stringify(value));
  } catch (_error) {
    return {};
  }
}

function getConfigTypeById(configTypeId) {
  return getConfigTypes().find((item) => item.id === configTypeId) || null;
}

export function getConfigTypeNameById(configTypeId) {
  return getConfigTypeById(configTypeId)?.name || "";
}

export function isDeprecatedConfigType(typeName) {
  return Boolean(deprecatedConfigTypeNotes[String(typeName || "").trim()]);
}

export function getConfigTypeDocNote(typeName) {
  const currentType = String(typeName || "").trim();
  if (!currentType) {
    return "";
  }
  if (deprecatedConfigTypeNotes[currentType]) {
    return deprecatedConfigTypeNotes[currentType];
  }
  if (currentType === "host.v1") {
    return "官方文档里 host.v1 仍然是当前可用类型，适合单个目标地址；如果需要多个后端终结点，优先改用 host.v2。";
  }
  if (currentType === "host.v2") {
    return "官方文档里 host.v2 用于多个托管终结点；当前页面先提供 JSON 模式，但会给你预置推荐模板。";
  }
  if (currentType === "intercept.v1") {
    return "官方文档里 intercept.v1 仍是当前推荐的 tunneler 拦截配置类型。";
  }
  return "";
}

export function buildConfigTypeDocNote(configTypeName) {
  const note = getConfigTypeDocNote(configTypeName);
  if (!note) {
    return "";
  }
  return `<p class="text-helper ${isDeprecatedConfigType(configTypeName) ? "is-warn" : ""}">${escapeHtml(note)}</p>`;
}

function getFieldHelpParagraphs(helpKey) {
  return ensureArray(fieldHelpContent[String(helpKey || "").trim()]);
}

function buildFieldHelp(helpKey) {
  const paragraphs = getFieldHelpParagraphs(helpKey);
  if (!paragraphs.length) {
    return "";
  }
  return `
    <details class="field-help">
      <summary>Help</summary>
      <div class="field-help-popover">
        ${paragraphs.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join("")}
      </div>
    </details>
  `;
}

export function buildFieldLabel(labelText, helpKey = "") {
  return `
    <span class="field-label-row">
      <span class="field-label-text">${escapeHtml(labelText)}</span>
      ${buildFieldHelp(helpKey)}
    </span>
  `;
}

export function buildToggleField(fieldName, labelText, checked, helpKey = "") {
  return `
    <div class="toggle-row">
      <label class="toggle-chip">
        <input name="${fieldName}" type="checkbox" ${checked ? "checked" : ""} />
        <span>${escapeHtml(labelText)}</span>
      </label>
      ${buildFieldHelp(helpKey)}
    </div>
  `;
}

export function formatDurationMillis(value) {
  if (value === null || value === undefined || value === "") {
    return "";
  }

  const text = String(value).trim();
  if (!text) {
    return "";
  }
  if (!/^\d+$/.test(text)) {
    return text;
  }

  const millis = Number.parseInt(text, 10);
  if (!Number.isFinite(millis) || millis <= 0) {
    return "0";
  }
  if (millis % 3600000 === 0) {
    return `${millis / 3600000}h`;
  }
  if (millis % 60000 === 0) {
    return `${millis / 60000}m`;
  }
  if (millis % 1000 === 0) {
    return `${millis / 1000}s`;
  }
  return `${millis}ms`;
}

export function getServiceMaxIdleInputValue(service) {
  if (!service || typeof service !== "object") {
    return "";
  }
  if (service.maxIdleTimeMillis !== undefined && service.maxIdleTimeMillis !== null && service.maxIdleTimeMillis !== "") {
    return formatDurationMillis(service.maxIdleTimeMillis);
  }
  return String(service.maxIdleTime || "").trim();
}

export function getServiceMaxIdleDisplay(service) {
  const text = getServiceMaxIdleInputValue(service);
  return text || "-";
}

export function buildAdvancedSection(content, helperText = "这些字段大多是可选的，只有你需要覆盖默认行为时再展开。") {
  if (!String(content || "").trim()) {
    return "";
  }
  return `
    <details class="advanced-section">
      <summary>高级选项</summary>
      <p class="text-helper">${escapeHtml(helperText)}</p>
      <div class="advanced-section-body">
        ${content}
      </div>
    </details>
  `;
}

function uniqueValues(values) {
  return [...new Set(ensureArray(values).map((value) => String(value ?? "").trim()).filter(Boolean))].sort((left, right) =>
    left.localeCompare(right, "zh-CN"),
  );
}

function getK8sNamespaces() {
  return uniqueValues(getK8sServices().map((item) => item.namespace));
}

function getK8sNamespaceOptions() {
  return getK8sNamespaces().map((namespace) => ({
    value: namespace,
    label: `${getK8sServicesInNamespace(namespace).length} 个 service`,
  }));
}

function getK8sServicesInNamespace(namespace = "") {
  const currentNamespace = String(namespace ?? "").trim();
  const items = getK8sServices().filter((item) => !currentNamespace || item.namespace === currentNamespace);
  return items.sort((left, right) => (left.name || "").localeCompare(right.name || "", "zh-CN"));
}

function findK8sService(namespace, serviceName) {
  const currentNamespace = String(namespace ?? "").trim();
  const currentServiceName = String(serviceName ?? "").trim();
  return getK8sServices().find((item) => item.namespace === currentNamespace && item.name === currentServiceName) || null;
}

export function getK8sServicePortOptions(namespace, serviceName) {
  const service = findK8sService(namespace, serviceName);
  if (!service) {
    return [];
  }
  return ensureArray(service.ports).map((port) => ({
    value: String(port.port ?? ""),
    label: `${String(port.protocol || "TCP").toLowerCase()}${port.name ? ` / ${port.name}` : ""}${port.target_port ? ` / target:${port.target_port}` : ""}`,
  }));
}

function normalizeSuggestionOption(option) {
  if (!option || typeof option !== "object") {
    const value = String(option ?? "").trim();
    return value
      ? {
          value,
          title: value,
          meta: "",
          keywords: value.toLowerCase(),
        }
      : null;
  }

  const value = String(option.value ?? "").trim();
  if (!value) {
    return null;
  }

  const title = String(option.title ?? option.name ?? option.value ?? "").trim() || value;
  const meta = String(option.meta ?? option.label ?? option.description ?? "").trim();
  const keywords = [value, title, meta, option.keywords]
    .flatMap((item) => ensureArray(Array.isArray(item) ? item : [item]))
    .map((item) => String(item ?? "").trim().toLowerCase())
    .filter(Boolean)
    .join(" ");

  return {
    value,
    title,
    meta,
    keywords,
  };
}

function sortSuggestionOptions(options = []) {
  return ensureArray(options)
    .map(normalizeSuggestionOption)
    .filter(Boolean)
    .sort((left, right) => {
      const titleOrder = String(left.title).localeCompare(String(right.title), "zh-CN");
      if (titleOrder !== 0) {
        return titleOrder;
      }
      return String(left.value).localeCompare(String(right.value), "zh-CN");
    });
}

function filterSuggestionOptions(options = [], query = "") {
  const normalizedQuery = String(query ?? "").trim().toLowerCase();
  if (!normalizedQuery) {
    return options;
  }
  return options.filter((option) => option.keywords.includes(normalizedQuery));
}

function roleAttributeOption(value, entityLabel) {
  return {
    value,
    title: value,
    meta: `${entityLabel}角色属性`,
  };
}

function collectRoleAttributes(items) {
  return uniqueValues(
    ensureArray(items).flatMap((item) => ensureArray(item?.roleAttributes).map((value) => `#${String(value ?? "").trim()}`)),
  );
}

function getEntityTypeLabel(item) {
  if (!item || typeof item !== "object") {
    return "";
  }
  if (typeof item.type === "string") {
    return item.type.trim();
  }
  if (item.type && typeof item.type === "object") {
    return String(item.type.name || item.type.id || "").trim();
  }
  return "";
}

function buildNamedEntitySuggestions(items, entityLabel) {
  return ensureArray(items)
    .flatMap((item) => {
      const name = String(item?.name || "").trim();
      const id = String(item?.id || "").trim();
      const status = item?.isOnline === true ? "online" : item?.isOnline === false ? "offline" : item?.disabled ? "disabled" : "";
      const notes = [status, getEntityTypeLabel(item)].filter(Boolean).join(" / ");
      const options = [];
      if (id) {
        options.push({
          value: `@${id}`,
          title: name || id,
          meta: [entityLabel, "推荐", "ID 匹配", id, notes].filter(Boolean).join(" / "),
        });
      }
      if (name) {
        options.push({
          value: `@${name}`,
          title: `${name}（名称写法）`,
          meta: [entityLabel, "备选", "名称匹配", id, notes].filter(Boolean).join(" / "),
        });
      }
      return options;
    })
    .filter(Boolean);
}

export function dedupeSuggestions(options = []) {
  const seen = new Set();
  return sortSuggestionOptions(ensureArray(options))
    .filter(Boolean)
    .filter((option) => {
      const value = String(option.value ?? "").trim();
      if (!value || seen.has(value)) {
        return false;
      }
      seen.add(value);
      return true;
    });
}

export function buildMatchedK8sServicePreview(namespace, serviceName) {
  const matchedService = findK8sService(namespace, serviceName);
  if (!matchedService) {
    return '<p class="text-helper">支持直接从 k8s 里现有的 namespace / service 下拉选择；如果下拉里没有，也可以继续手输自定义值。</p>';
  }

  return `
    <div class="preview-card">
      <span>匹配到的 K8s Service</span>
      <strong class="mono">${escapeHtml(`${matchedService.namespace}/${matchedService.name}`)}</strong>
      <span class="mono">${escapeHtml(matchedService.fqdn || "-")}</span>
      <div class="pill-row">
        <span class="pill">${escapeHtml(matchedService.type || "ClusterIP")}</span>
        ${matchedService.cluster_ip ? `<span class="pill">ClusterIP ${escapeHtml(matchedService.cluster_ip)}</span>` : ""}
        ${renderPillList(
          ensureArray(matchedService.ports).map((port) => `${String(port.protocol || "TCP").toLowerCase()}:${port.port}`),
          "无端口",
        )}
      </div>
    </div>
  `;
}

function getRoleSuggestions(fieldName) {
  if (fieldName === "identityRoles") {
    return dedupeSuggestions([
      { value: "#all", title: "#all", meta: "全部身份" },
      ...buildNamedEntitySuggestions(getIdentities(), "身份"),
      ...collectRoleAttributes(getIdentities()).map((value) => roleAttributeOption(value, "身份")),
    ]);
  }
  if (fieldName === "serviceRoles") {
    return dedupeSuggestions([
      { value: "#all", title: "#all", meta: "全部服务" },
      ...buildNamedEntitySuggestions(getServices(), "服务"),
      ...collectRoleAttributes(getServices()).map((value) => roleAttributeOption(value, "服务")),
    ]);
  }
  if (fieldName === "edgeRouterRoles") {
    return dedupeSuggestions([
      { value: "#all", title: "#all", meta: "全部路由器" },
      ...buildNamedEntitySuggestions(getEdgeRouters(), "路由器"),
      ...collectRoleAttributes(getEdgeRouters()).map((value) => roleAttributeOption(value, "路由器")),
    ]);
  }
  if (fieldName === "postureCheckRoles") {
    return dedupeSuggestions([
      { value: "#all", title: "#all", meta: "全部 posture checks" },
      ...buildNamedEntitySuggestions(getPostureChecks(), "Posture Check"),
    ]);
  }
  return [];
}

export function buildComboboxField(fieldName, label, currentValue, placeholder, helperText = "", helpKey = "", extras = "") {
  return `
    <div class="field combo-field" data-combobox="${fieldName}">
      ${buildFieldLabel(label, helpKey)}
      <div class="combo-shell">
        <input
          class="combo-input"
          name="${fieldName}"
          data-combobox-input="${fieldName}"
          value="${escapeHtml(currentValue)}"
          placeholder="${escapeHtml(placeholder)}"
          autocomplete="off"
          spellcheck="false"
        />
        <button type="button" class="button-muted compact-button combo-trigger" data-combobox-toggle="${fieldName}">浏览</button>
      </div>
      <div class="combo-menu hidden" data-combobox-menu="${fieldName}"></div>
      ${helperText ? `<p class="text-helper">${helperText}</p>` : ""}
      ${extras}
    </div>
  `;
}

export function buildEditableSuggestionField(fieldName, label, currentValue, placeholder, helperText, helpKey = "") {
  const pickerName = `picker__${fieldName}`;
  return `
    <label class="field">${buildFieldLabel(label, helpKey)}<input name="${fieldName}" value="${escapeHtml(currentValue)}" placeholder="${escapeHtml(placeholder)}" /></label>
    <div class="picker-row">
      <div class="picker-suggestions">
        <div class="combo-shell">
          <input
            class="picker-input combo-input"
            name="${pickerName}"
            data-combobox-input="${pickerName}"
            placeholder="从建议列表选择，或继续输入自定义值"
            autocomplete="off"
            spellcheck="false"
          />
          <button type="button" class="button-muted compact-button combo-trigger" data-combobox-toggle="${pickerName}">浏览</button>
        </div>
        <div class="combo-menu hidden" data-combobox-menu="${pickerName}"></div>
      </div>
      <button type="button" class="button-muted compact-button" data-picker-add-target="${fieldName}" data-picker-source="${pickerName}">追加</button>
    </div>
    <p class="text-helper">${helperText}</p>
  `;
}

export function buildSingleSuggestionField(fieldName, label, currentValue, placeholder, helperText, _options = [], helpKey = "") {
  return buildComboboxField(fieldName, label, currentValue, placeholder, helperText, helpKey);
}

function getAuthPolicySuggestions() {
  return dedupeSuggestions(
    getAuthPolicies().flatMap((item) => {
      const name = String(item?.name || "").trim();
      const id = String(item?.id || "").trim();
      return [
        name
          ? {
              value: name,
              title: name,
              meta: [id, item?.tags && Object.keys(item.tags).length ? "带标签" : ""].filter(Boolean).join(" / "),
            }
          : null,
        id
          ? {
              value: id,
              title: id,
              meta: [name].filter(Boolean).join(" / "),
            }
          : null,
      ].filter(Boolean);
    }),
  );
}

function getComboboxOptions(fieldName) {
  if (fieldName === "configBuilderNamespace") {
    return sortSuggestionOptions(
      getK8sNamespaceOptions().map((option) => ({
        value: option.value,
        title: option.value,
        meta: option.label,
      })),
    );
  }

  if (fieldName === "configBuilderServiceName") {
    const namespace = refs.dialogBody.querySelector('[name="configBuilderNamespace"]')?.value || "default";
    return sortSuggestionOptions(
      getK8sServicesInNamespace(namespace).map((service) => ({
        value: service.name,
        title: service.name,
        meta: `${service.namespace || "-"} / ${service.type || "ClusterIP"} / ${
          ensureArray(service.ports)
            .map((port) => `${String(port.protocol || "TCP").toLowerCase()}:${port.port}`)
            .join(" ") || "无端口"
        }`,
      })),
    );
  }

  if (fieldName === "configBuilderPort") {
    const namespace = refs.dialogBody.querySelector('[name="configBuilderNamespace"]')?.value || "default";
    const serviceName = refs.dialogBody.querySelector('[name="configBuilderServiceName"]')?.value || "";
    return sortSuggestionOptions(
      getK8sServicePortOptions(namespace, serviceName).map((option) => ({
        value: option.value,
        title: option.value,
        meta: option.label,
      })),
    );
  }

  if (fieldName === "authPolicyId") {
    return getAuthPolicySuggestions();
  }

  if (fieldName.startsWith("picker__")) {
    return getRoleSuggestions(fieldName.replace(/^picker__/, ""));
  }

  return [];
}

export function renderComboboxMenu(fieldName, openMenu = true, queryOverride = null) {
  const input = refs.dialogBody.querySelector(`[data-combobox-input="${fieldName}"]`);
  const menu = refs.dialogBody.querySelector(`[data-combobox-menu="${fieldName}"]`);
  if (!(input instanceof HTMLInputElement) || !(menu instanceof HTMLElement)) {
    return;
  }

  const filtered = filterSuggestionOptions(getComboboxOptions(fieldName), queryOverride === null ? input.value : queryOverride).slice(0, 12);
  menu.innerHTML = filtered.length
    ? filtered
        .map(
          (option) => `
            <button type="button" class="combo-option" data-combobox-option="${fieldName}" data-value="${escapeHtml(option.value)}">
              <span class="combo-option-title">${escapeHtml(option.title)}</span>
              ${option.meta ? `<span class="combo-option-meta">${escapeHtml(option.meta)}</span>` : ""}
              <span class="combo-option-value mono">${escapeHtml(option.value)}</span>
            </button>
          `,
        )
        .join("")
    : '<div class="combo-empty">没有匹配项。你可以继续手输自定义值。</div>';

  menu.classList.toggle("hidden", !openMenu);
  refreshDialogFieldStates();
}

export function closeCombobox(fieldName) {
  const menu = refs.dialogBody.querySelector(`[data-combobox-menu="${fieldName}"]`);
  if (menu instanceof HTMLElement) {
    menu.classList.add("hidden");
  }
  refreshDialogFieldStates();
}

export function closeAllComboboxes(exceptFieldName = "") {
  refs.dialogBody.querySelectorAll("[data-combobox-menu]").forEach((menu) => {
    if (!(menu instanceof HTMLElement)) {
      return;
    }
    if (exceptFieldName && menu.dataset.comboboxMenu === exceptFieldName) {
      return;
    }
    menu.classList.add("hidden");
  });
  refreshDialogFieldStates();
}

export function refreshVisibleComboboxes() {
  refs.dialogBody.querySelectorAll("[data-combobox-menu]").forEach((menu) => {
    if (!(menu instanceof HTMLElement) || menu.classList.contains("hidden")) {
      return;
    }
    const fieldName = menu.dataset.comboboxMenu || "";
    if (fieldName) {
      renderComboboxMenu(fieldName, true);
    }
  });
}

export function markFieldTouched(fieldName) {
  if (!state.modal || !fieldName) {
    return;
  }
  state.modal.touchedFields = state.modal.touchedFields || {};
  state.modal.touchedFields[fieldName] = true;
}

export function refreshDialogFieldStates() {
  if (!refs.dialogBody) {
    return;
  }

  refs.dialogBody.querySelectorAll(".field, .combo-field, .toggle-row").forEach((container) => {
    if (!(container instanceof HTMLElement)) {
      return;
    }
    const namedControls = Array.from(container.querySelectorAll("input[name], select[name], textarea[name]")).filter((control) => {
      return control instanceof HTMLElement && control.getAttribute("name");
    });
    const hasValue = namedControls.some((control) => {
      if (!(control instanceof HTMLInputElement || control instanceof HTMLSelectElement || control instanceof HTMLTextAreaElement)) {
        return false;
      }
      if (control instanceof HTMLInputElement && control.type === "checkbox") {
        return control.checked;
      }
      if (control instanceof HTMLSelectElement && control.multiple) {
        return Array.from(control.selectedOptions).some((option) => option.value);
      }
      return Boolean(String(control.value || "").trim());
    });
    const isDirty = namedControls.some((control) => {
      const fieldName = control.getAttribute("name") || "";
      return Boolean(state.modal?.touchedFields?.[fieldName]);
    });
    container.classList.toggle("has-value", hasValue);
    container.classList.toggle("is-dirty", isDirty);
    container.classList.toggle("is-focused", container.contains(document.activeElement));
    if (container.classList.contains("combo-field")) {
      const menu = container.querySelector("[data-combobox-menu]");
      container.classList.toggle("is-open", menu instanceof HTMLElement && !menu.classList.contains("hidden"));
    }
  });
}

export function isSupportedConfigType(typeName) {
  return ["host.v1", "intercept.v1"].includes(typeName);
}

export function defaultConfigData(typeName) {
  if (typeName === "host.v1") {
    return {
      address: "",
      port: 80,
      protocol: "tcp",
    };
  }
  if (typeName === "intercept.v1") {
    return {
      addresses: [""],
      portRanges: [{ low: 80, high: 80 }],
      protocols: ["tcp"],
    };
  }
  if (typeName === "host.v2") {
    return {
      terminators: [
        {
          address: "",
          port: 80,
          protocol: "tcp",
        },
      ],
    };
  }
  return { xxx: "" };
}

export function readDelimitedList(value) {
  return String(value ?? "")
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function normalizePort(value, fallback = 80) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return fallback;
  }
  return parsed;
}

export function composeK8sServiceAddress(serviceName, namespace) {
  const trimmedServiceName = String(serviceName ?? "").trim();
  if (!trimmedServiceName) {
    return "";
  }
  const trimmedNamespace = String(namespace ?? "").trim() || "default";
  return `${trimmedServiceName}.${trimmedNamespace}.svc.cluster.local`;
}

function parseK8sServiceAddress(address) {
  const match = /^\s*([a-z0-9]([-a-z0-9]*[a-z0-9])?)\.([a-z0-9]([-a-z0-9]*[a-z0-9])?)\.svc(?:\.cluster\.local)?\s*$/i.exec(
    String(address ?? ""),
  );
  if (!match) {
    return null;
  }
  return {
    serviceName: match[1],
    namespace: match[3],
  };
}

function sortEntitiesByName(items = []) {
  return [...ensureArray(items)].sort((left, right) => {
    const leftKey = String(left?.name || left?.id || "");
    const rightKey = String(right?.name || right?.id || "");
    const nameOrder = leftKey.localeCompare(rightKey, "zh-CN");
    if (nameOrder !== 0) {
      return nameOrder;
    }
    return String(left?.id || "").localeCompare(String(right?.id || ""), "zh-CN");
  });
}

export function classifyConfigType(typeName) {
  const currentType = String(typeName || "").trim();
  if (currentType === "intercept.v1") {
    return "intercept";
  }
  if (currentType.startsWith("host.")) {
    return "host";
  }
  return "other";
}

export function roleExpressionMatchesEntity(roleExpression, entity) {
  const value = String(roleExpression || "").trim();
  if (!value || !entity || typeof entity !== "object") {
    return false;
  }
  if (value === "#all") {
    return true;
  }
  if (value.startsWith("@")) {
    const target = value.slice(1);
    return target === String(entity.id || "") || target === String(entity.name || "");
  }
  if (value.startsWith("#")) {
    const attribute = value.slice(1);
    return ensureArray(entity.roleAttributes).map((item) => String(item || "")).includes(attribute);
  }
  return false;
}

export function roleListMatchesEntity(roleExpressions, entity, semantic = "AnyOf") {
  const values = ensureArray(roleExpressions).map((item) => String(item || "").trim()).filter(Boolean);
  if (!values.length) {
    return false;
  }
  if (String(semantic || "AnyOf") === "AllOf") {
    return values.every((value) => roleExpressionMatchesEntity(value, entity));
  }
  return values.some((value) => roleExpressionMatchesEntity(value, entity));
}

export function getServiceConfigs(service) {
  const configMap = getConfigMap();
  return sortEntitiesByName(ensureArray(service?.configs).map((configId) => configMap.get(configId)).filter(Boolean));
}

export function findServicesForConfig(configId) {
  const currentConfigId = String(configId || "").trim();
  if (!currentConfigId) {
    return [];
  }
  return sortEntitiesByName(
    getServices().filter((service) => {
      return ensureArray(service?.configs).includes(currentConfigId);
    }),
  );
}

export function matchK8sServiceReference(address) {
  const normalizedAddress = String(address || "").trim();
  if (!normalizedAddress) {
    return null;
  }

  const parsedAddress = parseK8sServiceAddress(normalizedAddress);
  if (parsedAddress) {
    return findK8sService(parsedAddress.namespace, parsedAddress.serviceName);
  }

  return (
    getK8sServices().find((service) => {
      const fqdn = String(service?.fqdn || "").trim();
      const shortFqdn = service?.namespace && service?.name ? `${service.name}.${service.namespace}.svc` : "";
      return (
        normalizedAddress === String(service?.cluster_ip || "").trim() ||
        normalizedAddress === fqdn ||
        normalizedAddress === shortFqdn
      );
    }) || null
  );
}

export function getServicePoliciesForService(service, policyType = "") {
  if (!service) {
    return [];
  }
  const currentType = String(policyType || "").trim();
  return sortEntitiesByName(
    getServicePolicies().filter((policy) => {
      if (currentType && String(policy?.type || "").trim() !== currentType) {
        return false;
      }
      return roleListMatchesEntity(policy?.serviceRoles, service, policy?.semantic);
    }),
  );
}

export function getMatchedIdentitiesForPolicy(policy) {
  return sortEntitiesByName(
    getIdentities().filter((identity) => roleListMatchesEntity(policy?.identityRoles, identity, policy?.semantic)),
  );
}

export function getMatchedServicesForPolicy(policy) {
  return sortEntitiesByName(getServices().filter((service) => roleListMatchesEntity(policy?.serviceRoles, service, policy?.semantic)));
}

export function getMatchedRoutersForPolicy(policy, routerRoleField = "edgeRouterRoles") {
  return sortEntitiesByName(
    getEdgeRouters().filter((router) => roleListMatchesEntity(policy?.[routerRoleField], router, policy?.semantic)),
  );
}

export function getMatchedDialIdentitiesForService(service) {
  const policies = getServicePoliciesForService(service, "Dial");
  return sortEntitiesByName(
    getIdentities().filter((identity) => policies.some((policy) => roleListMatchesEntity(policy?.identityRoles, identity, policy?.semantic))),
  );
}

export function getMatchedBindIdentitiesForService(service) {
  const policies = getServicePoliciesForService(service, "Bind");
  return sortEntitiesByName(
    getIdentities().filter((identity) => policies.some((policy) => roleListMatchesEntity(policy?.identityRoles, identity, policy?.semantic))),
  );
}

export function getMatchedRoutersForService(service) {
  const policies = sortEntitiesByName(
    getServiceEdgeRouterPolicies().filter((policy) => roleListMatchesEntity(policy?.serviceRoles, service, policy?.semantic)),
  );
  return sortEntitiesByName(
    getEdgeRouters().filter((router) => policies.some((policy) => roleListMatchesEntity(policy?.edgeRouterRoles, router, policy?.semantic))),
  );
}

export function getMatchedDialServicesForIdentity(identity) {
  const policies = sortEntitiesByName(
    getServicePolicies().filter(
      (policy) => String(policy?.type || "").trim() === "Dial" && roleListMatchesEntity(policy?.identityRoles, identity, policy?.semantic),
    ),
  );
  return sortEntitiesByName(
    getServices().filter((service) => policies.some((policy) => roleListMatchesEntity(policy?.serviceRoles, service, policy?.semantic))),
  );
}

export function getMatchedBindServicesForIdentity(identity) {
  const policies = sortEntitiesByName(
    getServicePolicies().filter(
      (policy) => String(policy?.type || "").trim() === "Bind" && roleListMatchesEntity(policy?.identityRoles, identity, policy?.semantic),
    ),
  );
  return sortEntitiesByName(
    getServices().filter((service) => policies.some((policy) => roleListMatchesEntity(policy?.serviceRoles, service, policy?.semantic))),
  );
}

export function getMatchedRoutersForIdentity(identity) {
  const policies = sortEntitiesByName(
    getEdgeRouterPolicies().filter((policy) => roleListMatchesEntity(policy?.identityRoles, identity, policy?.semantic)),
  );
  return sortEntitiesByName(
    getEdgeRouters().filter((router) => policies.some((policy) => roleListMatchesEntity(policy?.edgeRouterRoles, router, policy?.semantic))),
  );
}

export function getMatchedServicesForRouter(router) {
  const policies = sortEntitiesByName(
    getServiceEdgeRouterPolicies().filter((policy) => roleListMatchesEntity(policy?.edgeRouterRoles, router, policy?.semantic)),
  );
  return sortEntitiesByName(
    getServices().filter((service) => policies.some((policy) => roleListMatchesEntity(policy?.serviceRoles, service, policy?.semantic))),
  );
}

export function getMatchedIdentitiesForRouter(router) {
  const policies = sortEntitiesByName(
    getEdgeRouterPolicies().filter((policy) => roleListMatchesEntity(policy?.edgeRouterRoles, router, policy?.semantic)),
  );
  return sortEntitiesByName(
    getIdentities().filter((identity) => policies.some((policy) => roleListMatchesEntity(policy?.identityRoles, identity, policy?.semantic))),
  );
}

function normalizeHostConfigData(data) {
  const draft = cloneJson(data);
  return {
    address: typeof draft.address === "string" ? draft.address : "",
    port: normalizePort(draft.port, 80),
    protocol: draft.protocol === "udp" ? "udp" : "tcp",
  };
}

function normalizeInterceptConfigData(data) {
  const draft = cloneJson(data);
  const firstRange = Array.isArray(draft.portRanges) ? draft.portRanges[0] || {} : {};
  return {
    addresses: Array.isArray(draft.addresses) ? draft.addresses.map((item) => String(item ?? "")) : [""],
    port: normalizePort(firstRange.low, 80),
    protocol: Array.isArray(draft.protocols) && draft.protocols[0] === "udp" ? "udp" : "tcp",
  };
}

function getActiveConfigTypeId() {
  if (!state.modal || state.modal.resourceType !== "configs") {
    return "";
  }
  if (state.modal.mode === "edit") {
    return state.modal.entity?.configTypeId || "";
  }
  const select = refs.dialogBody.querySelector('select[name="configTypeId"]');
  return select?.value || state.modal.configTypeId || "";
}

export function getActiveConfigTypeName() {
  return getConfigTypeNameById(getActiveConfigTypeId());
}

function buildHostConfigEditor(data) {
  const normalized = normalizeHostConfigData(data);
  const k8sRef = parseK8sServiceAddress(normalized.address);
  const hasAddress = Boolean(String(normalized.address || "").trim());
  const mode = !hasAddress || k8sRef ? "k8s" : "custom";
  const namespace = k8sRef?.namespace || "default";
  const serviceName = k8sRef?.serviceName || "";
  const preview = mode === "k8s" ? composeK8sServiceAddress(serviceName, namespace) || "service.namespace.svc.cluster.local" : normalized.address || "example.internal";

  return `
    <div class="builder-card" data-config-builder="host.v1">
      <div class="builder-header">
        <div>
          <p class="section-kicker">默认表单</p>
          <h3>Host 配置</h3>
        </div>
        <span class="pill">host.v1</span>
      </div>
      <label class="field">
        ${buildFieldLabel("代理目标", "config.hostMode")}
        <select name="configBuilderHostMode">
          <option value="k8s" ${mode === "k8s" ? "selected" : ""}>Kubernetes Service</option>
          <option value="custom" ${mode === "custom" ? "selected" : ""}>自定义地址</option>
        </select>
      </label>
      <div class="split-grid ${mode === "custom" ? "hidden" : ""}" data-config-host-mode="k8s">
        ${buildComboboxField(
          "configBuilderNamespace",
          "K8s 命名空间",
          namespace,
          "default",
          "优先从当前集群里现有的 namespace 里选择，也可以继续手输。",
          "config.namespace",
        )}
        ${buildComboboxField(
          "configBuilderServiceName",
          "K8s Service",
          serviceName,
          "my-service",
          "建议项会直接显示 Service 名称，并附带 namespace、类型和端口信息。",
          "config.serviceName",
        )}
      </div>
      <label class="field ${mode === "k8s" ? "hidden" : ""}" data-config-host-mode="custom">
        ${buildFieldLabel("自定义地址", "config.address")}
        <input name="configBuilderAddress" value="${escapeHtml(mode === "custom" ? normalized.address : "")}" placeholder="example.internal" />
      </label>
      <div class="split-grid">
        ${buildComboboxField(
          "configBuilderPort",
          "端口",
          normalized.port,
          "8080",
          "如果选中了 k8s Service，建议列表会优先给出它真实暴露的端口。",
          "config.port",
        )}
        <label class="field">
          ${buildFieldLabel("协议", "config.protocol")}
          <select name="configBuilderProtocol">
            <option value="tcp" ${normalized.protocol === "tcp" ? "selected" : ""}>tcp</option>
            <option value="udp" ${normalized.protocol === "udp" ? "selected" : ""}>udp</option>
          </select>
        </label>
      </div>
      <p class="text-helper">常见场景是把流量代理到集群内的 Service，地址会自动拼成 <code>service.namespace.svc.cluster.local</code>，不会直接写成 ClusterIP。</p>
      <div data-k8s-service-match>
        ${buildMatchedK8sServicePreview(namespace, serviceName)}
      </div>
      <div class="preview-card">
        <span>当前目标地址</span>
        <strong class="mono" data-config-host-preview>${escapeHtml(preview)}</strong>
      </div>
    </div>
  `;
}

function buildInterceptConfigEditor(data) {
  const normalized = normalizeInterceptConfigData(data);
  return `
    <div class="builder-card" data-config-builder="intercept.v1">
      <div class="builder-header">
        <div>
          <p class="section-kicker">默认表单</p>
          <h3>Intercept 配置</h3>
        </div>
        <span class="pill">intercept.v1</span>
      </div>
      <label class="field">
        ${buildFieldLabel("Ziti 域名", "config.interceptAddresses")}
        <textarea name="configBuilderInterceptAddresses" rows="3" placeholder="port-audit.ziti">${escapeHtml(normalized.addresses.join("\n"))}</textarea>
      </label>
      <p class="text-helper">支持一行一个地址，也支持逗号分隔。大多数场景先填一个域名就够了。</p>
      <div class="split-grid">
        <label class="field">
          ${buildFieldLabel("端口", "config.port")}
          <input name="configBuilderInterceptPort" type="number" min="1" max="65535" value="${escapeHtml(normalized.port)}" />
        </label>
        <label class="field">
          ${buildFieldLabel("协议", "config.protocol")}
          <select name="configBuilderInterceptProtocol">
            <option value="tcp" ${normalized.protocol === "tcp" ? "selected" : ""}>tcp</option>
            <option value="udp" ${normalized.protocol === "udp" ? "selected" : ""}>udp</option>
          </select>
        </label>
      </div>
    </div>
  `;
}

function buildConfigEditorFields(configTypeName, data) {
  if (configTypeName === "host.v1") {
    return buildHostConfigEditor(data);
  }
  if (configTypeName === "intercept.v1") {
    return buildInterceptConfigEditor(data);
  }
  return `
    <div class="builder-card">
      <div class="builder-header">
        <div>
          <p class="section-kicker">JSON 模式</p>
          <h3>原始配置</h3>
        </div>
        <span class="pill warn">无专用表单</span>
      </div>
      ${buildConfigTypeDocNote(configTypeName)}
      <p class="text-helper">当前类型暂时没有专用表单，会直接使用原始 JSON。默认已给你放了一个可改的模板。</p>
    </div>
  `;
}

function buildConfigJsonEditor(configTypeName, data) {
  const supported = isSupportedConfigType(configTypeName);
  const expanded = supported ? Boolean(state.modal?.configJsonExpanded) : true;
  const rawJson = state.modal?.configRawJson || formatJson(data);
  const statusText =
    state.modal?.configJsonStatus ||
    (supported ? "表单会自动同步更新 JSON；需要时也可以从 JSON 回填表单。" : "直接编辑原始 JSON。");
  return `
    <div class="config-json-shell">
      <div class="builder-row">
        ${
          supported
            ? `<button type="button" class="button-muted compact-button" data-config-json-toggle>
          ${expanded ? "收起原始 JSON" : "查看原始 JSON"}
        </button>`
            : '<span class="pill warn">原始 JSON</span>'
        }
        <div class="button-row compact">
          <button type="button" class="button-muted compact-button" data-config-json-copy>复制 JSON</button>
          ${
            supported
              ? '<button type="button" class="button-muted compact-button" data-config-json-apply>从 JSON 回填表单</button>'
              : ""
          }
        </div>
      </div>
      <div class="${expanded ? "" : "hidden"}" data-config-json-panel>
        <label class="field"><span>Data JSON / 原始内容</span><textarea name="dataJson" rows="12" placeholder='{"xxx":""}'>${escapeHtml(rawJson)}</textarea></label>
        <p class="text-helper ${state.modal?.configJsonError ? "is-error" : ""}" data-config-json-status>${escapeHtml(statusText)}</p>
      </div>
    </div>
  `;
}

export function buildConfigDataSection(configTypeName, data) {
  return `
    ${!isSupportedConfigType(configTypeName) ? "" : buildConfigTypeDocNote(configTypeName)}
    ${buildConfigEditorFields(configTypeName, data)}
    ${buildConfigJsonEditor(configTypeName, data)}
  `;
}

export function toJsonPayload(formData) {
  const payload = {};

  Array.from(refs.entityForm.querySelectorAll('input[type="checkbox"][name$="Checkbox"]')).forEach((input) => {
    payload[input.name.replace(/Checkbox$/, "")] = formData.has(input.name);
  });

  const multiSelectNames = new Set();
  Array.from(refs.entityForm.querySelectorAll("select[multiple][name]")).forEach((select) => {
    multiSelectNames.add(select.name);
    payload[select.name] = Array.from(select.selectedOptions)
      .map((option) => option.value)
      .filter(Boolean);
  });

  for (const [key, rawValue] of formData.entries()) {
    if (
      key.endsWith("Checkbox") ||
      multiSelectNames.has(key) ||
      key.startsWith("configBuilder") ||
      key.startsWith("picker__")
    ) {
      continue;
    }

    const text = String(rawValue);
    if (key === "tagsJson") {
      payload.tags = text.trim() ? JSON.parse(text) : {};
      continue;
    }
    if (key === "dataJson") {
      payload.data = text.trim() ? JSON.parse(text) : {};
      continue;
    }

    if (Object.prototype.hasOwnProperty.call(payload, key)) {
      payload[key] = Array.isArray(payload[key]) ? [...payload[key], text] : [payload[key], text];
      continue;
    }
    payload[key] = text;
  }

  return payload;
}

export function findEntity(resourceType, entityId) {
  const map = {
    configs: state.overview?.configs || [],
    "edge-routers": state.overview?.edge_routers || [],
    "edge-router-policies": state.overview?.edge_router_policies || [],
    identities: state.overview?.identities || [],
    "service-edge-router-policies": state.overview?.service_edge_router_policies || [],
    "service-policies": state.overview?.service_policies || [],
    services: state.overview?.services || [],
  };
  return map[resourceType]?.find((item) => item.id === entityId) || null;
}
