import { renderDialogCommandPreview } from "./commands.js";
import {
  buildAdvancedSection,
  buildConfigDataSection,
  buildEditableSuggestionField,
  buildFieldLabel,
  buildMatchedK8sServicePreview,
  buildSingleSuggestionField,
  buildToggleField,
  cloneJson,
  closeAllComboboxes,
  closeCombobox,
  composeK8sServiceAddress,
  configOptionsHtml,
  configTypeOptionsHtml,
  copyText,
  dedupeSuggestions,
  defaultConfigData,
  ensureArray,
  escapeHtml,
  formatJson,
  getActiveConfigTypeName,
  getAuthPolicies,
  getConfigTypeNameById,
  getConfigTypes,
  getConfigs,
  getK8sServicePortOptions,
  getServiceMaxIdleInputValue,
  isSupportedConfigType,
  markFieldTouched,
  normalizePort,
  readDelimitedList,
  refs,
  refreshDialogFieldStates,
  refreshVisibleComboboxes,
  renderComboboxMenu,
  resourceLabels,
  state,
} from "./shared.js";

function buildDialogFields(resourceType, mode, entity) {
  const isCreate = mode === "create";

  if (resourceType === "edge-routers") {
    return `
      <label class="field">${buildFieldLabel("名称", "common.name")}<input name="name" value="${escapeHtml(entity?.name || "")}" /></label>
      ${buildAdvancedSection(
        `
      <label class="field">${buildFieldLabel("成本", "router.cost")}<input name="cost" type="number" min="0" value="${escapeHtml(entity?.cost ?? 0)}" /></label>
      <label class="field">${buildFieldLabel("角色属性", "common.roleAttributes")}<input name="roleAttributes" value="${escapeHtml(ensureArray(entity?.roleAttributes).join(","))}" placeholder="示例: public,branch-a" /></label>
      <label class="field">${buildFieldLabel("Tags JSON", "common.tags")}<textarea name="tagsJson" rows="4" placeholder='{"env":"prod"}'>${escapeHtml(formatJson(entity?.tags || {}))}</textarea></label>
      ${buildToggleField("disabledCheckbox", "禁用 router", entity?.disabled, "router.disabled")}
      ${buildToggleField("noTraversalCheckbox", "禁止 traversal", entity?.noTraversal, "router.noTraversal")}
      ${buildToggleField("isTunnelerEnabledCheckbox", "允许 tunneler", entity?.isTunnelerEnabled, "router.tunneler")}
      `,
        "大多数场景先填名称就够了，其他像 cost、traversal、tunneler 开关都可以按需再配。",
      )}
      ${isCreate ? '<p class="text-helper">创建后页面会展示 enrollment JWT，便于后续给 router 发放入网凭据。</p>' : ""}
    `;
  }

  if (resourceType === "services") {
    const configs = getConfigs();
    const currentConfigs = ensureArray(entity?.configs);
    const selectSize = Math.min(Math.max(configs.length || 1, 4), 8);
    return `
      <label class="field">${buildFieldLabel("名称", "common.name")}<input name="name" value="${escapeHtml(entity?.name || "")}" /></label>
      <label class="field">
        ${buildFieldLabel("绑定 Configs", "service.configs")}
        <select name="configs" multiple size="${selectSize}">
          ${configOptionsHtml(currentConfigs)}
        </select>
      </label>
      <p class="text-helper">按住 Ctrl/Command 或 Shift 进行多选。官方常见示例通常就是先选好 <code>intercept.v1</code> 和 <code>host.v1 / host.v2</code> 对应的 config，再创建 service。</p>
      ${buildAdvancedSection(
        `
      <label class="field">${buildFieldLabel("角色属性", "common.roleAttributes")}<input name="roleAttributes" value="${escapeHtml(ensureArray(entity?.roleAttributes).join(","))}" placeholder="示例: web,internal" /></label>
      <label class="field">${buildFieldLabel("终结器策略", "service.terminatorStrategy")}<input name="terminatorStrategy" value="${escapeHtml(entity?.terminatorStrategy || "smartrouting")}" placeholder="smartrouting" /></label>
      <label class="field">${buildFieldLabel("空闲回收时间", "service.maxIdleTime")}<input name="maxIdleTime" value="${escapeHtml(getServiceMaxIdleInputValue(entity))}" placeholder="示例: 30s / 5m / 1h" /></label>
      ${
        isCreate
          ? buildToggleField("encryptionRequiredCheckbox", "要求端到端加密", entity ? entity.encryptionRequired : true, "service.encryptionRequired")
          : `
      <label class="field">${buildFieldLabel("加密要求", "service.encryptionRequired")}<input value="${escapeHtml(entity?.encryptionRequired ? "强制加密" : "允许明文")}" disabled /></label>
      <p class="text-helper">官方 Edge Management API 文档把 <code>encryptionRequired</code> 标成只读字段，所以编辑时这里仅展示当前状态。</p>
      `
      }
      <label class="field">${buildFieldLabel("Tags JSON", "common.tags")}<textarea name="tagsJson" rows="4">${escapeHtml(formatJson(entity?.tags || {}))}</textarea></label>
      `,
        "这些字段大多有默认值：encryption 默认 ON，terminatorStrategy 默认 smartrouting，max idle 留空即可。",
      )}
    `;
  }

  if (resourceType === "configs") {
    const configTypes = getConfigTypes();
    const selectedConfigTypeId = state.modal?.configTypeId || entity?.configTypeId || configTypes[0]?.id || "";
    const selectedConfigTypeName =
      entity?.configType?.name || configTypes.find((item) => item.id === selectedConfigTypeId)?.name || selectedConfigTypeId || "-";
    const currentData = cloneJson(state.modal?.configDraftData || entity?.data || defaultConfigData(selectedConfigTypeName));
    const currentName = state.modal?.configNameDraft ?? entity?.name ?? "";
    const currentTagsJson = state.modal?.configTagsDraft ?? formatJson(entity?.tags || {});

    return `
      <label class="field">${buildFieldLabel("名称", "common.name")}<input name="name" value="${escapeHtml(currentName)}" /></label>
      ${
        isCreate
          ? `<label class="field">${buildFieldLabel("配置类型", "config.type")}<select name="configTypeId">${configTypeOptionsHtml(selectedConfigTypeId)}</select></label>`
          : `<label class="field">${buildFieldLabel("配置类型", "config.type")}<input value="${escapeHtml(selectedConfigTypeName)} (${escapeHtml(selectedConfigTypeId)})" disabled /></label>`
      }
      ${buildConfigDataSection(selectedConfigTypeName, currentData)}
      <p class="text-helper">点击保存后，页面真正提交的是当前 JSON 内容；如果表单和 JSON 都动过，以 JSON 为准。</p>
      ${buildAdvancedSection(
        `<label class="field">${buildFieldLabel("Tags JSON", "common.tags")}<textarea name="tagsJson" rows="4">${escapeHtml(currentTagsJson)}</textarea></label>`,
        "Tags 不是必填；只有你需要做额外标记或筛选时再填。",
      )}
    `;
  }

  if (resourceType === "service-policies") {
    return `
      <label class="field">${buildFieldLabel("名称", "common.name")}<input name="name" value="${escapeHtml(entity?.name || "")}" /></label>
      <label class="field">${buildFieldLabel("类型", "policy.type")}<select name="type"><option value="Dial" ${entity?.type === "Dial" ? "selected" : ""}>Dial</option><option value="Bind" ${entity?.type === "Bind" ? "selected" : ""}>Bind</option></select></label>
      ${buildEditableSuggestionField(
        "identityRoles",
        "匹配身份",
        ensureArray(entity?.identityRoles).join(","),
        "#all,@identity-name,#role-attr",
        "可以直接写原始 role 语法，也可以从 controller 里现有身份下拉选择并追加。",
        "policy.identityRoles",
      )}
      ${buildEditableSuggestionField(
        "serviceRoles",
        "匹配服务",
        ensureArray(entity?.serviceRoles).join(","),
        "#all,@service-name,#role-attr",
        "服务角色支持直接引用现有服务，也支持继续手写自定义规则。",
        "policy.serviceRoles",
      )}
      ${buildEditableSuggestionField(
        "postureCheckRoles",
        "姿态校验",
        ensureArray(entity?.postureCheckRoles).join(","),
        "@posture-check-name,@posture-check-id,#all",
        "这里已经接 controller 实时列表了，同时仍然支持继续手写原生 role 语法。",
        "policy.postureCheckRoles",
      )}
      ${buildAdvancedSection(
        `
      <label class="field">${buildFieldLabel("Semantic", "common.semantic")}<select name="semantic"><option value="AnyOf" ${entity?.semantic === "AnyOf" || !entity?.semantic ? "selected" : ""}>AnyOf</option><option value="AllOf" ${entity?.semantic === "AllOf" ? "selected" : ""}>AllOf</option></select></label>
      <label class="field">${buildFieldLabel("Tags JSON", "common.tags")}<textarea name="tagsJson" rows="4">${escapeHtml(formatJson(entity?.tags || {}))}</textarea></label>
      `,
        "官方文档里 semantic 默认就是 AnyOf，大多数简单场景不需要额外调整。",
      )}
    `;
  }

  if (resourceType === "edge-router-policies") {
    return `
      <label class="field">${buildFieldLabel("名称", "common.name")}<input name="name" value="${escapeHtml(entity?.name || "")}" /></label>
      ${buildEditableSuggestionField(
        "identityRoles",
        "匹配身份",
        ensureArray(entity?.identityRoles).join(","),
        "#all,@identity-name,#role-attr",
        "身份角色可以从现有 identity 下拉选择，也可以保留自定义写法。",
        "policy.identityRoles",
      )}
      ${buildEditableSuggestionField(
        "edgeRouterRoles",
        "匹配路由器",
        ensureArray(entity?.edgeRouterRoles).join(","),
        "#all,@router-name,#role-attr",
        "路由器角色支持从当前在线或离线路由器里挑选一个直接追加。",
        "policy.edgeRouterRoles",
      )}
      ${buildAdvancedSection(
        `
      <label class="field">${buildFieldLabel("Semantic", "common.semantic")}<select name="semantic"><option value="AnyOf" ${entity?.semantic === "AnyOf" || !entity?.semantic ? "selected" : ""}>AnyOf</option><option value="AllOf" ${entity?.semantic === "AllOf" ? "selected" : ""}>AllOf</option></select></label>
      <label class="field">${buildFieldLabel("Tags JSON", "common.tags")}<textarea name="tagsJson" rows="4">${escapeHtml(formatJson(entity?.tags || {}))}</textarea></label>
      `,
        "大多数场景下直接用默认的 AnyOf 就够了。",
      )}
    `;
  }

  if (resourceType === "service-edge-router-policies") {
    return `
      <label class="field">${buildFieldLabel("名称", "common.name")}<input name="name" value="${escapeHtml(entity?.name || "")}" /></label>
      ${buildEditableSuggestionField(
        "serviceRoles",
        "匹配服务",
        ensureArray(entity?.serviceRoles).join(","),
        "@service-name,#service-tag",
        "支持从现有服务里直接选，也支持继续手写 controller 原生 role 语法。",
        "policy.serviceRoles",
      )}
      ${buildEditableSuggestionField(
        "edgeRouterRoles",
        "匹配路由器",
        ensureArray(entity?.edgeRouterRoles).join(","),
        "@router-name,#router-tag",
        "支持从当前路由器里选择，或继续手写自定义 role。",
        "policy.edgeRouterRoles",
      )}
      <p class="text-helper">支持 controller 原生 role 语法，比如 <code>@资源名</code>、<code>@资源ID</code>、<code>#角色属性</code>、<code>#all</code>。</p>
      ${buildAdvancedSection(
        `
      <label class="field">${buildFieldLabel("Semantic", "common.semantic")}<select name="semantic"><option value="AnyOf" ${entity?.semantic === "AnyOf" || !entity?.semantic ? "selected" : ""}>AnyOf</option><option value="AllOf" ${entity?.semantic === "AllOf" ? "selected" : ""}>AllOf</option></select></label>
      <label class="field">${buildFieldLabel("Tags JSON", "common.tags")}<textarea name="tagsJson" rows="4">${escapeHtml(formatJson(entity?.tags || {}))}</textarea></label>
      `,
        "如果你只是把某些服务接到某些路由器上，保持默认 AnyOf 往往就够了。",
      )}
    `;
  }

  return `
    <label class="field">${buildFieldLabel("名称", "common.name")}<input name="name" value="${escapeHtml(entity?.name || "")}" /></label>
    ${
      isCreate
        ? buildToggleField("generateClientJwtCheckbox", "创建后立即生成客户端 JWT", true, "identity.generateClientJwt")
        : '<p class="text-helper">客户端 JWT 现在在身份卡片的“客户端 JWT / 重签 JWT”按钮里，不再需要到别处找。</p>'
    }
    <label class="field">${buildFieldLabel("UPDB 用户名", "identity.updbUsername")}<input name="updbUsername" value="" ${isCreate ? "" : 'placeholder="编辑时留空，不修改 enrollment"'} /></label>
    ${buildToggleField("isAdminCheckbox", "管理员身份", entity?.isAdmin, "identity.isAdmin")}
    ${buildAdvancedSection(
      `
    ${buildSingleSuggestionField(
      "authPolicyId",
      "认证策略",
      entity?.authPolicyId || "default",
      "default",
      "支持直接选 controller 里已有的 auth policy，也可以继续手输自定义 id 或名称。",
      dedupeSuggestions(
        getAuthPolicies().flatMap((item) => {
          const name = String(item?.name || "").trim();
          const id = String(item?.id || "").trim();
          return [
            name ? { value: name, title: name, meta: `${id || "-"}` } : null,
            id ? { value: id, title: id, meta: `${name || "-"}` } : null,
          ].filter(Boolean);
        }),
      ),
      "identity.authPolicyId",
    )}
    <label class="field">${buildFieldLabel("角色属性", "common.roleAttributes")}<input name="roleAttributes" value="${escapeHtml(ensureArray(entity?.roleAttributes).join(","))}" placeholder="ops,group-a" /></label>
    <label class="field">${buildFieldLabel("External ID", "identity.externalId")}<input name="externalId" value="${escapeHtml(entity?.externalId || "")}" /></label>
    <label class="field">${buildFieldLabel("默认 Hosting Cost", "identity.defaultHostingCost")}<input name="defaultHostingCost" type="number" min="0" value="${escapeHtml(entity?.defaultHostingCost ?? 0)}" /></label>
    <label class="field">${buildFieldLabel("默认 Hosting Precedence", "identity.defaultHostingPrecedence")}<select name="defaultHostingPrecedence"><option value="default" ${entity?.defaultHostingPrecedence === "default" || !entity?.defaultHostingPrecedence ? "selected" : ""}>default</option><option value="required" ${entity?.defaultHostingPrecedence === "required" ? "selected" : ""}>required</option><option value="failed" ${entity?.defaultHostingPrecedence === "failed" ? "selected" : ""}>failed</option></select></label>
    <label class="field">${buildFieldLabel("Tags JSON", "common.tags")}<textarea name="tagsJson" rows="4">${escapeHtml(formatJson(entity?.tags || {}))}</textarea></label>
    `,
      "Auth Policy 默认就是 default；Hosting Cost / Precedence 只有在你需要控制服务托管优先级时才需要改。",
    )}
  `;
}

