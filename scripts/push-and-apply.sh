#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="${SCRIPT_DIR}/VERSION"
DEFAULT_IMAGE_ARCHIVE="$(find "${SCRIPT_DIR}" -maxdepth 1 -type f -name 'k8s-port-audit-*.tar.gz' | sort | tail -n 1 || true)"
IMAGE_ARCHIVE="${1:-${IMAGE_ARCHIVE:-${DEFAULT_IMAGE_ARCHIVE}}}"
MANIFEST_PATH="${2:-${MANIFEST_PATH:-${SCRIPT_DIR}/k8s-port-audit.yaml}}"
NAMESPACE="${PORT_AUDIT_NAMESPACE:-port-audit}"

if [[ ! -f "${VERSION_FILE}" ]]; then
  echo "Missing VERSION file: ${VERSION_FILE}" >&2
  exit 1
fi

VERSION="$(head -n 1 "${VERSION_FILE}" | tr -d '[:space:]')"
LOCAL_IMAGE="${LOCAL_IMAGE:-local/k8s-port-audit:${VERSION}}"
PORT_AUDIT_IMAGE="${PORT_AUDIT_IMAGE:-}"
IMAGE_PULL_SECRET="${IMAGE_PULL_SECRET:-}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-180s}"
REGISTRY_SERVER="${REGISTRY_SERVER:-}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

require_cmd docker
require_cmd gzip
require_cmd kubectl
require_cmd mktemp
require_cmd sed

if [[ -z "${PORT_AUDIT_IMAGE}" ]]; then
  echo "PORT_AUDIT_IMAGE is required. Example: harbor.example.com/security/k8s-port-audit:${VERSION}" >&2
  exit 1
fi

if [[ -z "${IMAGE_ARCHIVE}" || ! -f "${IMAGE_ARCHIVE}" ]]; then
  echo "Image archive not found: ${IMAGE_ARCHIVE}" >&2
  exit 1
fi

if [[ ! -f "${MANIFEST_PATH}" ]]; then
  echo "Manifest not found: ${MANIFEST_PATH}" >&2
  exit 1
fi

if [[ -z "${REGISTRY_SERVER}" ]]; then
  REGISTRY_SERVER="${PORT_AUDIT_IMAGE%%/*}"
fi

if [[ -n "${REGISTRY_USERNAME:-}" && -n "${REGISTRY_PASSWORD:-}" ]]; then
  printf '%s' "${REGISTRY_PASSWORD}" | docker login "${REGISTRY_SERVER}" --username "${REGISTRY_USERNAME}" --password-stdin
fi

gzip -dc "${IMAGE_ARCHIVE}" | docker load
docker image inspect "${LOCAL_IMAGE}" >/dev/null
docker tag "${LOCAL_IMAGE}" "${PORT_AUDIT_IMAGE}"
docker push "${PORT_AUDIT_IMAGE}"

TMP_MANIFEST="$(mktemp)"
cleanup() {
  rm -f "${TMP_MANIFEST}"
}
trap cleanup EXIT

sed -E "s#^([[:space:]]*image:).*#\\1 ${PORT_AUDIT_IMAGE}#" "${MANIFEST_PATH}" >"${TMP_MANIFEST}"

kubectl apply -f "${TMP_MANIFEST}"

if [[ -n "${IMAGE_PULL_SECRET}" ]]; then
  if [[ -n "${REGISTRY_USERNAME:-}" && -n "${REGISTRY_PASSWORD:-}" ]]; then
    kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
    kubectl -n "${NAMESPACE}" create secret docker-registry "${IMAGE_PULL_SECRET}" \
      --docker-server="${REGISTRY_SERVER}" \
      --docker-username="${REGISTRY_USERNAME}" \
      --docker-password="${REGISTRY_PASSWORD}" \
      --docker-email="${REGISTRY_EMAIL:-devnull@example.com}" \
      --dry-run=client -o yaml | kubectl apply -f -
  fi

  kubectl -n "${NAMESPACE}" patch serviceaccount k8s-port-audit \
    --type=merge \
    -p "{\"imagePullSecrets\":[{\"name\":\"${IMAGE_PULL_SECRET}\"}]}"

  kubectl -n "${NAMESPACE}" rollout restart deployment/k8s-port-audit
fi

kubectl -n "${NAMESPACE}" rollout status deployment/k8s-port-audit --timeout="${ROLLOUT_TIMEOUT}"

echo "Port-audit deployed."
echo "Target image: ${PORT_AUDIT_IMAGE}"
echo "Access: kubectl -n ${NAMESPACE} port-forward svc/k8s-port-audit 8080:8080"
