#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VERSION="$(head -n 1 "${ROOT_DIR}/VERSION" | tr -d '[:space:]')"
IMAGE="local/k8s-port-audit:${VERSION}"
BASE_IMAGE="${BASE_IMAGE:-python:3.13-slim}"
BUNDLE_DIR="${ROOT_DIR}/dist/k8s-port-audit-local-${VERSION}"
TAR_PATH="${BUNDLE_DIR}/k8s-port-audit-${VERSION}.tar"
MANIFEST_SOURCE="${ROOT_DIR}/manifests/k8s-port-audit-local.yaml"
MANIFEST_PATH="${BUNDLE_DIR}/k8s-port-audit-local.yaml"
IMPORT_SCRIPT_SOURCE="${ROOT_DIR}/scripts/import-and-apply.sh"
IMPORT_SCRIPT_PATH="${BUNDLE_DIR}/import-and-apply.sh"
QUICKSTART_SOURCE="${ROOT_DIR}/README-DEPLOY.md"
QUICKSTART_PATH="${BUNDLE_DIR}/README.md"
DEPLOY_DOC_PATH="${BUNDLE_DIR}/DEPLOY.md"

if [[ ! -f "${MANIFEST_SOURCE}" ]]; then
  echo "缺少清单文件: ${MANIFEST_SOURCE}" >&2
  exit 1
fi

if ! grep -Fq "image: ${IMAGE}" "${MANIFEST_SOURCE}"; then
  echo "清单里的镜像标签与 VERSION (${VERSION}) 不一致: ${MANIFEST_SOURCE}" >&2
  exit 1
fi

# dist 目录只保留当前版本的 bundle，避免离线交付时误拿旧包。
find "${ROOT_DIR}/dist" -maxdepth 1 -mindepth 1 -type d -name 'k8s-port-audit-local-*' \
  ! -name "k8s-port-audit-local-${VERSION}" -exec find {} -depth -delete \; 2>/dev/null || true

mkdir -p "${BUNDLE_DIR}"

if [[ "${KEEP_DOCKER_PROXY:-0}" != "1" ]]; then
  unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
fi

docker info >/dev/null

if [[ "${SKIP_DOCKER_BUILD:-0}" != "1" ]]; then
  DOCKER_BUILDKIT=1 docker build \
    --build-arg BASE_IMAGE="${BASE_IMAGE}" \
    --build-arg HTTP_PROXY= \
    --build-arg HTTPS_PROXY= \
    -t "${IMAGE}" \
    "${ROOT_DIR}"
else
  docker image inspect "${IMAGE}" >/dev/null
fi

docker save -o "${TAR_PATH}" "${IMAGE}"

cp "${MANIFEST_SOURCE}" "${MANIFEST_PATH}"
cp "${IMPORT_SCRIPT_SOURCE}" "${IMPORT_SCRIPT_PATH}"
cp "${QUICKSTART_SOURCE}" "${QUICKSTART_PATH}"
chmod +x "${IMPORT_SCRIPT_PATH}"
printf '%s\n' "${VERSION}" > "${BUNDLE_DIR}/VERSION"

cat > "${DEPLOY_DOC_PATH}" <<EOF
# 离线部署说明

Bundle 版本：${VERSION}

目录内容：

- k8s-port-audit-${VERSION}.tar
- k8s-port-audit-local.yaml
- import-and-apply.sh
- VERSION

目标机器执行：

\`\`\`bash
sudo ctr -n k8s.io images import ./k8s-port-audit-${VERSION}.tar
kubectl apply -f ./k8s-port-audit-local.yaml
kubectl -n port-audit rollout status deployment/k8s-port-audit --timeout=180s
\`\`\`

或直接执行：

\`\`\`bash
chmod +x ./import-and-apply.sh
./import-and-apply.sh
\`\`\`
EOF

echo "离线 bundle 已生成: ${BUNDLE_DIR}"
echo "清单文件: ${MANIFEST_PATH}"
echo "镜像归档: ${TAR_PATH}"