export function renderConfigDialogBody() {
  if (!state.modal || state.modal.resourceType !== "configs") {
    return;
  }
  refs.dialogBody.innerHTML = buildDialogFields("configs", state.modal.mode, state.modal.entity);
  refreshDialogFieldStates();
  renderDialogCommandPreview();
}

export function setConfigJsonStatus(message, isError = false) {
  if (!state.modal || state.modal.resourceType !== "configs") {
    return;
  }
  state.modal.configJsonStatus = message;
  state.modal.configJsonError = isError;
  const status = refs.dialogBody.querySelector("[data-config-json-status]");
  if (!status) {
    return;
  }
  status.textContent = message;
  status.classList.toggle("is-error", isError);
}

function buildHostConfigDataFromDialog() {
  const mode = refs.dialogBody.querySelector('[name="configBuilderHostMode"]')?.value || "k8s";
  const namespace = refs.dialogBody.querySelector('[name="configBuilderNamespace"]')?.value || "default";
  const serviceName = refs.dialogBody.querySelector('[name="configBuilderServiceName"]')?.value || "";
  const customAddress = refs.dialogBody.querySelector('[name="configBuilderAddress"]')?.value || "";
  return {
    address: mode === "k8s" ? composeK8sServiceAddress(serviceName, namespace) : String(customAddress).trim(),
    port: normalizePort(refs.dialogBody.querySelector('[name="configBuilderPort"]')?.value, 80),
    protocol: refs.dialogBody.querySelector('[name="configBuilderProtocol"]')?.value === "udp" ? "udp" : "tcp",
  };
}

