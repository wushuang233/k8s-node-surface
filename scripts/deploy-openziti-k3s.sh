#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

NAMESPACE="${ZITI_NAMESPACE:-openziti}"
CONTROLLER_RELEASE="${ZITI_CONTROLLER_RELEASE:-ziti-controller}"
ROUTER_RELEASE="${ZITI_ROUTER_RELEASE:-ziti-router}"
ROUTER_NAME="${ZITI_ROUTER_NAME:-ziti-router}"
ROUTER_ROLE="${ZITI_ROUTER_ROLE:-public-router}"
CERT_MANAGER_NAMESPACE="${CERT_MANAGER_NAMESPACE:-cert-manager}"
CONTROLLER_CHART_VERSION="${ZITI_CONTROLLER_CHART_VERSION:-3.1.1}"
ROUTER_CHART_VERSION="${ZITI_ROUTER_CHART_VERSION:-2.1.0}"
CERT_MANAGER_CHART_VERSION="${CERT_MANAGER_CHART_VERSION:-1.20.1}"
TRUST_MANAGER_CHART_VERSION="${TRUST_MANAGER_CHART_VERSION:-0.22.0}"
CONTROLLER_NODEPORT="${ZITI_CONTROLLER_NODEPORT:-31280}"
ROUTER_NODEPORT="${ZITI_ROUTER_NODEPORT:-30222}"
CONTROLLER_DB_SIZE="${ZITI_CONTROLLER_DB_SIZE:-2Gi}"
STORAGE_CLASS_NAME="${ZITI_STORAGE_CLASS_NAME:-local-path}"

if [[ -n "${ZITI_CONTROLLER_DB_PVC:-}" ]]; then
  CONTROLLER_DB_PVC="${ZITI_CONTROLLER_DB_PVC}"
elif [[ "${CONTROLLER_RELEASE}" == "ziti-controller" ]]; then
  CONTROLLER_DB_PVC="ziti-controller-db"
else
  CONTROLLER_DB_PVC="${CONTROLLER_RELEASE}-db"
fi

if [[ -n "${ZITI_ROUTER_ENROLLMENT_SECRET:-}" ]]; then
  ROUTER_ENROLLMENT_SECRET="${ZITI_ROUTER_ENROLLMENT_SECRET}"
elif [[ "${ROUTER_RELEASE}" == "ziti-router" ]]; then
  ROUTER_ENROLLMENT_SECRET="ziti-router-enrollment"
else
  ROUTER_ENROLLMENT_SECRET="${ROUTER_RELEASE}-enrollment"
fi

detect_node_ip() {
  kubectl get nodes -o json \
    | jq -r '
      .items[0].status.addresses
      | map(select(.type == "InternalIP"))[0].address // empty
    '
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

require_cmd helm
require_cmd kubectl
require_cmd jq
require_cmd bash

HOST_IP="${ZITI_HOST_IP:-$(detect_node_ip)}"
if [[ -z "${HOST_IP}" ]]; then
  echo "unable to detect a node InternalIP, please set ZITI_HOST_IP" >&2
  exit 1
fi

controller_login='ziti edge login 127.0.0.1:1280 --yes -u "$ZITI_ADMIN_USER" -p "$ZITI_ADMIN_PASSWORD" --ca "$ZITI_CTRL_PLANE_CA/ctrl-plane-cas.crt" >/dev/null'

current_trust_namespace="$(
  helm get values trust-manager -n "${CERT_MANAGER_NAMESPACE}" -a 2>/dev/null \
    | awk '
        $1 == "namespace:" && seen == 1 { print $2; exit }
        $1 == "trust:" { seen = 1; next }
        seen == 1 && $1 != "" && $1 !~ /^namespace:/ && $1 !~ /^trust:/ { seen = 0 }
      ' \
    || true
)"

if [[ -n "${current_trust_namespace}" && "${current_trust_namespace}" != "null" && "${current_trust_namespace}" != "${NAMESPACE}" ]]; then
  cat >&2 <<EOF
trust-manager is currently configured with app.trust.namespace=${current_trust_namespace}
requested controller namespace is ${NAMESPACE}

The official ziti-controller chart depends on trust-manager reading CA sources from a single "trust namespace".
Safest options:
  1. deploy the controller into ${current_trust_namespace}
  2. or deliberately retarget trust-manager to ${NAMESPACE} before deploying

This script exits here to avoid silently breaking an existing controller trust bundle.
EOF
  exit 1
fi

echo "using host IP: ${HOST_IP}"
echo "controller public address: https://${HOST_IP}:${CONTROLLER_NODEPORT}"
echo "router public address: tls://${HOST_IP}:${ROUTER_NODEPORT}"
echo "controller namespace: ${NAMESPACE}"
echo "controller pvc: ${CONTROLLER_DB_PVC}"
echo "router enrollment secret: ${ROUTER_ENROLLMENT_SECRET}"

echo "[1/9] ensure helm repos"
helm repo add jetstack https://charts.jetstack.io >/dev/null 2>&1 || true
helm repo add openziti https://docs.openziti.io/helm-charts/ >/dev/null 2>&1 || true
helm repo update >/dev/null

echo "[2/9] install cert-manager"
helm upgrade --install cert-manager jetstack/cert-manager \
  -n "${CERT_MANAGER_NAMESPACE}" \
  --create-namespace \
  --version "${CERT_MANAGER_CHART_VERSION}" \
  --set crds.enabled=true

