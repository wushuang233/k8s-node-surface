#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ZITI_NAMESPACE="${ZITI_NAMESPACE:-openziti}"
CONTROLLER_RELEASE="${ZITI_CONTROLLER_RELEASE:-ziti-controller}"
ROUTER_ROLE="${ZITI_ROUTER_ROLE:-public-router}"
DEFAULT_PORT_AUDIT_MANIFEST_PATH="${ROOT_DIR}/manifests/k8s-port-audit-local.yaml"

PORT_AUDIT_NAMESPACE="${PORT_AUDIT_NAMESPACE:-port-audit}"
PORT_AUDIT_MANIFEST_PATH="${PORT_AUDIT_MANIFEST_PATH:-${DEFAULT_PORT_AUDIT_MANIFEST_PATH}}"
PORT_AUDIT_APPLY_MANIFEST="${PORT_AUDIT_APPLY_MANIFEST:-auto}"
PORT_AUDIT_SERVICE_NAME="${PORT_AUDIT_SERVICE_NAME:-k8s-port-audit}"
PORT_AUDIT_SERVICE_PORT="${PORT_AUDIT_SERVICE_PORT:-8080}"
PORT_AUDIT_SERVICE_FQDN="${PORT_AUDIT_SERVICE_NAME}.${PORT_AUDIT_NAMESPACE}.svc.cluster.local"
PORT_AUDIT_ZITI_SERVICE_NAME="${PORT_AUDIT_ZITI_SERVICE_NAME:-port-audit-web}"
PORT_AUDIT_INTERCEPT_NAME="${PORT_AUDIT_INTERCEPT_NAME:-port-audit-intercept-config}"
PORT_AUDIT_HOST_CONFIG_NAME="${PORT_AUDIT_HOST_CONFIG_NAME:-port-audit-host-config}"
PORT_AUDIT_BIND_POLICY_NAME="${PORT_AUDIT_BIND_POLICY_NAME:-port-audit-bind-policy}"
PORT_AUDIT_DIAL_POLICY_NAME="${PORT_AUDIT_DIAL_POLICY_NAME:-port-audit-dial-policy}"
PORT_AUDIT_ROUTER_POLICY_NAME="${PORT_AUDIT_ROUTER_POLICY_NAME:-port-audit-router-access}"
PORT_AUDIT_SERP_NAME="${PORT_AUDIT_SERP_NAME:-port-audit-service-router-access}"
PORT_AUDIT_HOST_IDENTITY_NAME="${PORT_AUDIT_HOST_IDENTITY_NAME:-port-audit-host}"
PORT_AUDIT_HOST_ROLE="${PORT_AUDIT_HOST_ROLE:-port-audit-hosts}"
PORT_AUDIT_CLIENT_IDENTITY_NAME="${PORT_AUDIT_CLIENT_IDENTITY_NAME:-port-audit-client}"
PORT_AUDIT_CLIENT_ROLE="${PORT_AUDIT_CLIENT_ROLE:-port-audit-clients}"
PORT_AUDIT_HOST_DEPLOYMENT_NAME="${PORT_AUDIT_HOST_DEPLOYMENT_NAME:-port-audit-ziti-host}"
PORT_AUDIT_HOST_SECRET_NAME="${PORT_AUDIT_HOST_SECRET_NAME:-port-audit-ziti-host-identity}"
PORT_AUDIT_CLIENT_JWT_OUTPUT_PATH="${PORT_AUDIT_CLIENT_JWT_OUTPUT_PATH:-}"
PORT_AUDIT_INTERCEPT_ADDRESS="${PORT_AUDIT_INTERCEPT_ADDRESS:-port-audit.ziti}"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

require_cmd kubectl
require_cmd jq
require_cmd bash
require_cmd sha256sum

controller_exec() {
  local script="$1"
  kubectl exec -n "${ZITI_NAMESPACE}" deploy/"${CONTROLLER_RELEASE}" -- sh -lc "${script}"
}

controller_wait_for() {
  local description="$1"
  local condition_script="$2"
  local timeout_seconds="${3:-180}"
  local start_ts now_ts
  start_ts="$(date +%s)"

  while true; do
    if controller_exec "${controller_login} && ${condition_script}" >/dev/null 2>&1; then
      echo "${description}: ready"
      return 0
    fi

    now_ts="$(date +%s)"
    if (( now_ts - start_ts >= timeout_seconds )); then
      echo "timed out waiting for ${description}" >&2
      return 1
    fi

    sleep 3
  done
}

