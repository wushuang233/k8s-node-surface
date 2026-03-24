from __future__ import annotations

"""Kubernetes 系统组件识别规则。

默认通过三类强信号识别 Kubernetes 系统组件：
1. 位于 kube-system
2. 命中明确的系统标签
3. 命中明确的系统组件名

NodeListener 仍然属于宿主机直接暴露面，不在“隐藏 K8s 系统组件”按钮的默认隐藏范围里。
如果需要扩展到其他命名空间或组件，再通过 NV_SYSTEM_GROUPS 显式补充。
"""

import os
from dataclasses import dataclass
from fnmatch import fnmatch
from functools import lru_cache

from ..domain import ExposureCandidate


EXACT_NAMESPACE_ROLES = {
    "kube-system": "kubernetes-core",
}

SYSTEM_LABEL_ROLES = {
    ("k8s-app", "kube-dns"): "kubernetes-core",
    ("k8s-app", "coredns"): "kubernetes-core",
    ("k8s-app", "metrics-server"): "kubernetes-core",
    ("k8s-app", "kube-proxy"): "kubernetes-core",
    ("component", "kube-apiserver"): "kubernetes-control-plane",
    ("component", "kube-scheduler"): "kubernetes-control-plane",
    ("component", "kube-controller-manager"): "kubernetes-control-plane",
    ("component", "etcd"): "kubernetes-control-plane",
    ("app.kubernetes.io/name", "coredns"): "kubernetes-core",
    ("app.kubernetes.io/name", "kube-dns"): "kubernetes-core",
    ("app.kubernetes.io/name", "metrics-server"): "kubernetes-core",
    ("app.kubernetes.io/name", "kube-proxy"): "kubernetes-core",
    ("app.kubernetes.io/name", "kube-apiserver"): "kubernetes-control-plane",
    ("app.kubernetes.io/name", "kube-scheduler"): "kubernetes-control-plane",
    ("app.kubernetes.io/name", "kube-controller-manager"): "kubernetes-control-plane",
    ("app.kubernetes.io/name", "etcd"): "kubernetes-control-plane",
}

BUILTIN_NAME_RULES = (
    ("coredns", "kubernetes-core"),
    ("coredns-*", "kubernetes-core"),
    ("kube-dns", "kubernetes-core"),
    ("kube-dns-*", "kubernetes-core"),
    ("metrics-server", "kubernetes-core"),
    ("metrics-server-*", "kubernetes-core"),
    ("kube-proxy", "kubernetes-core"),
    ("kube-proxy-*", "kubernetes-core"),
    ("kube-apiserver", "kubernetes-control-plane"),
    ("kube-apiserver-*", "kubernetes-control-plane"),
    ("kube-scheduler", "kubernetes-control-plane"),
    ("kube-scheduler-*", "kubernetes-control-plane"),
    ("kube-controller-manager", "kubernetes-control-plane"),
    ("kube-controller-manager-*", "kubernetes-control-plane"),
    ("etcd", "kubernetes-control-plane"),
    ("etcd-*", "kubernetes-control-plane"),
)

@dataclass(frozen=True)
class PlatformRule:
    namespace_pattern: str
    name_pattern: str
    role: str


def normalized(value: str | None) -> str:
    return (value or "").strip().lower()


def pattern_matches(value: str, pattern: str) -> bool:
    return fnmatch(value, pattern)


def parse_system_group_entry(entry: str) -> PlatformRule | None:
    token = entry.strip()
    if not token:
        return None

    role = "custom-platform"
    if "=" in token:
        role_text, token = token.split("=", 1)
        role = normalized(role_text) or role

    namespace_pattern = token
    name_pattern = "*"
    if "/" in token:
        namespace_pattern, name_pattern = token.split("/", 1)

    namespace_pattern = normalized(namespace_pattern) or "*"
    name_pattern = normalized(name_pattern) or "*"
    return PlatformRule(namespace_pattern=namespace_pattern, name_pattern=name_pattern, role=role)


@lru_cache(maxsize=1)
def extra_system_group_rules() -> tuple[PlatformRule, ...]:
    raw = os.getenv("NV_SYSTEM_GROUPS", "")
    rules: list[PlatformRule] = []
    for separator in ("\n", ";"):
        raw = raw.replace(separator, ",")

    for entry in raw.split(","):
        rule = parse_system_group_entry(entry)
        if rule is not None:
            rules.append(rule)
    return tuple(rules)


def namespace_role(namespace: str) -> str | None:
    return EXACT_NAMESPACE_ROLES.get(namespace)


def label_role(labels: dict[str, str] | None) -> str | None:
    normalized_labels = {
        normalized(key): normalized(value)
        for key, value in (labels or {}).items()
        if key and value
    }
    for (label_key, label_value), role in SYSTEM_LABEL_ROLES.items():
        if normalized_labels.get(label_key) == label_value:
            return role
    return None


def builtin_name_role(resource_name: str) -> str | None:
    for pattern, role in BUILTIN_NAME_RULES:
        if pattern_matches(resource_name, pattern):
            return role
    return None


def rule_role(namespace: str, resource_name: str) -> str | None:
    for rule in extra_system_group_rules():
        if pattern_matches(namespace, rule.namespace_pattern) and pattern_matches(
            resource_name,
            rule.name_pattern,
        ):
            return rule.role
    return None


def platform_role_for_candidate(candidate: ExposureCandidate) -> str | None:
    namespace = normalized(candidate.get("namespace"))
    resource_name = normalized(candidate.get("group_name") or candidate.get("resource_name"))
    labels = candidate.get("labels") or {}
    reason = candidate.get("reason")
    if reason == "node_full_scan":
        return None

    if namespace and namespace != "-":
        role = namespace_role(namespace)
        if role:
            return role

    role = label_role(labels)
    if role:
        return role

    if resource_name:
        role = builtin_name_role(resource_name)
        if role:
            return role

    if resource_name:
        role = rule_role(namespace or "*", resource_name)
        if role:
            return role

    return None
