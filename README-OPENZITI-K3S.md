# OpenZiti Controller + Router on k3s

这是一份按“少变量、少惊喜、能重复复现”整理的 OpenZiti k3s 部署手册。

目标只有一套：

- 一个持久化 `ziti-controller`
- 一个对外广播 `NodePort + 宿主机 IP` 的 `ziti-router`
- 证书和 CA 分发交给 `cert-manager + trust-manager`

这份手册不是只按文档拼出来的。我在这台机器上于 `2026-04-02` 做过一次完整 proof 验证：

- 在同一个 trust namespace `openziti` 里额外部署了临时 release
  - `ziti-controller-proof`
  - `ziti-router-proof`
- proof controller 对外地址：`https://192.168.198.128:32280`
- proof router 对外地址：`tls://192.168.198.128:32223`
- 验证结果
  - `curl --noproxy '*' -sk https://192.168.198.128:32280/edge/client/v1/version` 返回的 API URL 正确指向 `192.168.198.128:32280`
  - controller 侧看到 proof router 为 `isOnline=true`、`isVerified=true`、`syncStatus=SYNC_DONE`
- 验证完成后已清理 proof release，只保留正式的 `ziti-controller / ziti-router`

## 先说结论

如果你想在这台 k3s 上稳定复现，不要一上来就追求“任意 namespace 都能装”。

最稳的做法是：

1. 固定使用 namespace `openziti`
2. `trust-manager` 的 `app.trust.namespace` 也固定为 `openziti`
3. controller 和 router 都用 `NodePort + 宿主机 InternalIP`
4. controller 广播裸 IP 时，手工给两张 `Certificate` 补 `ipAddresses`
5. router 用角色属性，例如 `#public-router`，不要把策略绑死到 router ID

## 为什么推荐固定 `openziti`

这是官方 chart 的现实约束，不是我额外加出来的复杂度。

`ziti-controller` chart 依赖：

- `cert-manager`
- `trust-manager`
- `Issuer`
- `Certificate`
- `Bundle`

而 `trust-manager` 有一个关键限制：整个集群只有一个“trust namespace”，Bundle 的信任源要从这个 namespace 读取。

官方 `ziti-controller` chart README 明确写了这一点：

- 一个集群里通常只适合放一个 controller
- 如果要多个 controller，要么共享同一个 namespace，要么你必须明确调整 trust-manager 的 trust namespace

所以对这台 k3s，最安全的规则就是：

- 正式部署统一放在 `openziti`
- 想做临时 proof，也放在 `openziti`，但换 release 名和 NodePort

不要把正式 controller 装在 `openziti`，又把 proof controller 装在另一个 namespace，然后希望 trust-manager 自动处理所有 CA 源。那样最容易踩坑。

## 当前经过验证的版本

- `cert-manager` chart: `1.20.1`
- `trust-manager` chart: `0.22.0`
- `ziti-controller` chart: `3.1.1`
- `ziti-router` chart: `2.1.0`
- OpenZiti app: `1.7.2`

本机当前正式对外地址：

- controller: `https://192.168.198.128:31280`
- router: `tls://192.168.198.128:30222`

## 官方资料

- ziti-controller chart README  
  https://github.com/openziti/helm-charts/tree/main/charts/ziti-controller
- ziti-router chart README  
  https://github.com/openziti/helm-charts/tree/main/charts/ziti-router
- trust-manager 安装文档  
  https://cert-manager.io/docs/trust/trust-manager/installation/

## 仓库里真正要看的文件

- 脚本：[scripts/deploy-openziti-k3s.sh](/home/wushuang/test-py/k8s-node-surface/scripts/deploy-openziti-k3s.sh)
- 整套脚本：[scripts/deploy-port-audit-ziti-stack.sh](/home/wushuang/test-py/k8s-node-surface/scripts/deploy-port-audit-ziti-stack.sh)
- controller values：[manifests/openziti/ziti-controller-values.yaml](/home/wushuang/test-py/k8s-node-surface/manifests/openziti/ziti-controller-values.yaml)
- router values：[manifests/openziti/ziti-router-values.yaml](/home/wushuang/test-py/k8s-node-surface/manifests/openziti/ziti-router-values.yaml)