function buildInterceptConfigDataFromDialog() {
  const addresses = readDelimitedList(refs.dialogBody.querySelector('[name="configBuilderInterceptAddresses"]')?.value);
  const port = normalizePort(refs.dialogBody.querySelector('[name="configBuilderInterceptPort"]')?.value, 80);
  const protocol =
    refs.dialogBody.querySelector('[name="configBuilderInterceptProtocol"]')?.value === "udp" ? "udp" : "tcp";
  return {
    addresses: addresses.length ? addresses : [""],
    portRanges: [{ low: port, high: port }],
    protocols: [protocol],
  };
}

function updateHostConfigBuilderUi() {
  const mode = refs.dialogBody.querySelector('[name="configBuilderHostMode"]')?.value || "k8s";
  const namespace = refs.dialogBody.querySelector('[name="configBuilderNamespace"]')?.value || "default";
  const serviceName = refs.dialogBody.querySelector('[name="configBuilderServiceName"]')?.value || "";
  refs.dialogBody.querySelectorAll("[data-config-host-mode]").forEach((node) => {
    node.classList.toggle("hidden", node.dataset.configHostMode !== mode);
  });
  const portOptions = getK8sServicePortOptions(namespace, serviceName);
  const portInput = refs.dialogBody.querySelector('[name="configBuilderPort"]');
  if (portInput && mode === "k8s" && portOptions.length) {
    const validPortValues = new Set(portOptions.map((option) => String(option.value)));
    if (!validPortValues.has(String(portInput.value || ""))) {
      portInput.value = String(portOptions[0].value);
    }
  }
  const matchSlot = refs.dialogBody.querySelector("[data-k8s-service-match]");
  if (matchSlot) {
    matchSlot.innerHTML = buildMatchedK8sServicePreview(namespace, serviceName);
  }
  const preview = refs.dialogBody.querySelector("[data-config-host-preview]");
  if (!preview) {
    return;
  }
  const previewData = buildHostConfigDataFromDialog();
  preview.textContent =
    previewData.address || (mode === "k8s" ? "service.namespace.svc.cluster.local" : "example.internal");
  refreshVisibleComboboxes();
}

