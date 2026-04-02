from __future__ import annotations

import json
import os
import secrets
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from ..runtime.dependencies import ApiException, client

DEFAULT_ZITI_NAMESPACE = "openziti"
DEFAULT_ZITI_SERVICE = "ziti-controller-client"
DEFAULT_ZITI_FALLBACK_URL = os.getenv(
    "ZITI_DEFAULT_CONTROLLER_URL",
    "https://ziti-controller-client.openziti.svc.cluster.local:1280",
)
DEFAULT_ZITI_USERNAME = os.getenv("ZITI_DEFAULT_USERNAME", "").strip()
DEFAULT_ZITI_PASSWORD = os.getenv("ZITI_DEFAULT_PASSWORD", "")
ZITI_SESSION_COOKIE = "ziti_session"
ZITI_RESOURCE_TYPES = {
    "configs",
    "edge-routers",
    "edge-router-policies",
    "identities",
    "service-edge-router-policies",
    "service-policies",
    "services",
}


def parse_iso_datetime(value: str | None) -> float | None:
    if not value:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def normalize_controller_url(controller_url: str | None) -> str:
    if not controller_url:
        return DEFAULT_ZITI_FALLBACK_URL

    normalized = controller_url.strip()
    if not normalized:
        return DEFAULT_ZITI_FALLBACK_URL

    if "://" not in normalized:
        normalized = f"https://{normalized}"

    return normalized.rstrip("/")


def resolve_default_controller_username() -> str:
    return DEFAULT_ZITI_USERNAME


def resolve_default_controller_password() -> str:
    return DEFAULT_ZITI_PASSWORD


def default_controller_credentials_configured() -> bool:
    return bool(DEFAULT_ZITI_USERNAME and DEFAULT_ZITI_PASSWORD)


def error_message_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return str(payload or "unknown error")

    error = payload.get("error")
    if isinstance(error, dict):
        cause = error.get("cause")
        if isinstance(cause, dict):
            for key in ("message", "reason", "field"):
                value = cause.get(key)
                if value:
                    return str(value)
        if error.get("message"):
            return str(error["message"])

    if payload.get("message"):
        return str(payload["message"])

    return json.dumps(payload, ensure_ascii=False)


class ZitiApiError(RuntimeError):
    def __init__(self, message: str, status_code: int = 500, payload: Any | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass
class ZitiSession:
    controller_url: str
    token: str
    expires_at: float | None
    identity_id: str | None
    identity_name: str | None
    username: str

    def is_expired(self) -> bool:
        return self.expires_at is not None and time.time() >= self.expires_at


class ZitiSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ZitiSession] = {}

    def create(self, session: ZitiSession) -> str:
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = session
        self.prune()
        return session_id

    def get(self, session_id: str | None) -> ZitiSession | None:
        if not session_id:
            return None

        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired():
            self.delete(session_id)
            return None
        return session

    def delete(self, session_id: str | None) -> None:
        if not session_id:
            return
        self._sessions.pop(session_id, None)

    def prune(self) -> None:
        expired = [session_id for session_id, session in self._sessions.items() if session.is_expired()]
        for session_id in expired:
            self._sessions.pop(session_id, None)


def ziti_cookie_header(session_id: str, max_age: int = 1800) -> str:
    cookie = SimpleCookie()
    cookie[ZITI_SESSION_COOKIE] = session_id
    morsel = cookie[ZITI_SESSION_COOKIE]
    morsel["httponly"] = True
    morsel["path"] = "/"
    morsel["samesite"] = "Lax"
    morsel["max-age"] = str(max_age)
    return morsel.OutputString()


