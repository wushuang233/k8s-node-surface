import {
  ensureArray,
  escapeHtml,
  getConfigMap,
  getConfigTypeNameById,
  getServiceMaxIdleInputValue,
  readDelimitedList,
  refs,
  state,
  toJsonPayload,
} from "./shared.js";

export function shellQuote(value) {
  return `'${String(value ?? "").replaceAll("'", "'\"'\"'")}'`;
}

function formatCliArgs(parts) {
  const filtered = ensureArray(parts).filter(Boolean);
  if (!filtered.length) {
    return "";
  }
  if (filtered.length <= 5) {
    return filtered.join(" ");
  }
  return `${filtered.slice(0, 5).join(" ")} \\\n  ${filtered.slice(5).join(" \\\n  ")}`;
}

function readCommandList(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  }
  return readDelimitedList(value);
}

function addCliStringFlag(parts, flag, value) {
  const text = String(value ?? "").trim();
  if (!text) {
    return;
  }
  parts.push(flag, shellQuote(text));
}

function addCliStringFlagUnlessDefault(parts, flag, value, defaultValue) {
  const text = String(value ?? "").trim();
  if (!text || text === String(defaultValue ?? "").trim()) {
    return;
  }
  parts.push(flag, shellQuote(text));
}

function addCliStringFlagIfChanged(parts, flag, value, originalValue) {
  const text = String(value ?? "").trim();
  const originalText = String(originalValue ?? "").trim();
  if (text === originalText || !text) {
    return;
  }
  parts.push(flag, shellQuote(text));
}

function addCliStringListFlag(parts, flag, value, { allowEmpty = false } = {}) {
  const items = readCommandList(value);
  if (!items.length && !allowEmpty) {
    return;
  }
  parts.push(flag, shellQuote(items.join(",")));
}

function addCliStringListFlagIfChanged(parts, flag, value, originalValue, { allowEmpty = false } = {}) {
  const currentItems = readCommandList(value);
  const originalItems = readCommandList(originalValue);
  if (currentItems.join(",") === originalItems.join(",")) {
    return;
  }
  if (!currentItems.length && !allowEmpty) {
    return;
  }
  parts.push(flag, shellQuote(currentItems.join(",")));
}

function addCliJsonFlag(parts, flag, value) {
  if (!value || typeof value !== "object" || !Object.keys(value).length) {
    return;
  }
  parts.push(flag, shellQuote(JSON.stringify(value)));
}

function addCliBooleanFlag(parts, flag, value, { explicit = false } = {}) {
  if (explicit) {
    parts.push(`${flag}=${value ? "true" : "false"}`);
    return;
  }
  if (value) {
    parts.push(flag);
  }
}

function addCliBooleanFlagIfChanged(parts, flag, value, originalValue) {
  if (Boolean(value) === Boolean(originalValue)) {
    return;
  }
  addCliBooleanFlag(parts, flag, value, { explicit: true });
}

function configCliReferences(configIds) {
  return readCommandList(configIds).map((configId) => getConfigMap().get(configId)?.name || configId);
}

function zitiResourceCommand(resourceType) {
  return (
    {
      configs: "config",
      "edge-routers": "edge-router",
      "edge-router-policies": "edge-router-policy",
      identities: "identity",
      "service-edge-router-policies": "service-edge-router-policy",
      "service-policies": "service-policy",
      services: "service",
    }[resourceType] || resourceType
  );
}

function modalCommandTarget(entity) {
  return String(entity?.id || entity?.name || "<id-or-name>").trim();
}

export function buildDeleteCommand(resourceType, entity) {
  return `ziti edge delete ${zitiResourceCommand(resourceType)} ${shellQuote(modalCommandTarget(entity))}`;
}