function syncConfigJsonFromBuilder() {
  if (!state.modal || state.modal.resourceType !== "configs") {
    return;
  }
  const typeName = getActiveConfigTypeName();
  if (!isSupportedConfigType(typeName)) {
    return;
  }

  if (typeName === "host.v1") {
    updateHostConfigBuilderUi();
  }
  const data =
    typeName === "host.v1" ? buildHostConfigDataFromDialog() : typeName === "intercept.v1" ? buildInterceptConfigDataFromDialog() : {};
  state.modal.configDraftData = data;
  state.modal.configRawJson = formatJson(data);

  const dataJson = refs.dialogBody.querySelector('textarea[name="dataJson"]');
  if (dataJson) {
    dataJson.value = state.modal.configRawJson;
  }
  setConfigJsonStatus("JSON 已按表单自动更新。");
}

function applyJsonToConfigBuilder() {
  if (!state.modal || state.modal.resourceType !== "configs") {
    return;
  }

  const dataJson = refs.dialogBody.querySelector('textarea[name="dataJson"]');
  if (!dataJson) {
    return;
  }

  try {
    const parsed = JSON.parse(dataJson.value.trim() || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("JSON 顶层必须是对象");
    }
    state.modal.configDraftData = parsed;
    state.modal.configRawJson = formatJson(parsed);
    state.modal.configJsonStatus = "已从 JSON 回填表单。";
    state.modal.configJsonError = false;
    renderConfigDialogBody();
  } catch (error) {
    setConfigJsonStatus(`JSON 解析失败: ${error.message}`, true);
  }
}

