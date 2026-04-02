#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VERSION="$(head -n 1 "${ROOT_DIR}/VERSION" | tr -d '[:space:]')"
IMAGE="local/k8s-port-audit-stack:${VERSION}"
BASE_IMAGE="${BASE_IMAGE:-python:3.13-slim}"
BUNDLE_DIR="${ROOT_DIR}/dist/k8s-port-audit-stack-local-${VERSION}"
TAR_PATH="${BUNDLE_DIR}/k8s-port-audit-stack-${VERSION}.tar"
SHA256_PATH="${BUNDLE_DIR}/SHA256SUMS"
INSTALLER_MANIFEST_SOURCE="${ROOT_DIR}/manifests/openziti-stack-installer-local.yaml"
APP_MANIFEST_SOURCE="${ROOT_DIR}/manifests/k8s-port-audit-stack-local.yaml"
INSTALLER_MANIFEST_PATH="${BUNDLE_DIR}/openziti-stack-installer-local.yaml"
APP_MANIFEST_PATH="${BUNDLE_DIR}/k8s-port-audit-stack-local.yaml"
README_PATH="${BUNDLE_DIR}/README.md"

REQUIRED_PATHS=(
  Dockerfile.stack
  Dockerfile.stack.refresh
  requirements.txt
  VERSION
  main.py
  README-BUILD.md
  README-DEPLOY.md
  README-OPENZITI-K3S.md
  config
  k8s_port_audit
  manifests
  scripts
  web
  ziti
)

compute_source_sha() {
  (
    cd "${ROOT_DIR}"
    tar -cf - "${REQUIRED_PATHS[@]}"
  ) | sha256sum | awk '{print $1}'
}

stage_build_context() {
  local context_dir="$1"
  mkdir -p "${context_dir}"
  (
    cd "${ROOT_DIR}"
    tar -cf - "${REQUIRED_PATHS[@]}"
  ) | tar -xf - -C "${context_dir}"
}

current_image_source_sha() {
  docker image inspect "${IMAGE}" \
    --format '{{ index .Config.Labels "io.k8s-node-surface.stack-source-sha" }}' \
    2>/dev/null || true
}

local_base_image_alias() {
  printf 'local/k8s-port-audit-stack-base:%s\n' \
    "$(printf '%s' "${BASE_IMAGE}" | tr '/:@' '---' | tr -cd '[:alnum:]._-')"
}

refresh_base_image_alias() {
  printf 'local/k8s-port-audit-stack-buildcache:%s\n' "${VERSION}"
}

for required_file in "${INSTALLER_MANIFEST_SOURCE}" "${APP_MANIFEST_SOURCE}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "缺少清单文件: ${required_file}" >&2
    exit 1
  fi
done

if ! grep -Fq "image: ${IMAGE}" "${INSTALLER_MANIFEST_SOURCE}"; then
  echo "installer 清单里的镜像标签与 VERSION (${VERSION}) 不一致: ${INSTALLER_MANIFEST_SOURCE}" >&2
  exit 1
fi

if ! grep -Fq "image: ${IMAGE}" "${APP_MANIFEST_SOURCE}"; then
  echo "app 清单里的镜像标签与 VERSION (${VERSION}) 不一致: ${APP_MANIFEST_SOURCE}" >&2
  exit 1
fi

mkdir -p "${BUNDLE_DIR}"

if [[ "${KEEP_DOCKER_PROXY:-0}" != "1" ]]; then
  unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
fi

docker info >/dev/null

SOURCE_SHA="$(compute_source_sha)"
CURRENT_IMAGE_SOURCE_SHA="$(current_image_source_sha)"
BUILD_BASE_IMAGE="${BASE_IMAGE}"
BUILD_DOCKERFILE="Dockerfile.stack"

if docker image inspect "${BASE_IMAGE}" >/dev/null 2>&1; then
  BUILD_BASE_IMAGE="$(local_base_image_alias)"
  docker tag "${BASE_IMAGE}" "${BUILD_BASE_IMAGE}" >/dev/null
