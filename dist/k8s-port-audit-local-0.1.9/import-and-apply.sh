#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_IMAGE_TAR="$(find "${SCRIPT_DIR}" -maxdepth 1 -type f -name 'k8s-port-audit-*.tar' | sort | tail -n 1 || true)"
IMAGE_TAR="${1:-${DEFAULT_IMAGE_TAR}}"
MANIFEST_PATH="${2:-${SCRIPT_DIR}/k8s-port-audit-local.yaml}"

if [[ -z "${IMAGE_TAR}" || ! -f "${IMAGE_TAR}" ]]; then
  echo "找不到镜像 tar。预期路径类似：${SCRIPT_DIR}/k8s-port-audit-*.tar" >&2
  exit 1
fi

if [[ ! -f "${MANIFEST_PATH}" ]]; then
  echo "找不到清单文件: ${MANIFEST_PATH}" >&2
  exit 1
fi

if command -v k3s >/dev/null 2>&1 && [[ -S /run/k3s/containerd/containerd.sock ]]; then
  CTR_IMPORT_CMD=(sudo k3s ctr -n k8s.io images import)
  CTR_LIST_CMD=(sudo k3s ctr -n k8s.io images ls)
else
  CTR_IMPORT_CMD=(sudo ctr -n k8s.io images import)
  CTR_LIST_CMD=(sudo ctr -n k8s.io images ls)
fi

"${CTR_IMPORT_CMD[@]}" "${IMAGE_TAR}"
kubectl apply -f "${MANIFEST_PATH}"
kubectl -n port-audit rollout status deployment/k8s-port-audit --timeout=180s

echo "镜像导入完成，Kubernetes 资源已应用。"
echo "已导入镜像列表："
"${CTR_LIST_CMD[@]}" | grep 'k8s-port-audit' || true
echo "如果集群有多个可调度节点，需要在每个节点导入同一个 tar。"
echo "如果 Pod 被调度到尚未导入镜像的节点，Kubernetes 会报 ErrImageNeverPull。"
echo "打开面板：kubectl -n port-audit port-forward svc/k8s-port-audit 8080:8080"
echo "访问地址：http://127.0.0.1:8080"
