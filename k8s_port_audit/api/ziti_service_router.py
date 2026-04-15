from __future__ import annotations

import time
from typing import Any, Callable

from .ziti_admin import ZitiApiError
from .ziti_router_k8s import DEFAULT_ZITI_NAMESPACE, ensure_router_tunnel_mode, sanitize_k8s_name

RequestJsonFn = Callable[[str, str, dict[str, Any] | None, dict[str, str] | None], dict[str, Any]]

MANAGED_TAG_KEY = "microsegxManaged"
MANAGED_TAG_VALUE = "true"


def list_entities(request_json: RequestJsonFn, resource_type: str) -> list[dict[str, Any]]:
    payload = request_json(
        "GET",
        f"/edge/management/v1/{resource_type}",
        None,
        {"limit": "500"},
    )
    data = payload.get("data")
    return data if isinstance(data, list) else []


def get_entity(request_json: RequestJsonFn, resource_type: str, entity_id: str) -> dict[str, Any]:
    payload = request_json("GET", f"/edge/management/v1/{resource_type}/{entity_id}", None, None)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ZitiApiError(f"{resource_type} 返回数据格式异常", status_code=502, payload=payload)
    return data


def normalize_string_list(values: Any) -> list[str]:
    return [str(item).strip() for item in values if str(item).strip()] if isinstance(values, list) else []


def append_unique(values: list[str], value: str) -> list[str]:
    normalized = str(value or "").strip()
    items = [item for item in values if str(item or "").strip()]
    if normalized and normalized not in items:
        items.append(normalized)
    return items


def build_managed_name(prefix: str, service_name: str, router_name: str) -> str:
    return sanitize_k8s_name(f"{prefix}-{service_name}-{router_name}", prefix=prefix)


def build_router_selector_role(router_name: str) -> str:
    return sanitize_k8s_name(f"router-{router_name}", prefix="router")


def build_router_host_role(router_name: str) -> str:
    return sanitize_k8s_name(f"router-host-{router_name}", prefix="router-host")


def config_type_name(config: dict[str, Any]) -> str:
    config_type = config.get("configType")
    if isinstance(config_type, dict):
        return str(config_type.get("name") or "").strip()
    return str(config.get("configTypeId") or "").strip()


def build_entity_role_tokens(entity: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()

    entity_id = str(entity.get("id") or "").strip()
    if entity_id:
        tokens.add(f"@{entity_id}")

    entity_name = str(entity.get("name") or "").strip()
    if entity_name:
        tokens.add(f"@{entity_name}")

    for role_attribute in normalize_string_list(entity.get("roleAttributes")):
        tokens.add(f"#{role_attribute}")

    return tokens


def policy_matches_service(policy: dict[str, Any], service: dict[str, Any]) -> bool:
    service_roles = set(normalize_string_list(policy.get("serviceRoles")))
    if not service_roles:
        return False
    return not service_roles.isdisjoint(build_entity_role_tokens(service))


def collect_dial_identity_roles(
    request_json: RequestJsonFn,
    service: dict[str, Any],
) -> list[str]:
    dial_roles: list[str] = []
    for policy in list_entities(request_json, "service-policies"):
        if not isinstance(policy, dict):
            continue
        if str(policy.get("type") or "").strip() != "Dial":
            continue
        if not policy_matches_service(policy, service):
            continue
        for identity_role in normalize_string_list(policy.get("identityRoles")):
            dial_roles = append_unique(dial_roles, identity_role)
    return dial_roles


def pick_hosting_config(service: dict[str, Any], configs: list[dict[str, Any]]) -> dict[str, Any] | None:
    config_ids = {str(item).strip() for item in normalize_string_list(service.get("configs"))}
    if not config_ids:
        return None

    for config in configs:
        config_id = str(config.get("id") or "").strip()
        if not config_id or config_id not in config_ids:
            continue
        if config_type_name(config) in {"host.v1", "host.v2"}:
            return config
    return None


def get_router_identity(request_json: RequestJsonFn, router: dict[str, Any]) -> dict[str, Any]:
    router_id = str(router.get("id") or "").strip()
    if router_id:
        try:
            identity = get_entity(request_json, "identities", router_id)
            if identity:
                return identity
        except ZitiApiError as exc:
            if exc.status_code != 404:
                raise

    router_name = str(router.get("name") or "").strip()
    candidates = list_entities(request_json, "identities")
    for identity in candidates:
        if not isinstance(identity, dict):
            continue
        if str(identity.get("id") or "").strip() == router_id:
            return identity
        if str(identity.get("name") or "").strip() != router_name:
            continue
        identity_type = identity.get("type")
        identity_type_name = ""
        if isinstance(identity_type, dict):
            identity_type_name = str(identity_type.get("name") or identity_type.get("id") or "").strip()
        if identity_type_name.lower() == "router":
            return identity

    raise ValueError("找不到与 edge router 对应的 Router identity")


def find_existing_policy(
    items: list[dict[str, Any]],
    *,
    name: str,
    purpose: str,
    service_id: str,
    router_id: str,
) -> dict[str, Any] | None:
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("name") or "").strip() == name:
            return item
        tags = item.get("tags")
        if not isinstance(tags, dict):
            continue
        if (
            str(tags.get(MANAGED_TAG_KEY) or "").strip().lower() == MANAGED_TAG_VALUE
            and str(tags.get("microsegxPurpose") or "").strip() == purpose
            and str(tags.get("microsegxServiceId") or "").strip() == service_id
            and str(tags.get("microsegxRouterId") or "").strip() == router_id
        ):
            return item
    return None


