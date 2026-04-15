#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VERSION="$(head -n 1 "${ROOT_DIR}/VERSION" | tr -d '[:space:]')"
LOCAL_IMAGE="${LOCAL_IMAGE:-local/k8s-port-audit:${VERSION}}"
BASE_IMAGE="${BASE_IMAGE:-python:3.13-slim}"
BUNDLE_DIR="${ROOT_DIR}/dist/k8s-port-audit-containerd-${VERSION}"
IMAGE_ARCHIVE="${BUNDLE_DIR}/k8s-port-audit-${VERSION}.tar.gz"
ARCHIVE_PATH="${ROOT_DIR}/dist/k8s-port-audit-containerd-${VERSION}.tar.gz"
MANIFEST_SOURCE="${ROOT_DIR}/manifests/k8s-port-audit.yaml"
MANIFEST_PATH="${BUNDLE_DIR}/k8s-port-audit.yaml"
ZITI_SECRET_SOURCE="${ROOT_DIR}/manifests/k8s-port-audit-ziti-admin-secret.example.yaml"
ZITI_SECRET_PATH="${BUNDLE_DIR}/k8s-port-audit-ziti-admin-secret.example.yaml"
IMPORT_CONTAINERD_SOURCE="${ROOT_DIR}/scripts/import-port-audit-images-containerd.sh"
IMPORT_CONTAINERD_PATH="${BUNDLE_DIR}/import-port-audit-images-containerd.sh"
APPLY_CONTAINERD_SOURCE="${ROOT_DIR}/scripts/apply-port-audit-containerd.sh"
APPLY_CONTAINERD_PATH="${BUNDLE_DIR}/apply-port-audit-containerd.sh"
README_PATH="${BUNDLE_DIR}/README.md"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

require_cmd docker
require_cmd gzip
require_cmd sha256sum
require_cmd tar

if [[ ! -f "${MANIFEST_SOURCE}" ]]; then
  echo "Missing manifest: ${MANIFEST_SOURCE}" >&2
  exit 1
fi

find "${ROOT_DIR}/dist" -maxdepth 1 -mindepth 1 -type d -name 'k8s-port-audit-containerd-*' \
  ! -name "k8s-port-audit-containerd-${VERSION}" -exec find {} -depth -delete \; 2>/dev/null || true

rm -rf "${BUNDLE_DIR}"
mkdir -p "${BUNDLE_DIR}"
rm -f "${ARCHIVE_PATH}"

if [[ "${KEEP_DOCKER_PROXY:-0}" != "1" ]]; then
  unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
fi

docker info >/dev/null

if docker image inspect "${LOCAL_IMAGE}" >/dev/null 2>&1 && [[ "${FORCE_DOCKER_BUILD:-0}" != "1" ]]; then
  SKIP_DOCKER_BUILD=1
fi

if [[ "${SKIP_DOCKER_BUILD:-0}" != "1" ]]; then
  DOCKER_BUILDKIT=1 docker build \
    --build-arg BASE_IMAGE="${BASE_IMAGE}" \
    --build-arg HTTP_PROXY= \
    --build-arg HTTPS_PROXY= \
    -t "${LOCAL_IMAGE}" \
    "${ROOT_DIR}"
else
  docker image inspect "${LOCAL_IMAGE}" >/dev/null
fi

docker save "${LOCAL_IMAGE}" | gzip >"${IMAGE_ARCHIVE}"
sha256sum "${IMAGE_ARCHIVE}" >"${IMAGE_ARCHIVE}.sha256"

cp "${MANIFEST_SOURCE}" "${MANIFEST_PATH}"
cp "${ZITI_SECRET_SOURCE}" "${ZITI_SECRET_PATH}"
cp "${IMPORT_CONTAINERD_SOURCE}" "${IMPORT_CONTAINERD_PATH}"
cp "${APPLY_CONTAINERD_SOURCE}" "${APPLY_CONTAINERD_PATH}"
chmod +x "${IMPORT_CONTAINERD_PATH}" "${APPLY_CONTAINERD_PATH}"
printf '%s\n' "${VERSION}" >"${BUNDLE_DIR}/VERSION"

cat >"${README_PATH}" <<EOF
# Port-Audit Containerd 交付包

Bundle 版本：${VERSION}

目录内容：

- k8s-port-audit-${VERSION}.tar.gz
- k8s-port-audit.yaml
- k8s-port-audit-ziti-admin-secret.example.yaml
- import-port-audit-images-containerd.sh
- apply-port-audit-containerd.sh
- VERSION

每个节点先导入镜像：

\`\`\`bash
sudo bash ./import-port-audit-images-containerd.sh
\`\`\`

再在有 kubectl 权限的机器部署：

\`\`\`bash
bash ./apply-port-audit-containerd.sh
\`\`\`

如果需要接 OpenZiti，先创建控制器管理员 Secret：

\`\`\`bash
kubectl create namespace port-audit --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f ./k8s-port-audit-ziti-admin-secret.example.yaml
\`\`\`
EOF

tar -C "${ROOT_DIR}/dist" -czf "${ARCHIVE_PATH}" "$(basename "${BUNDLE_DIR}")"
sha256sum "${ARCHIVE_PATH}" >"${ARCHIVE_PATH}.sha256"

echo "Containerd bundle created: ${ARCHIVE_PATH}"
