#!/usr/bin/env bash
set -euo pipefail

namespace="${1:-openziti}"
controller_service="${ZITI_CONTROLLER_SERVICE:-ziti-controller-client}"
router_deployment="${ZITI_ROUTER_DEPLOYMENT:-ziti-router}"

cluster_ip="$(kubectl get service "${controller_service}" -n "${namespace}" -o jsonpath='{.spec.clusterIP}')"

if [[ -z "${cluster_ip}" ]]; then
  echo "failed to resolve ClusterIP for service ${namespace}/${controller_service}" >&2
  exit 1
fi

kubectl patch deployment "${router_deployment}" -n "${namespace}" --type=strategic -p "$(cat <<EOF
spec:
  template:
    spec:
      hostAliases:
      - ip: ${cluster_ip}
        hostnames:
        - ziti-controller-client
        - ziti-controller-client.${namespace}
        - ziti-controller-client.${namespace}.svc
        - ziti-controller-client.${namespace}.svc.cluster.local
EOF
)"

kubectl rollout status deployment/"${router_deployment}" -n "${namespace}" --timeout=180s

echo "router hostAliases now point controller FQDNs to ${cluster_ip}"