def is_managed_policy_for_service(
    item: dict[str, Any],
    *,
    purpose: str,
    service_id: str,
) -> bool:
    tags = item.get("tags")
    if not isinstance(tags, dict):
        return False
    return (
        str(tags.get(MANAGED_TAG_KEY) or "").strip().lower() == MANAGED_TAG_VALUE
        and str(tags.get("microsegxPurpose") or "").strip() == purpose
        and str(tags.get("microsegxServiceId") or "").strip() == service_id
    )


def collect_stale_managed_policies(
    items: list[dict[str, Any]],
    *,
    purpose: str,
    service_id: str,
    router_id: str,
) -> list[dict[str, Any]]:
    stale_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not is_managed_policy_for_service(item, purpose=purpose, service_id=service_id):
            continue
        tags = item.get("tags") or {}
        if str(tags.get("microsegxRouterId") or "").strip() == router_id:
            continue
        stale_items.append(item)
    return stale_items


def delete_managed_policies(
    request_json: RequestJsonFn,
    *,
    resource_type: str,
    items: list[dict[str, Any]],
) -> list[dict[str, str]]:
    deleted: list[dict[str, str]] = []
    for item in items:
        entity_id = str(item.get("id") or "").strip()
        if not entity_id:
            continue
        request_json("DELETE", f"/edge/management/v1/{resource_type}/{entity_id}", None, None)
        tags = item.get("tags") or {}
        deleted.append(
            {
                "id": entity_id,
                "name": str(item.get("name") or "").strip(),
                "resourceType": resource_type,
                "purpose": str(tags.get("microsegxPurpose") or "").strip(),
                "routerId": str(tags.get("microsegxRouterId") or "").strip(),
            }
        )
    return deleted


def wait_for_service_terminator(
    request_json: RequestJsonFn,
    *,
    service_id: str,
    router_id: str,
    timeout_seconds: int = 20,
) -> dict[str, Any] | None:
    deadline = time.time() + max(timeout_seconds, 1)
    while time.time() <= deadline:
        for terminator in list_entities(request_json, "terminators"):
            if not isinstance(terminator, dict):
                continue
            service = terminator.get("service")
            router = terminator.get("router")
            if not isinstance(service, dict) or not isinstance(router, dict):
                continue
            if str(service.get("id") or "").strip() != service_id:
                continue
            if str(router.get("id") or "").strip() != router_id:
                continue
            return terminator
        time.sleep(1)
    return None


