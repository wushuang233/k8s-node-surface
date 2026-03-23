from __future__ import annotations

MISSING_MODULES: list[str] = []

try:
    import yaml
except ModuleNotFoundError:
    yaml = None
    MISSING_MODULES.append("PyYAML")

try:
    from kubernetes import client, config, watch
    from kubernetes.client.exceptions import ApiException
    from kubernetes.config.config_exception import ConfigException
except ModuleNotFoundError:
    client = None
    config = None
    watch = None
    ApiException = Exception
    ConfigException = Exception
    MISSING_MODULES.append("kubernetes")


def ensure_dependencies() -> None:
    if MISSING_MODULES:
        packages = ", ".join(MISSING_MODULES)
        raise RuntimeError(f"缺少依赖，请先安装: {packages}")


def load_kubernetes_config() -> str:
    ensure_dependencies()
    if config is None:
        raise RuntimeError("kubernetes 依赖不可用")

    try:
        config.load_incluster_config()
        return "incluster"
    except ConfigException:
        try:
            config.load_kube_config()
            return "kubeconfig"
        except ConfigException as exc:
            raise RuntimeError(
                "无法加载 Kubernetes 配置，请在集群内运行，或在本地提供 kubeconfig"
            ) from exc
