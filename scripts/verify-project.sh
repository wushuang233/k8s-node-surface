#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VERSION="$(head -n 1 "${ROOT_DIR}/VERSION" | tr -d '[:space:]')"
LOCAL_MANIFEST="${ROOT_DIR}/manifests/k8s-port-audit-local.yaml"
REGISTRY_MANIFEST="${ROOT_DIR}/manifests/k8s-port-audit.yaml"

ROOT_DIR="${ROOT_DIR}" python3 - <<'PY'
import ast
import os
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
for path in sorted(root.rglob("*.py")):
    if "__pycache__" in path.parts:
        continue
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path))
PY
bash -n "${ROOT_DIR}/scripts/import-and-apply.sh"
bash -n "${ROOT_DIR}/scripts/build-local-bundle.sh"

if ! grep -Fq "image: local/k8s-port-audit:${VERSION}" "${LOCAL_MANIFEST}"; then
  echo "Local manifest image tag does not match VERSION (${VERSION})" >&2
  exit 1
fi

kubectl apply --dry-run=client -f "${LOCAL_MANIFEST}" >/dev/null
kubectl apply --dry-run=client -f "${REGISTRY_MANIFEST}" >/dev/null

echo "Project verification passed."
