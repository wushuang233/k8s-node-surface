#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="${SCRIPT_DIR}/../VERSION"
MANIFEST_PATH="${1:-${MANIFEST_PATH:-${SCRIPT_DIR}/k8s-port-audit.yaml}}"
NAMESPACE="${PORT_AUDIT_NAMESPACE:-port-audit}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-180s}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

require_cmd kubectl
require_cmd mktemp
require_cmd sed

if [[ ! -f "${VERSION_FILE}" ]]; then
  echo "Missing VERSION file: ${VERSION_FILE}" >&2
  exit 1
fi

VERSION="$(head -n 1 "${VERSION_FILE}" | tr -d '[:space:]')"
LOCAL_IMAGE="${LOCAL_IMAGE:-local/k8s-port-audit:${VERSION}}"

if [[ ! -f "${MANIFEST_PATH}" ]]; then
  echo "Manifest not found: ${MANIFEST_PATH}" >&2
  exit 1
fi

TMP_MANIFEST="$(mktemp)"
cleanup() {
  rm -f "${TMP_MANIFEST}"
}
trap cleanup EXIT

sed -E \
  -e "s#^([[:space:]]*image:).*#\\1 ${LOCAL_IMAGE}#" \
  -e "s#^([[:space:]]*imagePullPolicy:).*#\\1 Never#" \
  "${MANIFEST_PATH}" >"${TMP_MANIFEST}"

kubectl apply -f "${TMP_MANIFEST}"
kubectl -n "${NAMESPACE}" rollout status deployment/k8s-port-audit --timeout="${ROLLOUT_TIMEOUT}"

echo "Port-audit deployed with local image ${LOCAL_IMAGE}"
