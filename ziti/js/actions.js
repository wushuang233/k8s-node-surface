import { buildDeleteCommand, renderDialogCommandPreview, shellQuote } from "./commands.js";
import {
  closeDialog,
  handleDialogBodyClick,
  handleDialogBodyFocusIn,
  handleDialogBodyFocusOut,
  handleDialogBodyInput,
  handleDialogCommandPreviewClick,
  openDialog,
} from "./dialog.js";
import { renderJwtPanel, renderSession, renderWorkspace } from "./render.js";
import {
  clearError,
  copyText,
  findEntity,
  refs,
  resourceLabels,
  showError,
  state,
  toJsonPayload,
} from "./shared.js";

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch (_error) {
    payload = {};
  }
  if (!response.ok) {
    throw new Error(payload.error || `${response.status} ${response.statusText}`);
  }
  return payload;
}

async function loadOverview() {
  if (!state.session) {
    state.overview = null;
    renderWorkspace();
    return;
  }
  const payload = await fetchJson("/api/ziti/overview", { headers: {} });
  state.overview = payload;
  renderWorkspace();
}

async function loadSession() {
  const payload = await fetchJson("/api/ziti/session", {
    headers: {},
  });
  state.session = payload.logged_in ? payload : null;
  refs.controllerUrl.value = payload.controller_url || payload.default_controller_url || "";
  if (!state.session && !refs.username.value && payload.default_username) {
    refs.username.value = payload.default_username;
  }
  refs.password.placeholder = payload.default_credentials_configured ? "留空则使用 Pod 内预设密码" : "";
  renderSession();
  if (state.session) {
    await loadOverview();
    return;
  }
  state.overview = null;
  renderWorkspace();
}

async function handleLogin(event) {
  event.preventDefault();
  clearError();
  state.busy = true;
  renderWorkspace();
  try {
    const payload = await fetchJson("/api/ziti/login", {
      method: "POST",
      body: JSON.stringify({
        controller_url: refs.controllerUrl.value.trim(),
        username: refs.username.value.trim(),
        password: refs.password.value,
      }),
    });
    state.session = payload;
    refs.password.value = "";
    await loadOverview();
  } catch (error) {
    showError(`登录失败: ${error.message}`);
  } finally {
    state.busy = false;
    renderWorkspace();
  }
}

async function handleLogout() {
  clearError();
  state.busy = true;
  renderWorkspace();
  try {
    await fetchJson("/api/ziti/logout", {
      method: "POST",
      body: JSON.stringify({}),
    });
    state.session = null;
    state.overview = null;
    state.lastJwt = null;
  } catch (error) {
    showError(`退出失败: ${error.message}`);
  } finally {
    state.busy = false;
    renderWorkspace();
  }
}

async function refreshOverview() {
  clearError();
  state.busy = true;
  renderWorkspace();
  try {
    await loadOverview();
  } catch (error) {
    showError(`刷新失败: ${error.message}`);
  } finally {
    state.busy = false;
    renderWorkspace();
  }
}

async function handleEntitySubmit(event) {
  event.preventDefault();
  if (!state.modal) {
    return;
  }

  clearError();
  state.busy = true;
  renderWorkspace();

  try {
    const payload = toJsonPayload(new FormData(refs.entityForm));
    const { resourceType, mode, entity } = state.modal;
    const baseUrl = `/api/ziti/${resourceType}`;
    const url = mode === "create" ? baseUrl : `${baseUrl}/${entity.id}`;
    const method = mode === "create" ? "POST" : "PATCH";
    const response = await fetchJson(url, {
      method,
      body: JSON.stringify(payload),
    });
    closeDialog();
    if (resourceType === "edge-routers" && response.data?.enrollmentJwt) {
      state.lastJwt = {
        name: response.data.name || response.data.id,
        jwt: response.data.enrollmentJwt,
        note: mode === "create" ? "新建 router 后生成的 enrollment JWT。" : "重新读取到的 enrollment JWT。",
        command:
          mode === "create"
            ? `ziti edge create edge-router ${shellQuote(response.data.name || response.data.id || "<router-name>")}`
            : `ziti edge re-enroll edge-router ${shellQuote(response.data.name || response.data.id || "<router-name>")}`,
      };
    }
    if (resourceType === "identities" && mode === "create" && payload.generateClientJwt) {
      const identityId = response.data?.id;
      const identityName = response.data?.name || payload.name;
      if (identityId) {
        const jwtResponse = await fetchJson(`/api/ziti/identities/${identityId}/client-jwt`, {
          method: "POST",
          body: JSON.stringify({ rotate: false, durationMinutes: 30 }),
        });
        const enrollment = jwtResponse.data?.enrollment || {};
        state.lastJwt = {
          name: identityName || identityId,
          jwt: enrollment.jwt || "",
          note: "新建 identity 后自动生成的客户端 enrollment JWT。JWT 只是入网令牌，真正的 JSON 身份文件需要在客户端执行 enroll 生成。",
          command: `ziti edge create enrollment ott ${shellQuote(identityName || identityId || "<identity-name>")} --jwt-output-file ./client.jwt`,
          enrollCommand: "ziti-edge-tunnel enroll --jwt ./client.jwt --identity ./client.json",
        };
      }
    }
    await loadOverview();
  } catch (error) {
    showError(`保存失败: ${error.message}`);
  } finally {
    state.busy = false;
    renderWorkspace();
  }
}