export function buildZitiCommandPreview(resourceType, mode, entity, payload) {
  const command = zitiResourceCommand(resourceType);
  const notes = [];
  const extraCommands = [];
  const base =
    mode === "create"
      ? ["ziti", "edge", "create", command, shellQuote(String(payload?.name || "<name>").trim() || "<name>")]
      : ["ziti", "edge", "update", command, shellQuote(modalCommandTarget(entity))];

  if (resourceType === "identities") {
    if (mode === "edit") {
      addCliStringFlagIfChanged(base, "--name", payload?.name, entity?.name);
      addCliStringFlagIfChanged(base, "--auth-policy", payload?.authPolicyId, entity?.authPolicyId);
      addCliStringListFlagIfChanged(base, "--role-attributes", payload?.roleAttributes, entity?.roleAttributes, { allowEmpty: true });
      addCliStringFlagIfChanged(base, "--external-id", payload?.externalId, entity?.externalId);
      addCliStringFlagIfChanged(base, "--default-hosting-cost", payload?.defaultHostingCost, entity?.defaultHostingCost);
      addCliStringFlagIfChanged(
        base,
        "--default-hosting-precedence",
        payload?.defaultHostingPrecedence,
        entity?.defaultHostingPrecedence,
      );
      addCliJsonFlag(base, "--tags-json", payload?.tags);
      if (Object.prototype.hasOwnProperty.call(payload || {}, "isAdmin")) {
        notes.push("identity 的管理员开关当前仍由页面直接调用 management API PATCH，CLI `update identity` 没有对应的 `--admin` 参数。");
      }
    } else {
      addCliStringFlagUnlessDefault(base, "--auth-policy", payload?.authPolicyId || "default", "default");
      addCliBooleanFlag(base, "--admin", payload?.isAdmin);
      addCliStringListFlag(base, "--role-attributes", payload?.roleAttributes);
      addCliStringFlag(base, "--external-id", payload?.externalId);
      addCliStringFlagUnlessDefault(base, "--default-hosting-cost", payload?.defaultHostingCost, "0");
      addCliStringFlagUnlessDefault(base, "--default-hosting-precedence", payload?.defaultHostingPrecedence, "default");
      addCliStringFlag(base, "--updb", payload?.updbUsername);
      addCliJsonFlag(base, "--tags-json", payload?.tags);
      if (payload?.generateClientJwt) {
        extraCommands.push(
          formatCliArgs([
            "ziti",
            "edge",
            "create",
            "enrollment",
            "ott",
            shellQuote(String(payload?.name || "<name>").trim() || "<name>"),
            "--jwt-output-file",
            shellQuote("./client.jwt"),
          ]),
        );
        notes.push("如果勾选“创建后立即生成客户端 JWT”，页面会在 identity 创建成功后，再追加一次 OTT enrollment。");
      }
    }
  } else if (resourceType === "service-policies") {
    if (mode === "create") {
      base.splice(5, 0, shellQuote(String(payload?.type || "Dial")));
      addCliStringFlagUnlessDefault(base, "--semantic", payload?.semantic || "AnyOf", "AnyOf");
    } else {
      addCliStringFlagIfChanged(base, "--name", payload?.name, entity?.name);
      if (Object.prototype.hasOwnProperty.call(payload || {}, "semantic")) {
        notes.push("service-policy 的 semantic 修改当前仍由页面直接调用 management API PATCH，CLI `update service-policy` 没有对应参数。");
      }
    }
    if (mode === "edit") {
      addCliStringListFlagIfChanged(base, "--identity-roles", payload?.identityRoles, entity?.identityRoles, { allowEmpty: true });
      addCliStringListFlagIfChanged(base, "--service-roles", payload?.serviceRoles, entity?.serviceRoles, { allowEmpty: true });
      addCliStringListFlagIfChanged(base, "--posture-check-roles", payload?.postureCheckRoles, entity?.postureCheckRoles, {
        allowEmpty: true,
      });
    } else {
      addCliStringListFlag(base, "--identity-roles", payload?.identityRoles);
      addCliStringListFlag(base, "--service-roles", payload?.serviceRoles);
      addCliStringListFlag(base, "--posture-check-roles", payload?.postureCheckRoles);
    }
    addCliJsonFlag(base, "--tags-json", payload?.tags);
  } else if (resourceType === "edge-router-policies") {
    if (mode === "create") {
      addCliStringFlagUnlessDefault(base, "--semantic", payload?.semantic || "AnyOf", "AnyOf");
    } else {
      addCliStringFlagIfChanged(base, "--name", payload?.name, entity?.name);
      if (Object.prototype.hasOwnProperty.call(payload || {}, "semantic")) {
        notes.push("edge-router-policy 的 semantic 修改当前仍由页面直接调用 management API PATCH，CLI `update edge-router-policy` 没有对应参数。");
      }
    }
    if (mode === "edit") {
      addCliStringListFlagIfChanged(base, "--identity-roles", payload?.identityRoles, entity?.identityRoles, { allowEmpty: true });
      addCliStringListFlagIfChanged(base, "--edge-router-roles", payload?.edgeRouterRoles, entity?.edgeRouterRoles, {
        allowEmpty: true,
      });
    } else {
      addCliStringListFlag(base, "--identity-roles", payload?.identityRoles);
      addCliStringListFlag(base, "--edge-router-roles", payload?.edgeRouterRoles);
    }
    addCliJsonFlag(base, "--tags-json", payload?.tags);
  } else if (resourceType === "service-edge-router-policies") {
    if (mode === "create") {
      addCliStringFlagUnlessDefault(base, "--semantic", payload?.semantic || "AnyOf", "AnyOf");
    } else {
      addCliStringFlagIfChanged(base, "--name", payload?.name, entity?.name);
      if (Object.prototype.hasOwnProperty.call(payload || {}, "semantic")) {
        notes.push(
          "service-edge-router-policy 的 semantic 修改当前仍由页面直接调用 management API PATCH，CLI `update service-edge-router-policy` 没有对应参数。",
        );
      }
    }
    if (mode === "edit") {
      addCliStringListFlagIfChanged(base, "--service-roles", payload?.serviceRoles, entity?.serviceRoles, { allowEmpty: true });
      addCliStringListFlagIfChanged(base, "--edge-router-roles", payload?.edgeRouterRoles, entity?.edgeRouterRoles, {
        allowEmpty: true,
      });
    } else {
      addCliStringListFlag(base, "--service-roles", payload?.serviceRoles);
      addCliStringListFlag(base, "--edge-router-roles", payload?.edgeRouterRoles);
    }
    addCliJsonFlag(base, "--tags-json", payload?.tags);
  } else if (resourceType === "services") {
    if (mode === "edit") {
      addCliStringFlagIfChanged(base, "--name", payload?.name, entity?.name);
    }
    const configRefs = configCliReferences(payload?.configs);
    if (mode === "edit") {
      addCliStringListFlagIfChanged(base, "--configs", configRefs, configCliReferences(entity?.configs), { allowEmpty: true });
      addCliStringListFlagIfChanged(base, "--role-attributes", payload?.roleAttributes, entity?.roleAttributes, { allowEmpty: true });
      addCliStringFlagIfChanged(base, "--terminator-strategy", payload?.terminatorStrategy, entity?.terminatorStrategy);
      addCliStringFlagIfChanged(base, "--max-idle-time", payload?.maxIdleTime, getServiceMaxIdleInputValue(entity));
    } else {
      addCliStringListFlag(base, "--configs", configRefs);
      addCliStringListFlag(base, "--role-attributes", payload?.roleAttributes);
      addCliStringFlagUnlessDefault(base, "--terminator-strategy", payload?.terminatorStrategy || "smartrouting", "smartrouting");
      addCliStringFlag(base, "--max-idle-time", payload?.maxIdleTime);
    }
    if (mode === "create" && payload?.encryptionRequired === false) {
      base.push("--encryption", "OFF");
    }
    addCliJsonFlag(base, "--tags-json", payload?.tags);
  } else if (resourceType === "configs") {
    const configTypeId = String(payload?.configTypeId || state.modal?.configTypeId || entity?.configTypeId || "").trim();
    const configTypeName = getConfigTypeNameById(configTypeId) || entity?.configType?.name || configTypeId || "<config-type>";
    if (mode === "create") {
      base.splice(5, 0, shellQuote(configTypeName), shellQuote(JSON.stringify(payload?.data || {})));
    } else {
      addCliStringFlag(base, "--name", payload?.name);
      base.push("--data", shellQuote(JSON.stringify(payload?.data || {})));
    }
    addCliJsonFlag(base, "--tags-json", payload?.tags);
  } else if (resourceType === "edge-routers") {
    if (mode === "edit") {
      addCliStringFlagIfChanged(base, "--name", payload?.name, entity?.name);
      addCliBooleanFlagIfChanged(base, "--disabled", payload?.disabled, entity?.disabled);
      addCliBooleanFlagIfChanged(base, "--no-traversal", payload?.noTraversal, entity?.noTraversal);
      addCliBooleanFlagIfChanged(base, "--tunneler-enabled", payload?.isTunnelerEnabled, entity?.isTunnelerEnabled);
      addCliStringFlagIfChanged(base, "--cost", payload?.cost, entity?.cost);
      addCliStringListFlagIfChanged(base, "--role-attributes", payload?.roleAttributes, entity?.roleAttributes, { allowEmpty: true });
    } else {
      addCliBooleanFlag(base, "--disabled", payload?.disabled);
      addCliBooleanFlag(base, "--no-traversal", payload?.noTraversal);
      addCliBooleanFlag(base, "--tunneler-enabled", payload?.isTunnelerEnabled);
      addCliStringFlagUnlessDefault(base, "--cost", payload?.cost, "0");
      addCliStringListFlag(base, "--role-attributes", payload?.roleAttributes);
    }
    addCliJsonFlag(base, "--tags-json", payload?.tags);
  }

  return {
    primary: formatCliArgs(base),
    secondary: mode === "edit" ? buildDeleteCommand(resourceType, entity) : "",
    extraCommands,
    notes,
  };
}