function appendPickerValue(targetName, sourceName) {
  const target = refs.dialogBody.querySelector(`[name="${targetName}"]`);
  const source = refs.dialogBody.querySelector(`[name="${sourceName}"]`);
  if (!(target instanceof HTMLInputElement) || !(source instanceof HTMLInputElement)) {
    return;
  }

  const incoming = readDelimitedList(source.value);
  if (!incoming.length) {
    return;
  }

  const current = readDelimitedList(target.value);
  incoming.forEach((value) => {
    if (!current.includes(value)) {
      current.push(value);
    }
  });
  target.value = current.join(",");
  source.value = "";
  markFieldTouched(targetName);
  target.dispatchEvent(new Event("input", { bubbles: true }));
}

export function handleDialogBodyInput(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }

  const targetName = target.getAttribute("name") || "";
  if (targetName) {
    markFieldTouched(targetName);
  }

  const comboboxFieldName = target.getAttribute("data-combobox-input");
  if (comboboxFieldName) {
    closeAllComboboxes(comboboxFieldName);
    renderComboboxMenu(comboboxFieldName, true);
  }

  if (!state.modal || state.modal.resourceType !== "configs") {
    refreshDialogFieldStates();
    return;
  }

  if (target.getAttribute("name") === "configTypeId") {
    const nextTypeName = getConfigTypeNameById(target.value);
    state.modal.configTypeId = target.value;
    state.modal.configDraftData = defaultConfigData(nextTypeName);
    state.modal.configRawJson = formatJson(state.modal.configDraftData);
    state.modal.configJsonExpanded = !isSupportedConfigType(nextTypeName);
    state.modal.configJsonStatus = isSupportedConfigType(nextTypeName)
      ? "表单会自动同步更新 JSON；需要时也可以从 JSON 回填表单。"
      : "当前类型没有专用表单，请直接编辑原始 JSON。";
    state.modal.configJsonError = false;
    renderConfigDialogBody();
    return;
  }

  if (target.getAttribute("name") === "name") {
    state.modal.configNameDraft = target.value;
    refreshDialogFieldStates();
    return;
  }

  if (target.getAttribute("name") === "tagsJson") {
    state.modal.configTagsDraft = target.value;
    refreshDialogFieldStates();
    return;
  }

  if (target.closest("[data-config-builder]")) {
    syncConfigJsonFromBuilder();
    refreshDialogFieldStates();
    return;
  }

  if (target.getAttribute("name") === "dataJson") {
    state.modal.configRawJson = target.value;
    setConfigJsonStatus("可直接编辑 JSON；需要同步回默认表单时，点“从 JSON 回填表单”。");
  }

  refreshDialogFieldStates();
}