注意：

- `namespace.yaml` 和 `ziti-controller-db-pvc.yaml` 现在只是示例文件
- 真正推荐的复现入口是脚本
- 脚本已经支持通过环境变量改 release、PVC、NodePort

## 这套方案为什么比“随便装个 chart”稳

因为这里把最容易出错的 4 个点都显式处理了：

1. `trust-manager` 只认一个 trust namespace  
   所以文档固定用 `openziti`

2. controller 广播的是裸 IP，而不是 DNS  
   所以必须给证书补 `ipAddresses`

3. router 要面对集群外客户端  
   所以必须广播宿主机 IP + NodePort，而不是 `*.svc.cluster.local`

4. router 经常因为旧 enrollment / 旧证书 / 旧 ID 残留导致离线  
   所以脚本默认会重建 router release、PVC 和 edge-router 实体

## 一次性部署

最简单的方式：

```bash
ZITI_HOST_IP=192.168.198.128 bash scripts/deploy-openziti-k3s.sh
```

如果不传 `ZITI_HOST_IP`，脚本会自动读取当前节点的第一个 `InternalIP`。

默认值等价于：

```bash
ZITI_NAMESPACE=openziti
ZITI_CONTROLLER_RELEASE=ziti-controller
ZITI_ROUTER_RELEASE=ziti-router
ZITI_ROUTER_NAME=ziti-router
ZITI_ROUTER_ROLE=public-router
ZITI_CONTROLLER_NODEPORT=31280
ZITI_ROUTER_NODEPORT=30222
ZITI_CONTROLLER_DB_PVC=ziti-controller-db
ZITI_STORAGE_CLASS_NAME=local-path
```

## 整套重建

如果你不只是想装 `controller + router`，而是想把这套仓库里的 `port-audit` 业务也一起恢复出来，直接用：

```bash
PORT_AUDIT_CLIENT_JWT_OUTPUT_PATH=/tmp/port-audit-client.jwt \
ZITI_HOST_IP=192.168.198.128 \
bash scripts/deploy-port-audit-ziti-stack.sh
```

这条脚本会顺序完成：

1. 调用 `scripts/deploy-openziti-k3s.sh` 重建核心 OpenZiti
2. 当集群里还没有 `k8s-port-audit` Deployment 时，默认应用 [manifests/k8s-port-audit-local.yaml](/home/wushuang/test-py/k8s-node-surface/manifests/k8s-port-audit-local.yaml)
3. 重建 `port-audit` 这组 Ziti 资源
   - service: `port-audit-web`
   - configs: `port-audit-intercept-config`, `port-audit-host-config`
   - policies: `port-audit-dial-policy`, `port-audit-bind-policy`, `port-audit-router-access`, `port-audit-service-router-access`
   - identities: `port-audit-host`, `port-audit-client`
4. 自动生成 `port-audit-host` 的 enrolled JSON，并更新 `port-audit-ziti-host` Deployment
5. 等待 host identity 在线，并等待 `port-audit-web` 的 terminator 出现

这里有一个我已经替你踩过并修掉的坑：

- 只更新 `Secret` 不会自动让 Pod 换成新的 identity JSON
- 所以脚本会把 `port-audit-host.json` 的 sha256 写进 Pod 模板注解 `openziti.io/identity-hash`
- 每次 host identity 重签后，`port-audit-ziti-host` 都会被强制滚动更新

另外还有一层“现网保护”逻辑：

- 默认 `PORT_AUDIT_APPLY_MANIFEST=auto`
- 如果集群里已经存在 `k8s-port-audit` Deployment，脚本会复用现有工作负载，不再强行套仓库里的默认镜像标签
- 如果你就是想强制覆盖当前业务 Deployment，再显式传 `PORT_AUDIT_APPLY_MANIFEST=always`