export function renderDialogCommandPreview() {
  if (!state.modal || !refs.dialogCommandPreview) {
    refs.dialogCommandPreview?.classList.add("hidden");
    if (refs.dialogCommandPreview) {
      refs.dialogCommandPreview.innerHTML = "";
    }
    return;
  }

  try {
    const payload = toJsonPayload(new FormData(refs.entityForm));
    const preview = buildZitiCommandPreview(state.modal.resourceType, state.modal.mode, state.modal.entity, payload);
    refs.dialogCommandPreview.innerHTML = `
      <section class="builder-card command-preview-card">
        <div class="builder-header">
          <div>
            <p class="section-kicker">参考示例</p>
            <h3>页面会直接执行，下面只是 CLI 参考</h3>
          </div>
          <span class="pill">${state.modal.mode === "create" ? "create" : "update"}</span>
        </div>
        <p class="text-helper">点击底部“创建 / 保存”后，页面会直接调用 controller management API 完成操作；以下命令只用于排障、复现或迁移到 CLI。</p>
        <p class="text-helper">如果你要手动运行这些命令，默认还需要先执行过 <code>ziti edge login</code>。</p>
        <pre class="json-block mono" data-command-block="primary">${escapeHtml(preview.primary)}</pre>
        <div class="command-preview-actions">
          <button type="button" class="button-muted compact-button" data-copy-command="primary">复制示例命令</button>
        </div>
        ${
          preview.secondary
            ? `
        <p class="text-helper">如果你后面想在命令行里复现删除动作，对应示例也一并放在下面。</p>
        <pre class="json-block mono" data-command-block="secondary">${escapeHtml(preview.secondary)}</pre>
        <div class="command-preview-actions">
          <button type="button" class="button-muted compact-button" data-copy-command="secondary">复制删除示例</button>
        </div>
        `
            : ""
        }
        ${
          ensureArray(preview.extraCommands).length
            ? ensureArray(preview.extraCommands)
                .map(
                  (commandText, index) => `
        <p class="text-helper">如果你想在命令行里复现页面里的后续动作，下面是附加示例。</p>
        <pre class="json-block mono" data-command-block="extra-${index}">${escapeHtml(commandText)}</pre>
        <div class="command-preview-actions">
          <button type="button" class="button-muted compact-button" data-copy-command="extra-${index}">复制附加示例</button>
        </div>
        `,
                )
                .join("")
            : ""
        }
        ${
          ensureArray(preview.notes).length
            ? ensureArray(preview.notes)
                .map((note) => `<p class="text-helper">${escapeHtml(note)}</p>`)
                .join("")
            : ""
        }
      </section>
    `;
  } catch (error) {
    refs.dialogCommandPreview.innerHTML = `
      <section class="builder-card command-preview-card">
        <div class="builder-header">
          <div>
            <p class="section-kicker">参考示例</p>
            <h3>参考命令暂不可用</h3>
          </div>
          <span class="pill warn">待修正</span>
        </div>
        <p class="text-helper is-error">当前表单里有尚未修正的 JSON，因此暂时无法生成参考命令：${escapeHtml(error.message || String(error))}</p>
      </section>
    `;
  }

  refs.dialogCommandPreview.classList.remove("hidden");
}