export function handleDialogBodyClick(event) {
  if (!(event.target instanceof Element)) {
    return;
  }

  const comboboxOption = event.target.closest("[data-combobox-option]");
  if (comboboxOption instanceof HTMLElement) {
    const fieldName = comboboxOption.dataset.comboboxOption || "";
    const value = comboboxOption.dataset.value || "";
    const input = refs.dialogBody.querySelector(`[data-combobox-input="${fieldName}"]`);
    if (input instanceof HTMLInputElement) {
      input.value = value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    closeCombobox(fieldName);
    return;
  }

  const comboboxToggle = event.target.closest("[data-combobox-toggle]");
  if (comboboxToggle instanceof HTMLElement) {
    const fieldName = comboboxToggle.dataset.comboboxToggle || "";
    const menu = refs.dialogBody.querySelector(`[data-combobox-menu="${fieldName}"]`);
    const shouldOpen = menu instanceof HTMLElement ? menu.classList.contains("hidden") : true;
    closeAllComboboxes(fieldName);
    renderComboboxMenu(fieldName, shouldOpen, "");
    return;
  }

  const comboboxInput = event.target.closest("[data-combobox-input]");
  if (comboboxInput instanceof HTMLElement) {
    const fieldName = comboboxInput.dataset.comboboxInput || "";
    closeAllComboboxes(fieldName);
    renderComboboxMenu(fieldName, true, "");
    return;
  }

  const pickerButton = event.target.closest("[data-picker-add-target]");
  if (pickerButton) {
    appendPickerValue(pickerButton.dataset.pickerAddTarget, pickerButton.dataset.pickerSource);
    return;
  }

  const toggleButton = event.target.closest("[data-config-json-toggle]");
  if (toggleButton) {
    if (!state.modal || state.modal.resourceType !== "configs") {
      return;
    }
    state.modal.configJsonExpanded = !state.modal.configJsonExpanded;
    renderConfigDialogBody();
    return;
  }

  const applyButton = event.target.closest("[data-config-json-apply]");
  if (applyButton) {
    applyJsonToConfigBuilder();
    return;
  }

  const copyJsonButton = event.target.closest("[data-config-json-copy]");
  if (copyJsonButton) {
    const dataJson = refs.dialogBody.querySelector('textarea[name="dataJson"]');
    copyText(dataJson?.value || "", copyJsonButton, "复制 JSON 失败，请手动复制。");
    return;
  }

  closeAllComboboxes();
}

export function handleDialogBodyFocusIn(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const fieldName = target.getAttribute("data-combobox-input");
  if (!fieldName) {
    refreshDialogFieldStates();
    return;
  }
  closeAllComboboxes(fieldName);
  renderComboboxMenu(fieldName, true, "");
  refreshDialogFieldStates();
}

export function handleDialogBodyFocusOut() {
  window.setTimeout(() => {
    refreshDialogFieldStates();
  }, 0);
}

export function handleDialogCommandPreviewClick(event) {
  const button = event.target.closest("[data-copy-command]");
  if (!button) {
    return;
  }
  const blockKey = button.dataset.copyCommand || "";
  const commandBlock = refs.dialogCommandPreview.querySelector(`[data-command-block="${blockKey}"]`);
  copyText(commandBlock?.textContent || "", button, "复制示例命令失败，请手动复制。");
}

export function openDialog(resourceType, mode, entity = null) {
  const modalState = { resourceType, mode, entity, touchedFields: {} };
  if (resourceType === "configs") {
    const configTypeId = entity?.configTypeId || getConfigTypes()[0]?.id || "";
    const configTypeName = getConfigTypeNameById(configTypeId);
    modalState.configTypeId = configTypeId;
    modalState.configNameDraft = entity?.name || "";
    modalState.configTagsDraft = formatJson(entity?.tags || {});
    modalState.configDraftData = cloneJson(entity?.data || defaultConfigData(configTypeName));
    modalState.configRawJson = formatJson(modalState.configDraftData);
    modalState.configJsonExpanded = !isSupportedConfigType(configTypeName);
    modalState.configJsonStatus = isSupportedConfigType(configTypeName)
      ? "表单会自动同步更新 JSON；需要时也可以从 JSON 回填表单。"
      : "当前类型没有专用表单，请直接编辑原始 JSON。";
    modalState.configJsonError = false;
  }
  state.modal = modalState;
  refs.dialogKicker.textContent = mode === "create" ? "新增" : "编辑";
  refs.dialogTitle.textContent = `${mode === "create" ? "新增" : "编辑"}${resourceLabels[resourceType] || "资源"}`;
  refs.dialogSubmitButton.textContent = mode === "create" ? "创建" : "保存";
  refs.dialogBody.innerHTML = buildDialogFields(resourceType, mode, entity);
  refreshDialogFieldStates();
  renderDialogCommandPreview();
  refs.dialog.showModal();
}

export function closeDialog() {
  refs.dialog.close();
  closeAllComboboxes();
  state.modal = null;
  renderDialogCommandPreview();
}