echo "[3/9] create namespace and PVC"
kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1 || kubectl create namespace "${NAMESPACE}"
kubectl label namespace "${NAMESPACE}" openziti.io/namespace=enabled --overwrite
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ${CONTROLLER_DB_PVC}
  namespace: ${NAMESPACE}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: ${CONTROLLER_DB_SIZE}
  storageClassName: ${STORAGE_CLASS_NAME}
EOF

echo "[4/9] install trust-manager"
helm upgrade --install trust-manager jetstack/trust-manager \
  -n "${CERT_MANAGER_NAMESPACE}" \
  --version "${TRUST_MANAGER_CHART_VERSION}" \
  --set app.trust.namespace="${NAMESPACE}"

echo "[5/9] install controller"
helm upgrade --install "${CONTROLLER_RELEASE}" openziti/ziti-controller \
  -n "${NAMESPACE}" \
  --version "${CONTROLLER_CHART_VERSION}" \
  --server-side=false \
  -f "${ROOT_DIR}/manifests/openziti/ziti-controller-values.yaml" \
  --set persistence.existingClaim="${CONTROLLER_DB_PVC}" \
  --set clientApi.advertisedHost="${HOST_IP}" \
  --set clientApi.advertisedPort="${CONTROLLER_NODEPORT}"

kubectl patch certificate -n "${NAMESPACE}" "${CONTROLLER_RELEASE}"-ctrl-plane-identity \
  --type=merge \
  -p "{\"spec\":{\"ipAddresses\":[\"127.0.0.1\",\"::1\",\"${HOST_IP}\"]}}"
kubectl patch certificate -n "${NAMESPACE}" "${CONTROLLER_RELEASE}"-web-identity-cert \
  --type=merge \
  -p "{\"spec\":{\"ipAddresses\":[\"127.0.0.1\",\"::1\",\"${HOST_IP}\"]}}"

kubectl wait certificate.cert-manager.io/"${CONTROLLER_RELEASE}"-ctrl-plane-identity \
  -n "${NAMESPACE}" \
  --for=condition=Ready=true \
  --timeout=180s
kubectl wait certificate.cert-manager.io/"${CONTROLLER_RELEASE}"-web-identity-cert \
  -n "${NAMESPACE}" \
  --for=condition=Ready=true \
  --timeout=180s

kubectl rollout restart deployment/"${CONTROLLER_RELEASE}" -n "${NAMESPACE}"

kubectl rollout status deployment/"${CONTROLLER_RELEASE}" -n "${NAMESPACE}" --timeout=180s

echo "[6/9] reset router release and edge-router entity"
helm uninstall -n "${NAMESPACE}" "${ROUTER_RELEASE}" >/dev/null 2>&1 || true
kubectl delete pvc -n "${NAMESPACE}" "${ROUTER_RELEASE}" --ignore-not-found=true >/dev/null 2>&1 || true

router_id="$(
  kubectl exec -n "${NAMESPACE}" deploy/"${CONTROLLER_RELEASE}" -- sh -lc \
    "${controller_login} && ziti edge list edge-routers -j" \
  | jq -r --arg router_name "${ROUTER_NAME}" '.data[]? | select(.name == $router_name) | .id'
)"

if [[ -n "${router_id}" && "${router_id}" != "null" ]]; then
  kubectl exec -n "${NAMESPACE}" deploy/"${CONTROLLER_RELEASE}" -- sh -lc \
    "${controller_login} && ziti edge delete edge-router \"${router_id}\" >/dev/null"
fi

echo "[7/9] create router enrollment JWT"
router_jwt="$(
  kubectl exec -n "${NAMESPACE}" deploy/"${CONTROLLER_RELEASE}" -- sh -lc \
    "${controller_login} && ziti edge create edge-router \"${ROUTER_NAME}\" --role-attributes \"${ROUTER_ROLE}\" --jwt-output-file /tmp/${ROUTER_NAME}.jwt >/dev/null && cat /tmp/${ROUTER_NAME}.jwt"
)"

kubectl delete secret "${ROUTER_ENROLLMENT_SECRET}" -n "${NAMESPACE}" --ignore-not-found=true
kubectl create secret generic "${ROUTER_ENROLLMENT_SECRET}" \
  -n "${NAMESPACE}" \
  --from-literal=enrollmentJwt="${router_jwt}"

echo "[8/9] install router"
helm upgrade --install "${ROUTER_RELEASE}" openziti/ziti-router \
  -n "${NAMESPACE}" \
  --version "${ROUTER_CHART_VERSION}" \
  --server-side=false \
  -f "${ROOT_DIR}/manifests/openziti/ziti-router-values.yaml" \
  --set enrollmentJwtSecretName="${ROUTER_ENROLLMENT_SECRET}" \
  --set ctrl.endpoint="${HOST_IP}:${CONTROLLER_NODEPORT}" \
  --set edge.advertisedHost="${HOST_IP}" \
  --set edge.advertisedPort="${ROUTER_NODEPORT}" \
  --set csr.sans.ip[1]="${HOST_IP}"

kubectl rollout status deployment/"${ROUTER_RELEASE}" -n "${NAMESPACE}" --timeout=180s

echo "[9/9] verify public addresses"

kubectl get pods,svc,pvc -n "${NAMESPACE}" -o wide
kubectl exec -n "${NAMESPACE}" deploy/"${CONTROLLER_RELEASE}" -- sh -lc \
  "${controller_login} && ziti edge list edge-routers -j" \
  | jq '{routers: [.data[] | {id, name, isOnline, isVerified, syncStatus, hostname, supportedProtocols, roleAttributes}]}'

echo "openziti deployment completed"