controller_login='ziti edge login 127.0.0.1:1280 --yes -u "$ZITI_ADMIN_USER" -p "$ZITI_ADMIN_PASSWORD" --ca "$ZITI_CTRL_PLANE_CA/ctrl-plane-cas.crt" >/dev/null'

echo "[1/7] deploy core OpenZiti"
bash "${ROOT_DIR}/scripts/deploy-openziti-k3s.sh"

port_audit_deployment_exists=false
if kubectl get deployment k8s-port-audit -n "${PORT_AUDIT_NAMESPACE}" >/dev/null 2>&1; then
  port_audit_deployment_exists=true
fi

if [[ "${PORT_AUDIT_APPLY_MANIFEST}" == "never" ]]; then
  echo "[2/7] skip port-audit manifest apply (PORT_AUDIT_APPLY_MANIFEST=never)"
elif [[ "${PORT_AUDIT_APPLY_MANIFEST}" == "auto" && "${port_audit_deployment_exists}" == "true" ]]; then
  echo "[2/7] reuse existing port-audit deployment (set PORT_AUDIT_APPLY_MANIFEST=always to force apply)"
elif [[ -n "${PORT_AUDIT_MANIFEST_PATH}" && -f "${PORT_AUDIT_MANIFEST_PATH}" ]]; then
  echo "[2/7] apply port-audit manifest: ${PORT_AUDIT_MANIFEST_PATH}"
  kubectl apply -f "${PORT_AUDIT_MANIFEST_PATH}"
else
  echo "[2/7] skip port-audit manifest apply (manifest not found: ${PORT_AUDIT_MANIFEST_PATH})"
fi

echo "[3/7] wait for port-audit service"
kubectl wait --for=condition=Available=true deployment/k8s-port-audit \
  -n "${PORT_AUDIT_NAMESPACE}" \
  --timeout=180s >/dev/null 2>&1 || true
kubectl wait --for=jsonpath='{.spec.clusterIP}' "service/${PORT_AUDIT_SERVICE_NAME}" \
  -n "${PORT_AUDIT_NAMESPACE}" \
  --timeout=180s >/dev/null

echo "port-audit backend: ${PORT_AUDIT_SERVICE_FQDN}:${PORT_AUDIT_SERVICE_PORT}"

echo "[4/7] recreate Ziti resources for port-audit"
controller_exec "${controller_login} && \
  for cmd in \
    'ziti edge delete service-edge-router-policy \"${PORT_AUDIT_SERP_NAME}\"' \
    'ziti edge delete edge-router-policy \"${PORT_AUDIT_ROUTER_POLICY_NAME}\"' \
    'ziti edge delete service-policy \"${PORT_AUDIT_BIND_POLICY_NAME}\"' \
    'ziti edge delete service-policy \"${PORT_AUDIT_DIAL_POLICY_NAME}\"' \
    'ziti edge delete service \"${PORT_AUDIT_ZITI_SERVICE_NAME}\"' \
    'ziti edge delete config \"${PORT_AUDIT_HOST_CONFIG_NAME}\"' \
    'ziti edge delete config \"${PORT_AUDIT_INTERCEPT_NAME}\"' \
    'ziti edge delete identity \"${PORT_AUDIT_HOST_IDENTITY_NAME}\"' \
    'ziti edge delete identity \"${PORT_AUDIT_CLIENT_IDENTITY_NAME}\"'
  do
    sh -lc \"\$cmd\" >/dev/null 2>&1 || true
  done"

controller_exec "${controller_login} && \
  ziti edge create identity \"${PORT_AUDIT_HOST_IDENTITY_NAME}\" -a \"${PORT_AUDIT_HOST_ROLE}\" -j >/tmp/port-audit-host.identity.json && \
  HOST_ID=\$(jq -r '.data.id' /tmp/port-audit-host.identity.json) && \
  ziti edge list enrollments -j | jq --arg id \"\${HOST_ID}\" '.data[] | select(.identityId == \$id)' >/tmp/port-audit-host.enrollment.json && \
  jq -r '.jwt' /tmp/port-audit-host.enrollment.json >/tmp/port-audit-host.jwt && \
  ziti edge enroll /tmp/port-audit-host.jwt --out /tmp/port-audit-host.json --ca \"\$ZITI_CTRL_PLANE_CA/ctrl-plane-cas.crt\" >/tmp/port-audit-host.enroll.log 2>&1 && \
  cat /tmp/port-audit-host.json" > "${tmp_dir}/port-audit-host.json"