脚本默认现在走的是“纯 k8s Service DNS”：

- `host.v1.address = k8s-port-audit.port-audit.svc.cluster.local`
- 不再额外给 `port-audit-ziti-host` 注入 `hostAliases`

这点我在当前集群重新验证过：

- `port-audit-ziti-host` Pod 内可以直接解析 `k8s-port-audit.port-audit.svc.cluster.local`
- host 绑定成功后，controller 能看到 `port-audit-web` terminator

如果你不想自动应用业务清单，可以显式跳过：

```bash
PORT_AUDIT_APPLY_MANIFEST=never \
PORT_AUDIT_MANIFEST_PATH=/nonexistent \
ZITI_HOST_IP=192.168.198.128 \
bash scripts/deploy-port-audit-ziti-stack.sh
```

如果你有自己的业务清单，也可以替换成自己的 manifest：

```bash
PORT_AUDIT_APPLY_MANIFEST=always \
PORT_AUDIT_MANIFEST_PATH=/abs/path/to/your-port-audit.yaml \
ZITI_HOST_IP=192.168.198.128 \
bash scripts/deploy-port-audit-ziti-stack.sh
```

如果你用的是仓库里的 `manifests/k8s-port-audit-local.yaml`，还要确保对应镜像已经导入 k3s 的 containerd。

这一步不属于 OpenZiti 本身，但属于“整套业务复现”的前置条件。可参考：

- [README-BUILD.md](/home/wushuang/test-py/k8s-node-surface/README-BUILD.md)
- [README-DEPLOY.md](/home/wushuang/test-py/k8s-node-surface/README-DEPLOY.md)

如果你希望 `port-audit` 里的 `/ziti/` 页面默认带上 controller 登录信息，还可以额外创建这个可选 Secret：

- [manifests/k8s-port-audit-ziti-admin-secret.example.yaml](/home/wushuang/test-py/k8s-node-surface/manifests/k8s-port-audit-ziti-admin-secret.example.yaml)

里面支持：

- `ZITI_DEFAULT_CONTROLLER_URL`
- `ZITI_DEFAULT_USERNAME`
- `ZITI_DEFAULT_PASSWORD`

应用后：

- 登录页会默认带上 controller URL
- 用户名可以默认带出
- 如果密码输入框留空，后端会自动回退到 Pod 内预设密码

## 脚本会做什么

脚本按下面顺序执行：

1. 安装或升级 `cert-manager`
2. 创建 namespace 并打上 `openziti.io/namespace=enabled`
3. 创建 controller PVC
4. 安装或升级 `trust-manager`
5. 安装 controller chart
6. 给 controller 的两张关键证书补宿主机 IP SAN
7. 重启并等待 controller 就绪
8. 删除旧 router release / PVC / edge-router 实体
9. 重新签发 router enrollment JWT
10. 安装 router chart
11. 验证 router 在线状态和对外广播地址

## 关键输入值说明

### controller

真正关键的是这几个值：

```yaml
clientApi:
  advertisedHost: 192.168.198.128
  advertisedPort: 31280
  service:
    type: NodePort

persistence:
  enabled: true
  existingClaim: ziti-controller-db
```

含义：

- `advertisedHost` 是客户端和 router 以后真正会拿到的 controller 地址
- `advertisedPort` 是 controller 的对外端口
- `service.type=NodePort` 表示把 controller 发布到宿主机 NodePort
- `existingClaim` 表示 controller 数据放在持久化 PVC 里

### router

关键的是：

```yaml
ctrl:
  endpoint: 192.168.198.128:31280

enrollmentJwtFromSecret: true
enrollmentJwtSecretName: ziti-router-enrollment

edge:
  advertisedHost: 192.168.198.128
  advertisedPort: 30222
  service:
    type: NodePort

linkListeners:
  transport:
    enabled: false

csr:
  sans:
    noDefaults: true
    dns:
      - localhost
    ip:
      - 127.0.0.1
      - 192.168.198.128

tunnel:
  mode: none
```

