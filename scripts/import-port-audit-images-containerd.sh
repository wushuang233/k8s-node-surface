#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="${SCRIPT_DIR}/../VERSION"
DEFAULT_IMAGE_ARCHIVE="$(find "${SCRIPT_DIR}" -maxdepth 1 -type f -name 'k8s-port-audit-*.tar.gz' | sort | tail -n 1 || true)"
IMAGE_ARCHIVE="${1:-${IMAGE_ARCHIVE:-${DEFAULT_IMAGE_ARCHIVE}}}"
CONTAINERD_NAMESPACE="${CONTAINERD_NAMESPACE:-k8s.io}"
CTR_BIN="${CTR_BIN:-ctr}"
CONTAINERD_ADDRESS="${CONTAINERD_ADDRESS:-}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

require_cmd gzip
require_cmd mktemp
require_cmd "${CTR_BIN}"

if [[ ! -f "${VERSION_FILE}" ]]; then
  echo "Missing VERSION file: ${VERSION_FILE}" >&2
  exit 1
fi

if [[ -z "${IMAGE_ARCHIVE}" || ! -f "${IMAGE_ARCHIVE}" ]]; then
  echo "Image archive not found: ${IMAGE_ARCHIVE}" >&2
  exit 1
fi

TMP_IMAGE_TAR="$(mktemp)"
cleanup() {
  rm -f "${TMP_IMAGE_TAR}"
}
trap cleanup EXIT

gzip -dc "${IMAGE_ARCHIVE}" >"${TMP_IMAGE_TAR}"

CTR_ARGS=(-n "${CONTAINERD_NAMESPACE}")
if [[ -n "${CONTAINERD_ADDRESS}" ]]; then
  CTR_ARGS=(-a "${CONTAINERD_ADDRESS}" "${CTR_ARGS[@]}")
fi

"${CTR_BIN}" "${CTR_ARGS[@]}" images import --all-platforms "${TMP_IMAGE_TAR}"

echo "Port-audit image imported into containerd namespace ${CONTAINERD_NAMESPACE}."
echo "Run this script on every Kubernetes node that may schedule the port-audit pod."