def expired_ziti_cookie_header() -> str:
    cookie = SimpleCookie()
    cookie[ZITI_SESSION_COOKIE] = ""
    morsel = cookie[ZITI_SESSION_COOKIE]
    morsel["httponly"] = True
    morsel["path"] = "/"
    morsel["samesite"] = "Lax"
    morsel["max-age"] = "0"
    morsel["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
    return morsel.OutputString()


def read_ziti_session_id(cookie_header: str | None) -> str | None:
    if not cookie_header:
        return None

    cookie = SimpleCookie()
    cookie.load(cookie_header)
    morsel = cookie.get(ZITI_SESSION_COOKIE)
    if morsel is None:
        return None
    return morsel.value or None


def resolve_default_controller_url(
    namespace: str = DEFAULT_ZITI_NAMESPACE,
    service_name: str = DEFAULT_ZITI_SERVICE,
) -> str:
    if client is None:
        return DEFAULT_ZITI_FALLBACK_URL

    try:
        api = client.CoreV1Api()
        service = api.read_namespaced_service(service_name, namespace)
    except ApiException:
        return DEFAULT_ZITI_FALLBACK_URL
    except Exception:
        return DEFAULT_ZITI_FALLBACK_URL

    cluster_ip = getattr(service.spec, "cluster_ip", None) or getattr(service.spec, "clusterIP", None)
    service_type = getattr(service.spec, "type", None) or ""
    ports = getattr(service.spec, "ports", None) or []
    port = 1280
    node_port = None
    if ports:
        port = getattr(ports[0], "port", None) or port
        node_port = getattr(ports[0], "node_port", None) or getattr(ports[0], "nodePort", None)

    if service_type == "NodePort" and node_port:
        try:
            node_list = api.list_node().items
            if node_list:
                addresses = getattr(node_list[0].status, "addresses", None) or []
                for address in addresses:
                    if getattr(address, "type", "") == "InternalIP" and getattr(address, "address", ""):
                        return f"https://{address.address}:{node_port}"
        except Exception:
            pass

    if cluster_ip:
        return f"https://{cluster_ip}:{port}"
    return DEFAULT_ZITI_FALLBACK_URL


def resolve_default_service_host_candidates(
    namespace: str = DEFAULT_ZITI_NAMESPACE,
    service_name: str = DEFAULT_ZITI_SERVICE,
) -> set[str]:
    candidates = {
        service_name,
        f"{service_name}.{namespace}",
        f"{service_name}.{namespace}.svc",
        f"{service_name}.{namespace}.svc.cluster.local",
    }

    if client is None:
        return candidates

    try:
        api = client.CoreV1Api()
        service = api.read_namespaced_service(service_name, namespace)
        cluster_ip = getattr(service.spec, "cluster_ip", None) or getattr(service.spec, "clusterIP", None)
        if cluster_ip:
            candidates.add(str(cluster_ip))
    except Exception:
        return candidates

    return candidates


class ZitiManagementClient:
    def __init__(self, controller_url: str) -> None:
        self.controller_url = normalize_controller_url(controller_url)
        self._ssl_context = ssl._create_unverified_context()
        # Ignore pod-level HTTP(S)_PROXY when talking to the controller directly.
        self._opener = build_opener(
            ProxyHandler({}),
            HTTPHandler(),
            HTTPSHandler(context=self._ssl_context),
        )

    def authenticate(self, username: str, password: str) -> dict[str, Any]:
        payload = self.request_json(
            "POST",
            "/edge/management/v1/authenticate",
            json_body={"username": username, "password": password},
            query={"method": "password"},
        )
        data = payload.get("data")
        if not isinstance(data, dict) or not data.get("token"):
            raise ZitiApiError("controller 未返回会话 token", status_code=502, payload=payload)
        return data

    def list_entities(self, resource_type: str, limit: int = 500) -> list[dict[str, Any]]:
        payload = self.request_json(
            "GET",
            f"/edge/management/v1/{resource_type}",
            query={"limit": str(limit)},
        )
        data = payload.get("data")
        if not isinstance(data, list):
            raise ZitiApiError("controller 返回的数据格式异常", status_code=502, payload=payload)
        return data

    def get_entity(self, resource_type: str, entity_id: str) -> dict[str, Any]:
        payload = self.request_json("GET", f"/edge/management/v1/{resource_type}/{entity_id}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ZitiApiError("controller 返回的数据格式异常", status_code=502, payload=payload)
        return data

    def create_entity(self, resource_type: str, body: dict[str, Any]) -> dict[str, Any]:
        payload = self.request_json("POST", f"/edge/management/v1/{resource_type}", json_body=body)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ZitiApiError("controller 返回的数据格式异常", status_code=502, payload=payload)
        entity_id = data.get("id")
        if entity_id:
            return self.get_entity(resource_type, str(entity_id))
        return data

    def update_entity(self, resource_type: str, entity_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self.request_json(
            "PATCH",
            f"/edge/management/v1/{resource_type}/{entity_id}",
            json_body=body,
        )
        return self.get_entity(resource_type, entity_id)

    def delete_entity(self, resource_type: str, entity_id: str) -> None:
        self.request_json("DELETE", f"/edge/management/v1/{resource_type}/{entity_id}")

    def reenroll_edge_router(self, entity_id: str) -> dict[str, Any]:
        self.request_json("POST", f"/edge/management/v1/edge-routers/{entity_id}/re-enroll")
        return self.get_entity("edge-routers", entity_id)

    def request_json(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
        session_token: str | None = None,
    ) -> dict[str, Any]:
        try:
            return self.request_json_direct(
                method=method,
                path=path,
                json_body=json_body,
                query=query,
                session_token=session_token,
            )
        except ZitiApiError as exc:
            if not self.should_fallback_to_service_proxy(exc):
                raise
        return self.request_json_via_service_proxy(
            method=method,
            path=path,
            json_body=json_body,
            query=query,
            session_token=session_token,
        )

    def request_json_direct(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
        session_token: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self.controller_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"

        headers = {"Accept": "application/json"}
        data: bytes | None = None
        if json_body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        if session_token:
            headers["zt-session"] = session_token

        request = Request(url=url, method=method, data=data, headers=headers)
        try:
            with self._opener.open(request, timeout=15) as response:
                raw_body = response.read()
                if not raw_body:
                    return {}
                return json.loads(raw_body.decode("utf-8"))
        except HTTPError as exc:
            raw_body = exc.read().decode("utf-8", errors="replace")
            payload: Any
            try:
                payload = json.loads(raw_body) if raw_body else {}
            except json.JSONDecodeError:
                payload = {"message": raw_body}
            raise ZitiApiError(
                error_message_from_payload(payload),
                status_code=exc.code,
                payload=payload,
            ) from exc
        except URLError as exc:
            raise ZitiApiError(f"无法连接 Ziti controller: {exc.reason}", status_code=502) from exc
        except ssl.SSLError as exc:
            raise ZitiApiError(f"无法连接 Ziti controller: {exc}", status_code=502) from exc

    def request_json_via_service_proxy(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
        session_token: str | None = None,
    ) -> dict[str, Any]:
        if client is None:
            raise ZitiApiError("当前环境不可用 Kubernetes service proxy", status_code=502)

        header_params = {"Accept": "application/json"}
        if session_token:
            header_params["zt-session"] = session_token
        if json_body is not None:
            header_params["Content-Type"] = "application/json; charset=utf-8"

        proxy_path = (
            f"/api/v1/namespaces/{DEFAULT_ZITI_NAMESPACE}/services/"
            f"https:{DEFAULT_ZITI_SERVICE}:1280/proxy{path}"
        )
        api_client = client.ApiClient()

        try:
            response = api_client.call_api(
                proxy_path,
                method,
                query_params=list((query or {}).items()),
                body=json_body,
                header_params=header_params,
                response_type=None,
                auth_settings=["BearerToken"],
                _return_http_data_only=True,
                _preload_content=False,
            )
            raw_body = response.data.decode("utf-8") if getattr(response, "data", None) else ""
            return json.loads(raw_body) if raw_body else {}
        except ApiException as exc:
            payload: Any
            raw_body = getattr(exc, "body", None) or ""
            try:
                payload = json.loads(raw_body) if raw_body else {}
            except json.JSONDecodeError:
                payload = {"message": raw_body}
            raise ZitiApiError(
                error_message_from_payload(payload) or str(exc),
                status_code=getattr(exc, "status", 502) or 502,
                payload=payload,
            ) from exc
        except Exception as exc:
            raise ZitiApiError(f"通过 Kubernetes proxy 访问 controller 失败: {exc}", status_code=502) from exc

    def should_fallback_to_service_proxy(self, exc: ZitiApiError) -> bool:
        if exc.status_code not in {0, 502, 503, 504}:
            return False
        if client is None:
            return False

        hostname = (urlsplit(self.controller_url).hostname or "").strip().lower()
        if not hostname:
            return True

        return hostname in {value.lower() for value in resolve_default_service_host_candidates()}


def make_ziti_session(controller_url: str, username: str, auth_payload: dict[str, Any]) -> ZitiSession:
    identity = auth_payload.get("identity") or {}
    expires_at = parse_iso_datetime(auth_payload.get("expiresAt"))
    if expires_at is None and auth_payload.get("expirationSeconds"):
        try:
            expires_at = time.time() + int(auth_payload["expirationSeconds"]) - 15
        except (TypeError, ValueError):
            expires_at = None

    return ZitiSession(
        controller_url=normalize_controller_url(controller_url),
        token=str(auth_payload["token"]),
        expires_at=expires_at,
        identity_id=str(identity.get("id")) if identity.get("id") else None,
        identity_name=str(identity.get("name")) if identity.get("name") else None,
        username=username,
    )