含义：

- `ctrl.endpoint` 是 router enroll 和控制面连接用的 controller 地址
- `edge.advertisedHost/Port` 是客户端以后真正要连的 router 地址
- `linkListeners.transport.enabled=false` 是为了避免“router 没打算对外做 fabric link，但一直尝试拨自己”
- `csr.sans.*` 是为了保证 router 服务端证书和宿主机 IP 一致
- `tunnel.mode=none` 表示这只是一个标准 edge router，不让 chart顺手加宿主机/代理隧道能力

## 最重要的坑：controller 证书 SAN

如果你把 controller 广播成裸 IP，例如：

```text
https://192.168.198.128:31280
```

只靠 chart 默认值是不够的。

原因：

- chart 会把 `advertisedHost` 当成 web identity / ctrl-plane identity 的 DNS 名
- 但裸 IP 还需要进 `ipAddresses`
- 不补的话 controller 会因为证书校验问题异常，或者客户端 enroll 时拿到不可用 TLS 身份

这就是为什么脚本会额外 patch 这两张 `Certificate`：

```bash
kubectl patch certificate -n openziti ziti-controller-ctrl-plane-identity \
  --type=merge \
  -p '{"spec":{"ipAddresses":["127.0.0.1","::1","192.168.198.128"]}}'

kubectl patch certificate -n openziti ziti-controller-web-identity-cert \
  --type=merge \
  -p '{"spec":{"ipAddresses":["127.0.0.1","::1","192.168.198.128"]}}'
```

这是整套里最容易漏掉的点。

## 完整手工步骤

如果你不想直接跑脚本，也可以按下面完整手工步骤来。

### 1. 准备变量

```bash
export HOST_IP=192.168.198.128
export ZITI_NS=openziti
export CONTROLLER_RELEASE=ziti-controller
export ROUTER_RELEASE=ziti-router
export ROUTER_NAME=ziti-router
export ROUTER_ROLE=public-router
export CONTROLLER_NODEPORT=31280
export ROUTER_NODEPORT=30222
export CONTROLLER_DB_PVC=ziti-controller-db
```

### 2. 安装 Helm 仓库

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo add openziti https://docs.openziti.io/helm-charts/
helm repo update
```

### 3. 安装 cert-manager

```bash
helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version 1.20.1 \
  --set crds.enabled=true
```

### 4. 创建 namespace 和 PVC

```bash
kubectl get namespace "${ZITI_NS}" >/dev/null 2>&1 || kubectl create namespace "${ZITI_NS}"
kubectl label namespace "${ZITI_NS}" openziti.io/namespace=enabled --overwrite

cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ${CONTROLLER_DB_PVC}
  namespace: ${ZITI_NS}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 2Gi
  storageClassName: local-path
EOF
```

### 5. 安装 trust-manager

```bash
helm upgrade --install trust-manager jetstack/trust-manager \
  --namespace cert-manager \
  --version 0.22.0 \
  --set app.trust.namespace="${ZITI_NS}"
```

### 6. 安装 controller

```bash
helm upgrade --install "${CONTROLLER_RELEASE}" openziti/ziti-controller \
  -n "${ZITI_NS}" \
  --version 3.1.1 \
  --server-side=false \
  -f manifests/openziti/ziti-controller-values.yaml \
  --set persistence.existingClaim="${CONTROLLER_DB_PVC}" \
  --set clientApi.advertisedHost="${HOST_IP}" \
  --set clientApi.advertisedPort="${CONTROLLER_NODEPORT}"
```

### 7. patch controller 证书 SAN

```bash
kubectl patch certificate -n "${ZITI_NS}" "${CONTROLLER_RELEASE}"-ctrl-plane-identity \
  --type=merge \
  -p "{\"spec\":{\"ipAddresses\":[\"127.0.0.1\",\"::1\",\"${HOST_IP}\"]}}"