controller_exec "${controller_login} && \
  ziti edge create identity \"${PORT_AUDIT_CLIENT_IDENTITY_NAME}\" -a \"${PORT_AUDIT_CLIENT_ROLE}\" -j >/tmp/port-audit-client.identity.json && \
  CLIENT_ID=\$(jq -r '.data.id' /tmp/port-audit-client.identity.json) && \
  ziti edge list enrollments -j | jq --arg id \"\${CLIENT_ID}\" '.data[] | select(.identityId == \$id)' >/tmp/port-audit-client.enrollment.json && \
  cat /tmp/port-audit-client.enrollment.json" > "${tmp_dir}/port-audit-client-enrollment.json"

if [[ -n "${PORT_AUDIT_CLIENT_JWT_OUTPUT_PATH}" ]]; then
  mkdir -p "$(dirname "${PORT_AUDIT_CLIENT_JWT_OUTPUT_PATH}")"
  jq -r '.jwt' "${tmp_dir}/port-audit-client-enrollment.json" > "${PORT_AUDIT_CLIENT_JWT_OUTPUT_PATH}"
  chmod 600 "${PORT_AUDIT_CLIENT_JWT_OUTPUT_PATH}"
fi

port_audit_host_identity_hash="$(
  sha256sum "${tmp_dir}/port-audit-host.json" | awk '{print $1}'
)"

controller_exec "${controller_login} && \
  printf '%s' '{\"addresses\":[\"${PORT_AUDIT_INTERCEPT_ADDRESS}\"],\"portRanges\":[{\"low\":80,\"high\":80}],\"protocols\":[\"tcp\"]}' >/tmp/${PORT_AUDIT_INTERCEPT_NAME}.json && \
  printf '%s' '{\"address\":\"${PORT_AUDIT_SERVICE_FQDN}\",\"port\":${PORT_AUDIT_SERVICE_PORT},\"protocol\":\"tcp\"}' >/tmp/${PORT_AUDIT_HOST_CONFIG_NAME}.json && \
  ziti edge create config \"${PORT_AUDIT_INTERCEPT_NAME}\" intercept.v1 --json-file /tmp/${PORT_AUDIT_INTERCEPT_NAME}.json >/dev/null && \
  ziti edge create config \"${PORT_AUDIT_HOST_CONFIG_NAME}\" host.v1 --json-file /tmp/${PORT_AUDIT_HOST_CONFIG_NAME}.json >/dev/null && \
  ziti edge create service \"${PORT_AUDIT_ZITI_SERVICE_NAME}\" -c \"${PORT_AUDIT_INTERCEPT_NAME},${PORT_AUDIT_HOST_CONFIG_NAME}\" >/dev/null && \
  ziti edge create service-policy \"${PORT_AUDIT_DIAL_POLICY_NAME}\" Dial --identity-roles \"#${PORT_AUDIT_CLIENT_ROLE}\" --service-roles \"@${PORT_AUDIT_ZITI_SERVICE_NAME}\" >/dev/null && \
  ziti edge create service-policy \"${PORT_AUDIT_BIND_POLICY_NAME}\" Bind --identity-roles \"#${PORT_AUDIT_HOST_ROLE}\" --service-roles \"@${PORT_AUDIT_ZITI_SERVICE_NAME}\" >/dev/null && \
  ziti edge create edge-router-policy \"${PORT_AUDIT_ROUTER_POLICY_NAME}\" --identity-roles \"#${PORT_AUDIT_CLIENT_ROLE},#${PORT_AUDIT_HOST_ROLE}\" --edge-router-roles \"#${ROUTER_ROLE}\" >/dev/null && \
  ziti edge create service-edge-router-policy \"${PORT_AUDIT_SERP_NAME}\" --service-roles \"@${PORT_AUDIT_ZITI_SERVICE_NAME}\" --edge-router-roles \"#${ROUTER_ROLE}\" >/dev/null"