def ensure_service_router_attachment(
    request_json: RequestJsonFn,
    *,
    service_id: str,
    router_id: str,
    namespace: str = DEFAULT_ZITI_NAMESPACE,
    auto_enable_router: bool = True,
    wait_timeout_seconds: int = 20,
) -> dict[str, Any]:
    service = get_entity(request_json, "services", service_id)
    router = get_entity(request_json, "edge-routers", router_id)
    configs = list_entities(request_json, "configs")

    host_config = pick_hosting_config(service, configs)
    if host_config is None:
        raise ValueError("服务还没有 host.v1 或 host.v2 托管配置，先为服务创建宿主机配置")

    if not bool(router.get("isTunnelerEnabled")):
        if not auto_enable_router:
            raise ValueError("目标 router 还没有启用 tunneler，请先在路由器配置里启用后再试")
        request_json(
            "PATCH",
            f"/edge/management/v1/edge-routers/{router_id}",
            {"isTunnelerEnabled": True},
            None,
        )
        router = get_entity(request_json, "edge-routers", router_id)

    service_name = str(service.get("name") or service_id).strip()
    router_name = str(router.get("name") or router_id).strip()
    normalized_service_id = str(service.get("id") or service_id).strip()
    normalized_router_id = str(router.get("id") or router_id).strip()
    router_selector_role = build_router_selector_role(router_name)
    router_host_role = build_router_host_role(router_name)

    router_roles = normalize_string_list(router.get("roleAttributes"))
    if router_selector_role not in router_roles:
        router_roles = append_unique(router_roles, router_selector_role)
        request_json(
            "PATCH",
            f"/edge/management/v1/edge-routers/{router_id}",
            {"roleAttributes": router_roles},
            None,
        )
        router = get_entity(request_json, "edge-routers", router_id)

    router_workload = ensure_router_tunnel_mode(
        namespace,
        str(router.get("id") or router_id),
        router_name,
        enabled=True,
    )

    router_identity = get_router_identity(request_json, router)
    identity_roles = normalize_string_list(router_identity.get("roleAttributes"))
    if router_host_role not in identity_roles:
        identity_roles = append_unique(identity_roles, router_host_role)
        request_json(
            "PATCH",
            f"/edge/management/v1/identities/{router_identity['id']}",
            {"roleAttributes": identity_roles},
            None,
        )
        router_identity = get_entity(request_json, "identities", str(router_identity["id"]))

    bind_policy_name = build_managed_name("msx-bind", service_name, router_name)
    edge_router_policy_name = build_managed_name("msx-erp", service_name, router_name)
    serp_name = build_managed_name("msx-serp", service_name, router_name)
    dial_identity_roles = collect_dial_identity_roles(request_json, service)
    bind_tags = {
        MANAGED_TAG_KEY: MANAGED_TAG_VALUE,
        "microsegxPurpose": "router-bind",
        "microsegxServiceId": normalized_service_id,
        "microsegxRouterId": normalized_router_id,
    }
    edge_router_policy_tags = {
        MANAGED_TAG_KEY: MANAGED_TAG_VALUE,
        "microsegxPurpose": "edge-router-access",
        "microsegxServiceId": normalized_service_id,
        "microsegxRouterId": normalized_router_id,
    }
    serp_tags = {
        MANAGED_TAG_KEY: MANAGED_TAG_VALUE,
        "microsegxPurpose": "service-edge-router",
        "microsegxServiceId": normalized_service_id,
        "microsegxRouterId": normalized_router_id,
    }

    bind_policy_body = {
        "name": bind_policy_name,
        "type": "Bind",
        "semantic": "AnyOf",
        "identityRoles": [f"#{router_host_role}"],
        "serviceRoles": [f"@{normalized_service_id}"],
        "postureCheckRoles": [],
        "tags": bind_tags,
    }
    edge_router_policy_body = {
        "name": edge_router_policy_name,
        "semantic": "AnyOf",
        "identityRoles": dial_identity_roles,
        "edgeRouterRoles": [f"#{router_selector_role}"],
        "tags": edge_router_policy_tags,
    }
    serp_body = {
        "name": serp_name,
        "semantic": "AnyOf",
        "serviceRoles": [f"@{normalized_service_id}"],
        "edgeRouterRoles": [f"#{router_selector_role}"],
        "tags": serp_tags,
    }

    service_policies = list_entities(request_json, "service-policies")
    existing_bind_policy = find_existing_policy(
        service_policies,
        name=bind_policy_name,
        purpose="router-bind",
        service_id=normalized_service_id,
        router_id=normalized_router_id,
    )
    if existing_bind_policy is None:
        request_json("POST", "/edge/management/v1/service-policies", bind_policy_body, None)
    else:
        request_json(
            "PATCH",
            f"/edge/management/v1/service-policies/{existing_bind_policy['id']}",
            {
                "identityRoles": bind_policy_body["identityRoles"],
                "serviceRoles": bind_policy_body["serviceRoles"],
                "postureCheckRoles": [],
                "semantic": "AnyOf",
                "tags": bind_tags,
            },
            None,
        )
    bind_policy = next(
        (
            item
            for item in list_entities(request_json, "service-policies")
            if isinstance(item, dict) and str(item.get("name") or "").strip() == bind_policy_name
        ),
        None,
    )
    removed_policies = delete_managed_policies(
        request_json,
        resource_type="service-policies",
        items=collect_stale_managed_policies(
            service_policies,
            purpose="router-bind",
            service_id=normalized_service_id,
            router_id=normalized_router_id,
        ),
    )

    edge_router_policies = list_entities(request_json, "edge-router-policies")
    existing_edge_router_policy = find_existing_policy(
        edge_router_policies,
        name=edge_router_policy_name,
        purpose="edge-router-access",
        service_id=normalized_service_id,
        router_id=normalized_router_id,
    )
    if dial_identity_roles:
        if existing_edge_router_policy is None:
            request_json("POST", "/edge/management/v1/edge-router-policies", edge_router_policy_body, None)
        else:
            request_json(
                "PATCH",
                f"/edge/management/v1/edge-router-policies/{existing_edge_router_policy['id']}",
                {
                    "semantic": "AnyOf",
                    "identityRoles": edge_router_policy_body["identityRoles"],
                    "edgeRouterRoles": edge_router_policy_body["edgeRouterRoles"],
                    "tags": edge_router_policy_tags,
                },
                None,
            )
    elif existing_edge_router_policy is not None:
        request_json(
            "DELETE",
            f"/edge/management/v1/edge-router-policies/{existing_edge_router_policy['id']}",
            None,
            None,
        )
    edge_router_policy = next(
        (
            item
            for item in list_entities(request_json, "edge-router-policies")
            if isinstance(item, dict) and str(item.get("name") or "").strip() == edge_router_policy_name
        ),
        None,
    )
    removed_policies.extend(
        delete_managed_policies(
            request_json,
            resource_type="edge-router-policies",
            items=collect_stale_managed_policies(
                edge_router_policies,
                purpose="edge-router-access",
                service_id=normalized_service_id,
                router_id=normalized_router_id,
            ),
        )
    )

    serps = list_entities(request_json, "service-edge-router-policies")
    existing_serp = find_existing_policy(
        serps,
        name=serp_name,
        purpose="service-edge-router",
        service_id=normalized_service_id,
        router_id=normalized_router_id,
    )
    if existing_serp is None:
        request_json("POST", "/edge/management/v1/service-edge-router-policies", serp_body, None)
    else:
        request_json(
            "PATCH",
            f"/edge/management/v1/service-edge-router-policies/{existing_serp['id']}",
            {
                "semantic": "AnyOf",
                "serviceRoles": serp_body["serviceRoles"],
                "edgeRouterRoles": serp_body["edgeRouterRoles"],
                "tags": serp_tags,
            },
            None,
        )
    service_edge_router_policy = next(
        (
            item
            for item in list_entities(request_json, "service-edge-router-policies")
            if isinstance(item, dict) and str(item.get("name") or "").strip() == serp_name
        ),
        None,
    )
    removed_policies.extend(
        delete_managed_policies(
            request_json,
            resource_type="service-edge-router-policies",
            items=collect_stale_managed_policies(
                serps,
                purpose="service-edge-router",
                service_id=normalized_service_id,
                router_id=normalized_router_id,
            ),
        )
    )

    terminator = wait_for_service_terminator(
        request_json,
        service_id=normalized_service_id,
        router_id=normalized_router_id,
        timeout_seconds=wait_timeout_seconds,
    )
    if terminator is None:
        raise ValueError("服务已挂到 router，但 controller 还没有在超时时间内返回 terminator，请稍后刷新再看")

    return {
        "service": service,
        "router": router,
        "routerIdentity": router_identity,
        "routerWorkload": router_workload,
        "hostConfig": host_config,
        "edgeRouterPolicy": edge_router_policy,
        "bindPolicy": bind_policy,
        "serviceEdgeRouterPolicy": service_edge_router_policy,
        "terminator": terminator,
        "dialIdentityRoles": dial_identity_roles,
        "routerSelectorRole": router_selector_role,
        "routerHostRole": router_host_role,
        "removedPolicies": removed_policies,
    }