kubectl patch certificate -n "${ZITI_NS}" "${CONTROLLER_RELEASE}"-web-identity-cert \
  --type=merge \
  -p "{\"spec\":{\"ipAddresses\":[\"127.0.0.1\",\"::1\",\"${HOST_IP}\"]}}"

kubectl wait certificate.cert-manager.io/"${CONTROLLER_RELEASE}"-ctrl-plane-identity \
  -n "${ZITI_NS}" --for=condition=Ready=true --timeout=180s

kubectl wait certificate.cert-manager.io/"${CONTROLLER_RELEASE}"-web-identity-cert \
  -n "${ZITI_NS}" --for=condition=Ready=true --timeout=180s

kubectl rollout restart deployment/"${CONTROLLER_RELEASE}" -n "${ZITI_NS}"
kubectl rollout status deployment/"${CONTROLLER_RELEASE}" -n "${ZITI_NS}" --timeout=180s
```

### 8. 重新创建 router enrollment JWT

先删除旧 router release 和旧实体：

```bash
helm uninstall -n "${ZITI_NS}" "${ROUTER_RELEASE}" || true
kubectl delete pvc -n "${ZITI_NS}" "${ROUTER_RELEASE}" --ignore-not-found
```

如果 controller 里已经有同名 router，也删掉：

```bash
kubectl exec -n "${ZITI_NS}" deploy/"${CONTROLLER_RELEASE}" -- sh -lc '
  ziti edge login 127.0.0.1:1280 --yes \
    -u "$ZITI_ADMIN_USER" \
    -p "$ZITI_ADMIN_PASSWORD" \
    --ca "$ZITI_CTRL_PLANE_CA/ctrl-plane-cas.crt" >/dev/null
  ziti edge list edge-routers -j
'
```

创建新 router JWT：

```bash
ROUTER_JWT="$(kubectl exec -n "${ZITI_NS}" deploy/"${CONTROLLER_RELEASE}" -- sh -lc '
  ziti edge login 127.0.0.1:1280 --yes \
    -u "$ZITI_ADMIN_USER" \
    -p "$ZITI_ADMIN_PASSWORD" \
    --ca "$ZITI_CTRL_PLANE_CA/ctrl-plane-cas.crt" >/dev/null
  ziti edge create edge-router "'"${ROUTER_NAME}"'" \
    --role-attributes "'"${ROUTER_ROLE}"'" \
    --jwt-output-file /tmp/'"${ROUTER_NAME}"'.jwt >/dev/null
  cat /tmp/'"${ROUTER_NAME}"'.jwt
')"

kubectl delete secret ziti-router-enrollment -n "${ZITI_NS}" --ignore-not-found=true
kubectl create secret generic ziti-router-enrollment \
  -n "${ZITI_NS}" \
  --from-literal=enrollmentJwt="${ROUTER_JWT}"
```

### 9. 安装 router

```bash
helm upgrade --install "${ROUTER_RELEASE}" openziti/ziti-router \
  -n "${ZITI_NS}" \
  --version 2.1.0 \
  --server-side=false \
  -f manifests/openziti/ziti-router-values.yaml \
  --set enrollmentJwtSecretName=ziti-router-enrollment \
  --set ctrl.endpoint="${HOST_IP}:${CONTROLLER_NODEPORT}" \
  --set edge.advertisedHost="${HOST_IP}" \
  --set edge.advertisedPort="${ROUTER_NODEPORT}" \
  --set csr.sans.ip[1]="${HOST_IP}"

kubectl rollout status deployment/"${ROUTER_RELEASE}" -n "${ZITI_NS}" --timeout=180s
```

## 验收步骤

### 1. controller 的外部版本接口

```bash
curl --noproxy '*' -sk "https://${HOST_IP}:${CONTROLLER_NODEPORT}/edge/client/v1/version"
```

返回里至少应该看到：

- `https://${HOST_IP}:${CONTROLLER_NODEPORT}/edge/client/v1`
- `https://${HOST_IP}:${CONTROLLER_NODEPORT}/edge/management/v1`