echo "[5/7] apply host identity secret and host deployment"
kubectl create secret generic "${PORT_AUDIT_HOST_SECRET_NAME}" \
  -n "${PORT_AUDIT_NAMESPACE}" \
  --from-file=port-audit-host.json="${tmp_dir}/port-audit-host.json" \
  -o yaml --dry-run=client | kubectl apply -f -

cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${PORT_AUDIT_HOST_DEPLOYMENT_NAME}
  namespace: ${PORT_AUDIT_NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ${PORT_AUDIT_HOST_DEPLOYMENT_NAME}
  template:
    metadata:
      labels:
        app: ${PORT_AUDIT_HOST_DEPLOYMENT_NAME}
      annotations:
        openziti.io/identity-hash: ${port_audit_host_identity_hash}
    spec:
      containers:
        - name: ziti-host
          image: openziti/ziti-edge-tunnel:latest
          imagePullPolicy: IfNotPresent
          command:
            - ziti-edge-tunnel
          args:
            - run-host
            - -i
            - /ziti-edge-tunnel/port-audit-host.json
            - -v
            - "6"
            - -r
            - "3"
          volumeMounts:
            - name: identity-work
              mountPath: /ziti-edge-tunnel
      initContainers:
        - name: init-identity
          image: busybox:1.36
          command:
            - sh
            - -c
            - cp /identity-src/port-audit-host.json /ziti-edge-tunnel/port-audit-host.json && chmod 600 /ziti-edge-tunnel/port-audit-host.json
          volumeMounts:
            - name: identity-src
              mountPath: /identity-src
              readOnly: true
            - name: identity-work
              mountPath: /ziti-edge-tunnel
      volumes:
        - name: identity-src
          secret:
            secretName: ${PORT_AUDIT_HOST_SECRET_NAME}
        - name: identity-work
          emptyDir: {}
EOF

kubectl rollout status deployment/"${PORT_AUDIT_HOST_DEPLOYMENT_NAME}" -n "${PORT_AUDIT_NAMESPACE}" --timeout=180s

echo "[6/7] verify Ziti identities and terminator"
controller_wait_for \
  "port-audit host identity online" \
  "ziti edge list identities -j | jq -e '.data[] | select(.name == \"${PORT_AUDIT_HOST_IDENTITY_NAME}\" and .edgeRouterConnectionStatus == \"online\" and .hasEdgeRouterConnection == true) | .id' >/dev/null"
controller_wait_for \
  "port-audit service terminator" \
  "ziti edge list terminators -j | jq -e '.data[] | select(.service.name == \"${PORT_AUDIT_ZITI_SERVICE_NAME}\") | .id' >/dev/null"
controller_exec "${controller_login} && \
  echo --- identities --- && \
  ziti edge list identities -j | jq '.data[] | select(.name==\"${PORT_AUDIT_HOST_IDENTITY_NAME}\" or .name==\"${PORT_AUDIT_CLIENT_IDENTITY_NAME}\") | {name,edgeRouterConnectionStatus,hasEdgeRouterConnection,roleAttributes}' && \
  echo --- terminators --- && \
  ziti edge list terminators -j | jq '.data[] | select(.service.name==\"${PORT_AUDIT_ZITI_SERVICE_NAME}\") | {id,service: .service.name,router: .router.name,binding,address}'"

echo "[7/7] summary"
echo "ziti service: ${PORT_AUDIT_ZITI_SERVICE_NAME}"
echo "intercept config: ${PORT_AUDIT_INTERCEPT_NAME}"
echo "host config: ${PORT_AUDIT_HOST_CONFIG_NAME}"
echo "host identity: ${PORT_AUDIT_HOST_IDENTITY_NAME}"
echo "client identity: ${PORT_AUDIT_CLIENT_IDENTITY_NAME}"
if [[ -n "${PORT_AUDIT_CLIENT_JWT_OUTPUT_PATH}" ]]; then
  echo "client JWT written to: ${PORT_AUDIT_CLIENT_JWT_OUTPUT_PATH}"
else
  echo "client JWT not exported. Set PORT_AUDIT_CLIENT_JWT_OUTPUT_PATH to save it on the next run."
fi
