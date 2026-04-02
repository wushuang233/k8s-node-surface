#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/opt/k8s-node-surface"

export PORT_AUDIT_MANIFEST_PATH="${PORT_AUDIT_MANIFEST_PATH:-${ROOT_DIR}/manifests/k8s-port-audit-stack-local.yaml}"
export PORT_AUDIT_APPLY_MANIFEST="${PORT_AUDIT_APPLY_MANIFEST:-always}"

cd "${ROOT_DIR}"
exec bash "${ROOT_DIR}/scripts/deploy-port-audit-ziti-stack.sh"