fi

if [[ "${SKIP_DOCKER_BUILD:-0}" == "1" ]]; then
  docker image inspect "${IMAGE}" >/dev/null
elif [[ "${FORCE_DOCKER_BUILD:-0}" != "1" && -n "${CURRENT_IMAGE_SOURCE_SHA}" && "${CURRENT_IMAGE_SOURCE_SHA}" == "${SOURCE_SHA}" ]]; then
  echo "复用已有镜像 ${IMAGE}，源码摘要未变化: ${SOURCE_SHA}"
else
  context_dir="$(mktemp -d)"
  trap 'rm -rf "${context_dir}"' EXIT
  stage_build_context "${context_dir}"
  if docker image inspect "${IMAGE}" >/dev/null 2>&1; then
    BUILD_BASE_IMAGE="$(refresh_base_image_alias)"
    docker tag "${IMAGE}" "${BUILD_BASE_IMAGE}" >/dev/null
    BUILD_DOCKERFILE="Dockerfile.stack.refresh"
  fi
  DOCKER_BUILDKIT=1 docker build \
    --pull=false \
    -f "${context_dir}/${BUILD_DOCKERFILE}" \
    --build-arg BASE_IMAGE="${BUILD_BASE_IMAGE}" \
    --build-arg STACK_SOURCE_SHA="${SOURCE_SHA}" \
    --build-arg HTTP_PROXY= \
    --build-arg HTTPS_PROXY= \
    --build-arg ALL_PROXY= \
    --build-arg http_proxy= \
    --build-arg https_proxy= \
    --build-arg all_proxy= \
    -t "${IMAGE}" \
    "${context_dir}"
fi

docker save -o "${TAR_PATH}" "${IMAGE}"
cp "${INSTALLER_MANIFEST_SOURCE}" "${INSTALLER_MANIFEST_PATH}"
cp "${APP_MANIFEST_SOURCE}" "${APP_MANIFEST_PATH}"
printf '%s\n' "${VERSION}" > "${BUNDLE_DIR}/VERSION"
(
  cd "${BUNDLE_DIR}"
  sha256sum \
    "k8s-port-audit-stack-${VERSION}.tar" \
    "openziti-stack-installer-local.yaml" \
    "k8s-port-audit-stack-local.yaml" \
    "VERSION" \
    > "${SHA256_PATH}"
)

cat > "${README_PATH}" <<EOF
# OpenZiti + Port-Audit 单镜像离线包

版本：${VERSION}

镜像：

\`\`\`text
${IMAGE}
\`\`\`

目录内容：

- k8s-port-audit-stack-${VERSION}.tar
- openziti-stack-installer-local.yaml
- k8s-port-audit-stack-local.yaml
- SHA256SUMS
- VERSION

使用方式：

1. 导入镜像到 k3s/containerd

\`\`\`bash
sudo k3s ctr -n k8s.io images import ./k8s-port-audit-stack-${VERSION}.tar
\`\`\`

2. 一次性安装整套

\`\`\`bash
kubectl apply -f ./openziti-stack-installer-local.yaml
kubectl logs -n openziti-installer job/openziti-stack-installer -f
\`\`\`

这条路径面向单节点 k3s。
用户侧不需要运行仓库脚本，只需要“导入镜像 + apply 一个 installer 清单”。

完成后访问：

\`\`\`bash
kubectl -n port-audit port-forward svc/k8s-port-audit 8080:8080
\`\`\`

\`\`\`text
http://127.0.0.1:8080
http://127.0.0.1:8080/ziti/
\`\`\`
EOF

echo "stack bundle 已生成: ${BUNDLE_DIR}"
echo "镜像归档: ${TAR_PATH}"
echo "installer 清单: ${INSTALLER_MANIFEST_PATH}"