### 2. admin 账号密码

```bash
kubectl get secret \
  -n "${ZITI_NS}" "${CONTROLLER_RELEASE}"-admin-secret \
  -o go-template='{{index .data "admin-user" | base64decode}}{{"\n"}}{{index .data "admin-password" | base64decode}}{{"\n"}}'
```

### 3. router 在线状态

```bash
kubectl exec -n "${ZITI_NS}" deploy/"${CONTROLLER_RELEASE}" -- sh -lc '
  ziti edge login 127.0.0.1:1280 --yes \
    -u "$ZITI_ADMIN_USER" \
    -p "$ZITI_ADMIN_PASSWORD" \
    --ca "$ZITI_CTRL_PLANE_CA/ctrl-plane-cas.crt" >/dev/null
  ziti edge list edge-routers -j
'
```

关键字段应为：

- `isOnline: true`
- `isVerified: true`
- `syncStatus: "SYNC_DONE"`
- `hostname: "${HOST_IP}"`
- `supportedProtocols.tls: "tls://${HOST_IP}:${ROUTER_NODEPORT}"`

### 4. router 证书 SAN

```bash
kubectl exec -n "${ZITI_NS}" deploy/"${ROUTER_RELEASE}" -- sh -lc '
  openssl x509 -in /etc/ziti/config/ziti-router.server.chain.cert -noout -text
'
```

SAN 至少应包含：

- `DNS:localhost`
- `IP Address:127.0.0.1`
- `IP Address:${HOST_IP}`

### 5. `port-audit` 整套验收

如果你跑的是 `scripts/deploy-port-audit-ziti-stack.sh`，再加看两项：

```bash
kubectl exec -n openziti deploy/ziti-controller -- sh -lc '
  ziti edge login 127.0.0.1:1280 --yes \
    -u "$ZITI_ADMIN_USER" \
    -p "$ZITI_ADMIN_PASSWORD" \
    --ca "$ZITI_CTRL_PLANE_CA/ctrl-plane-cas.crt" >/dev/null
  echo --- identities ---
  ziti edge list identities -j | jq ".data[] | select(.name==\"port-audit-host\" or .name==\"port-audit-client\") | {name,edgeRouterConnectionStatus,hasEdgeRouterConnection}"
  echo --- terminators ---
  ziti edge list terminators -j | jq ".data[] | select(.service.name==\"port-audit-web\")"
'
```

至少应满足：

- `port-audit-host.edgeRouterConnectionStatus = "online"`
- `port-audit-host.hasEdgeRouterConnection = true`
- `terminators` 里能看到 `service.name = "port-audit-web"`

## Proof release 的正确做法

如果你想在不动正式 release 名的前提下做 proof，不要换 namespace，直接在同一个 `openziti` namespace 里换 release 名和 NodePort。

例如：

```bash
ZITI_NAMESPACE=openziti \
ZITI_CONTROLLER_RELEASE=ziti-controller-proof \
ZITI_ROUTER_RELEASE=ziti-router-proof \
ZITI_ROUTER_NAME=ziti-router-proof \
ZITI_ROUTER_ROLE=public-router-proof \
ZITI_CONTROLLER_NODEPORT=32280 \
ZITI_ROUTER_NODEPORT=32223 \
ZITI_CONTROLLER_DB_PVC=ziti-controller-proof-db \
bash scripts/deploy-openziti-k3s.sh
```

为什么不推荐换 namespace：

- `trust-manager` 只能从一个 trust namespace 读取 Bundle 信任源
- 这正是官方 controller chart README 提到的限制
- 在这台集群上，`trust-manager` 现在就是以 `openziti` 作为 trust namespace 在运行

## 旧 JWT / 旧 JSON 的处理规则

如果你改过 controller 的对外地址，例如：

- 从 `https://ziti-controller-client.openziti.svc.cluster.local:1280`
- 改成 `https://192.168.198.128:31280`