async function handleCardAction(event) {
  const button = event.target.closest("[data-action]");
  if (!button) {
    return;
  }

  const action = button.dataset.action;
  const resourceType = button.dataset.type;
  const entityId = button.dataset.id;
  const entity = findEntity(resourceType, entityId);
  if (!entity) {
    showError("找不到对应资源。");
    return;
  }

  if (action === "edit") {
    openDialog(resourceType, "edit", entity);
    return;
  }

  if (action === "delete") {
    const deleteCommand = buildDeleteCommand(resourceType, entity);
    const confirmed = window.confirm(
      `确认删除${resourceLabels[resourceType] || "资源"}：${entity.name || entity.id}？\n\n确认后页面会直接调用 controller API 执行删除。下面命令仅供参考：\n${deleteCommand}`,
    );
    if (!confirmed) {
      return;
    }
    clearError();
    state.busy = true;
    renderWorkspace();
    try {
      await fetchJson(`/api/ziti/${resourceType}/${entityId}`, {
        method: "DELETE",
        body: JSON.stringify({}),
      });
      await loadOverview();
    } catch (error) {
      showError(`删除失败: ${error.message}`);
    } finally {
      state.busy = false;
      renderWorkspace();
    }
    return;
  }

  if (action === "re-enroll") {
    clearError();
    state.busy = true;
    renderWorkspace();
    try {
      const response = await fetchJson(`/api/ziti/edge-routers/${entityId}/re-enroll`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      const router = response.data || {};
      state.lastJwt = {
        name: router.name || router.id,
        jwt: router.enrollmentJwt || "",
        note: "重新签发后的 enrollment JWT。发给新的 router 实例前请尽快使用。",
        command: `ziti edge re-enroll edge-router ${shellQuote(router.name || router.id || "<router-name>")}`,
      };
      await loadOverview();
    } catch (error) {
      showError(`重签 JWT 失败: ${error.message}`);
    } finally {
      state.busy = false;
      renderWorkspace();
    }
    return;
  }

  if (action === "deploy-k8s-router") {
    const workload = entity.k8sWorkload || null;
    const confirmed = window.confirm(
      workload
        ? `确认重新部署路由器 ${entity.name || entity.id} 到 K8s？\n\n页面会自动复用现有 Deployment / Service / PVC，并按当前 controller 地址重新下发配置。`
        : `确认把路由器 ${entity.name || entity.id} 部署到 K8s？\n\n页面会自动创建 Secret、ConfigMap、PVC、NodePort Service 和 Deployment，并尽量自动选择宿主机 IP 与 NodePort。`,
    );
    if (!confirmed) {
      return;
    }
    clearError();
    state.busy = true;
    renderWorkspace();
    try {
      const response = await fetchJson(`/api/ziti/edge-routers/${entityId}/deploy-k8s`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      const router = response.data || entity;
      const deployed = response.workload || router.k8sWorkload || {};
      state.lastJwt = null;
      await loadOverview();
      window.alert(
        `K8s 部署已完成。\n\nDeployment: ${deployed.deploymentName || "-"}\nNodePort: ${deployed.nodePort || "-"}\nPublic Host: ${deployed.publicHost || "-"}\n\n接下来等这张卡片变成 在线 / 已验证 / SYNC_DONE 即可。`,
      );
    } catch (error) {
      showError(`部署 router 到 K8s 失败: ${error.message}`);
    } finally {
      state.busy = false;
      renderWorkspace();
    }
    return;
  }

  if (action === "undeploy-k8s-router") {
    const confirmed = window.confirm(
      `确认删除路由器 ${entity.name || entity.id} 对应的 K8s 工作负载？\n\n这会删除 Deployment、Service、ConfigMap、Secret 和 PVC，但不会删除 controller 里的 router 记录。`,
    );
    if (!confirmed) {
      return;
    }
    clearError();
    state.busy = true;
    renderWorkspace();
    try {
      await fetchJson(`/api/ziti/edge-routers/${entityId}/deploy-k8s`, {
        method: "DELETE",
        body: JSON.stringify({}),
      });
      await loadOverview();
    } catch (error) {
      showError(`删除 router K8s 工作负载失败: ${error.message}`);
    } finally {
      state.busy = false;
      renderWorkspace();
    }
    return;
  }

  if (action === "identity-jwt" || action === "identity-jwt-rotate") {
    clearError();
    state.busy = true;
    renderWorkspace();
    try {
      const rotate = action === "identity-jwt-rotate";
      const response = await fetchJson(`/api/ziti/identities/${entityId}/client-jwt`, {
        method: "POST",
        body: JSON.stringify({ rotate, durationMinutes: 30 }),
      });
      const enrollment = response.data?.enrollment || {};
      const identityName = response.data?.identity?.name || entity.name || entity.id;
      const isReused = response.data?.reused && !rotate;
      state.lastJwt = {
        name: identityName,
        jwt: enrollment.jwt || "",
        note: rotate
          ? "已重新签发客户端 enrollment JWT。旧的未完成 OTT enrollment 已失效。"
          : isReused
            ? "当前 identity 已经有一条未完成的客户端 enrollment JWT，这里展示的是现有 JWT。JWT 只是入网令牌，真正的 JSON 身份文件需要在客户端执行 enroll 生成。"
            : "已为当前 identity 生成新的客户端 enrollment JWT。JWT 只是入网令牌，真正的 JSON 身份文件需要在客户端执行 enroll 生成。",
        command: rotate || !isReused
          ? `ziti edge create enrollment ott ${shellQuote(identityName || entityId || "<identity-name>")} --jwt-output-file ./client.jwt`
          : `ziti edge list enrollments ${shellQuote(`identity = "${identityName}" and method = "ott"`)} -j`,
        enrollCommand: "ziti-edge-tunnel enroll --jwt ./client.jwt --identity ./client.json",
      };
      await loadOverview();
    } catch (error) {
      showError(`${rotate ? "重签" : "获取"}客户端 JWT 失败: ${error.message}`);
    } finally {
      state.busy = false;
      renderWorkspace();
    }
  }
}

function copyJwt(event) {
  if (!state.lastJwt?.jwt) {
    return;
  }
  copyText(state.lastJwt.jwt, event?.currentTarget, "复制 JWT 失败，请手动复制。");
}

function copyJwtCommand(event) {
  if (!state.lastJwt?.command) {
    return;
  }
  copyText(state.lastJwt.command, event?.currentTarget, "复制示例命令失败，请手动复制。");
}

function copyJwtEnrollCommand(event) {
  if (!state.lastJwt?.enrollCommand) {
    return;
  }
  copyText(state.lastJwt.enrollCommand, event?.currentTarget, "复制示例 Enroll 命令失败，请手动复制。");
}

function clearJwt() {
  state.lastJwt = null;
  renderJwtPanel();
}

function onAddEntity() {
  openDialog(state.activeTab, "create");
}

function handleEntityFormLiveUpdate() {
  if (!state.modal) {
    return;
  }
  renderDialogCommandPreview();
}

function initEvents() {
  refs.loginForm.addEventListener("submit", handleLogin);
  refs.logoutButton.addEventListener("click", handleLogout);
  refs.refreshButton.addEventListener("click", refreshOverview);
  refs.copyJwtCommandButton.addEventListener("click", copyJwtCommand);
  refs.copyJwtEnrollButton.addEventListener("click", copyJwtEnrollCommand);
  refs.copyJwtButton.addEventListener("click", copyJwt);
  refs.clearJwtButton.addEventListener("click", clearJwt);
  refs.addEntityButton.addEventListener("click", onAddEntity);
  refs.contentPanel.addEventListener("click", handleCardAction);
  refs.entityForm.addEventListener("submit", handleEntitySubmit);
  refs.entityForm.addEventListener("input", handleEntityFormLiveUpdate);
  refs.entityForm.addEventListener("change", handleEntityFormLiveUpdate);
  refs.dialogCommandPreview.addEventListener("click", handleDialogCommandPreviewClick);
  refs.dialogBody.addEventListener("click", handleDialogBodyClick);
  refs.dialogBody.addEventListener("focusin", handleDialogBodyFocusIn);
  refs.dialogBody.addEventListener("focusout", handleDialogBodyFocusOut);
  refs.dialogBody.addEventListener("input", handleDialogBodyInput);
  refs.dialogBody.addEventListener("change", handleDialogBodyInput);
  refs.dialogCloseButton.addEventListener("click", closeDialog);
  refs.dialogCancelButton.addEventListener("click", closeDialog);
  refs.aliveOnlyCheckbox.addEventListener("change", () => {
    state.aliveOnly = refs.aliveOnlyCheckbox.checked;
    renderWorkspace();
  });
  refs.tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      state.activeTab = button.dataset.tab;
      renderWorkspace();
    });
  });
}

export async function boot() {
  initEvents();
  clearError();
  try {
    await loadSession();
  } catch (error) {
    showError(`初始化失败: ${error.message}`);
  }
}