那下面这两类东西都不能继续复用：

1. 旧的 enrollment JWT
2. 旧的 enroll 后生成的 identity JSON

原因很直接：

- 旧 JWT 里会把 `iss` 和 `ctrls` 固定成旧 controller 地址
- 旧 JSON 也会缓存旧 controller 信息

所以每次 controller 公网地址变化后，规则是：

1. 重新签 JWT
2. 重新 enroll
3. 用新的 JSON 替换旧 JSON
4. host identity 挂在 Pod 里的 secret 也要一起更新

## 策略怎么写才不容易炸

不要把策略写死到 router ID。

推荐：

- edge-router policy 里写 `#public-router`
- service-edge-router policy 里也授权 `#public-router`

不要依赖：

- `@uB6LWb1nzq`
- `@dwW6QWA3e8`

因为 router 一旦重建，ID 一定变，role attribute 不一定变。

## 关于 `cert-manager` 为什么会有 4 个 Pod

这不是重复部署，是 4 个不同角色：

- `cert-manager`
  - 管理 `CertificateRequest / Certificate / Issuer`
- `cert-manager-cainjector`
  - 负责 CA 注入
- `cert-manager-webhook`
  - admission webhook
- `trust-manager`
  - 把 controller 的 CA bundle 同步成 ConfigMap 给各 namespace 用

对你这套 chart 方式来说，它们不是多余的。

## 常见故障与处理

### 1. controller Pod 起不来

优先看：

- `advertisedHost` 是否用了裸 IP
- 如果是裸 IP，`Certificate.spec.ipAddresses` 是否补了宿主机 IP

### 2. router 一直不在线

优先看：

- `ctrl.endpoint` 是否是宿主机 IP + controller NodePort
- `edge.advertisedHost/Port` 是否是宿主机 IP + router NodePort
- 是否还残留旧 router 实体 / 旧 PVC / 旧 enrollment secret
- `linkListeners.transport.enabled` 是否已关闭

### 3. 客户端拿到 JWT 但 enroll 失败

解码 JWT 看这两个字段：

- `iss`
- `ctrls`

如果还是 `*.svc.cluster.local`，说明你拿的是旧 JWT，不是新签出来的公网 JWT。

### 4. host identity 在线，但服务访问失败

这是“业务托管”问题，不是 controller/router 核心安装问题。

优先看：

- `host.v1` 指向的后端地址
- 业务 Pod 里 `ziti-edge-tunnel run-host` 的日志
- 业务 Pod 里是否能直接解析 `service.namespace.svc.cluster.local`

当前这套 `port-audit` 已经验证过可以直接用：

- `k8s-port-audit.port-audit.svc.cluster.local`
- 不需要额外补 `hostAliases`

### 5. 宿主机客户端能连虚拟 IP，但域名偶尔还是旧地址

这是本机 DNS 缓存问题，不是 Ziti service 本身坏了。

在这台机器上我实际遇到过这个现象：

- `port-audit.ziti` 旧缓存还指向旧的 `100.64.0.3`
- controller / service 重建后，新映射已经变成 `100.64.0.5`
- 结果是直接 `curl http://port-audit.ziti` 失败，但 `curl http://100.64.0.5/healthz` 成功

这种情况优先做：

1. 重启宿主机的 `ziti-edge-tunnel` / `ziti-host-client`
2. 重新查询 `getent hosts port-audit.ziti`
3. 再访问域名

## 推荐的最终实践

如果你只维护一套正式 OpenZiti：

- namespace 固定 `openziti`
- controller release 固定 `ziti-controller`
- router release 固定 `ziti-router`
- router role 固定 `public-router`
- NodePort 固定成你自己选好的端口

然后把这两个东西视为唯一入口：

- 复现：`scripts/deploy-openziti-k3s.sh`
- 文档：`README-OPENZITI-K3S.md`

只要不改掉上面那几个关键约束，这套在这台 k3s 上就是已经实测通过的。
