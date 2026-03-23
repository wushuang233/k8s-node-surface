# 宿主机暴露端口审计

用途：识别宿主机地址上的 TCP 暴露端口，并按 Kubernetes 暴露路径归类。

本地镜像打包步骤见 [README-BUILD.md](README-BUILD.md)。
离线部署步骤见 [README-DEPLOY.md](README-DEPLOY.md)。
代码结构与运行流程见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 范围

纳入结果：

- `ExternalIP`
- `LoadBalancer`
- `NodePort`
- `HostPort`
- `HostNetworkPod`
- `NodeListener`

不纳入结果：

- `ClusterIP`
- `Endpoint / EndpointSlice`
- 普通 `PodIP`
- `UDP`

判定原则：不映射到宿主机地址的端口不进入结果。

## 判定逻辑

### 1. 节点地址主动探测

对每个 `Node` 的下列地址执行真实 TCP 建连：

- `InternalIP`
- `ExternalIP`

探测端口范围来自 [config/scanner-config.yaml](config/scanner-config.yaml) 中的 `ports.full_node_tcp_ports`。
默认值：

```yaml
1-65535
```

这一步用于确认节点地址上哪些端口真实可达。

核心文件：

- [k8s_port_audit/scan/scanner.py](k8s_port_audit/scan/scanner.py)
- [k8s_port_audit/scan/probe.py](k8s_port_audit/scan/probe.py)

### 2. Kubernetes 元数据归因

对开放端口读取 Kubernetes 元数据并归因到以下路径：

- `ExternalIP`
- `LoadBalancer`
- `NodePort`
- `HostPort`
- `HostNetworkPod`
- `NodeListener`

归因来源：

- `ExternalIP / LoadBalancer / NodePort` 对应 `Service`
- `HostPort / HostNetworkPod` 对应 `Pod.spec.containers[].ports`
- 无法匹配到明确对象时归类为 `NodeListener`

核心文件：

- [k8s_port_audit/scan/discovery.py](k8s_port_audit/scan/discovery.py)
- [k8s_port_audit/report/exposure.py](k8s_port_audit/report/exposure.py)
- [k8s_port_audit/report/exposure_summary.py](k8s_port_audit/report/exposure_summary.py)
- [k8s_port_audit/report/reporting.py](k8s_port_audit/report/reporting.py)

### 3. 被动 TCP 证据

如已挂载宿主机 `/proc`，则补充解析：

- `/host-proc/1/net/tcp`
- `/host-proc/1/net/tcp6`

补充证据：

- `监听`：检测到监听状态
- `流量`：检测到非 `LISTEN` 的活跃连接状态

该部分仅覆盖扫描器所在节点。

核心文件：

- [k8s_port_audit/scan/traffic.py](k8s_port_audit/scan/traffic.py)

## 分类优先级

同一 `address:port` 命中多条路径时，主分类按以下顺序确定：

1. `ExternalIP`
2. `LoadBalancer`
3. `NodePort`
4. `HostPort`
5. `HostNetworkPod`
6. `NodeListener`

其他命中路径保留在说明字段中。

## 目录结构

```text
.
├── VERSION
├── Dockerfile
├── main.py
├── requirements.txt
├── README.md
├── README-BUILD.md
├── README-DEPLOY.md
├── ARCHITECTURE.md
├── config/
│   └── scanner-config.yaml
├── k8s_port_audit/
│   ├── __init__.py
│   ├── __main__.py
│   ├── app.py
│   ├── core.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── dashboard.py
│   ├── domain/
│   │   ├── __init__.py
│   │   └── models.py
│   ├── report/
│   │   ├── __init__.py
│   │   ├── exposure.py
│   │   ├── exposure_summary.py
│   │   └── reporting.py
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── dependencies.py
│   │   └── state.py
│   ├── scan/
│   │   ├── __init__.py
│   │   ├── discovery.py
│   │   ├── probe.py
│   │   ├── scanner.py
│   │   └── traffic.py
│   └── settings/
│       ├── __init__.py
│       └── config.py
├── manifests/
│   ├── k8s-port-audit.yaml
│   └── k8s-port-audit-local.yaml
├── scripts/
│   ├── build-local-bundle.ps1
│   ├── build-local-bundle.sh
│   ├── import-and-apply.sh
│   └── verify-project.sh
├── web/
│   ├── app-data.js
│   ├── app-render.js
│   ├── app.js
│   ├── index.html
│   ├── render-fragments.js
│   └── styles.css
└── dist/
    └── k8s-port-audit-local-0.1.8/
```

## 模块说明

- [k8s_port_audit/app.py](k8s_port_audit/app.py)：启动、参数解析、扫描调度、重试
- [k8s_port_audit/settings/config.py](k8s_port_audit/settings/config.py)：配置解析与校验
- [k8s_port_audit/runtime/dependencies.py](k8s_port_audit/runtime/dependencies.py)：依赖检查与 Kubernetes 配置加载
- [k8s_port_audit/runtime/state.py](k8s_port_audit/runtime/state.py)：报告缓存与手动刷新协调
- [k8s_port_audit/domain/models.py](k8s_port_audit/domain/models.py)：共享数据模型
- [k8s_port_audit/scan/discovery.py](k8s_port_audit/scan/discovery.py)：宿主机暴露路径发现
- [k8s_port_audit/scan/scanner.py](k8s_port_audit/scan/scanner.py)：单轮扫描编排
- [k8s_port_audit/scan/probe.py](k8s_port_audit/scan/probe.py)：异步 TCP 探测与状态分类
- [k8s_port_audit/scan/traffic.py](k8s_port_audit/scan/traffic.py)：`/proc` TCP 证据解析
- [k8s_port_audit/report/exposure.py](k8s_port_audit/report/exposure.py)：暴露类型、优先级与状态排序常量
- [k8s_port_audit/report/exposure_summary.py](k8s_port_audit/report/exposure_summary.py)：页面对象归并、主分类选择、对象分组
- [k8s_port_audit/report/reporting.py](k8s_port_audit/report/reporting.py)：报告结构装配与 JSON 输出
- [k8s_port_audit/api/dashboard.py](k8s_port_audit/api/dashboard.py)：HTTP API 与静态页面
- [web/app.js](web/app.js)：前端状态管理与轮询
- [web/app-data.js](web/app-data.js)：前端数据归一化与分组
- [web/app-render.js](web/app-render.js)：页面渲染
- [web/render-fragments.js](web/render-fragments.js)：节点卡片、对象卡片、表格行片段
- [web/styles.css](web/styles.css)：样式

## 本地运行

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

执行单次扫描：

```bash
python3 main.py --config config/scanner-config.yaml --once
```

启动面板：

```bash
python3 main.py --config config/scanner-config.yaml --web-host 127.0.0.1 --web-port 8080
```

访问地址：

```text
http://127.0.0.1:8080
```

说明：

- 优先加载集群内配置，失败后回退到本机 `kubeconfig`
- 当前仅支持 `TCP`
- 页面支持手动刷新
- 如在宿主机本地运行源码并需要被动 TCP 证据，可将 `traffic_observation.host_proc_root` 设为 `/proc`

## 配置项

主要配置项见 [config/scanner-config.yaml](config/scanner-config.yaml)：

- `scan`：超时、并发、扫描周期、输出路径
- `scope`：命名空间白名单与黑名单
- `discovery`：是否启用各类宿主机暴露路径发现
- `ports.full_node_tcp_ports`：节点地址探测端口范围
- `traffic_observation`：宿主机 `/proc` TCP 证据开关与路径
- `web`：监听地址、端口、刷新周期

## Kubernetes 部署

### 镜像仓库部署

```bash
docker build -t your-registry/k8s-port-audit:0.1.8 .
docker push your-registry/k8s-port-audit:0.1.8
kubectl apply -f manifests/k8s-port-audit.yaml
```

### 离线部署

Linux：

```bash
chmod +x ./scripts/build-local-bundle.sh
./scripts/build-local-bundle.sh
```

Windows PowerShell：

```powershell
./scripts/build-local-bundle.ps1
```

生成目录：

```text
dist/k8s-port-audit-local-0.1.8/
```

目录内容：

- `k8s-port-audit-0.1.8.tar`
- `k8s-port-audit-local.yaml`
- `import-and-apply.sh`
- `README.md`
- `DEPLOY.md`
- `VERSION`

目标机器执行：

```bash
cd k8s-port-audit-local-0.1.8
sudo ctr -n k8s.io images import ./k8s-port-audit-0.1.8.tar
kubectl apply -f ./k8s-port-audit-local.yaml
kubectl -n port-audit rollout status deployment/k8s-port-audit --timeout=180s
```

或直接运行：

```bash
cd k8s-port-audit-local-0.1.8
chmod +x ./import-and-apply.sh
./import-and-apply.sh
```

## 权限与运行要求

默认清单包含以下能力：

- 读取 `pods`
- 读取 `services`
- 读取 `nodes`
- 通过 `MY_NODE_NAME` 获取运行节点名称
- 只读挂载宿主机 `/proc` 到 `/host-proc`

用途：

- 获取节点地址
- 识别宿主机暴露路径
- 补充当前节点的监听与活跃连接证据

## 限制

- 探测视角为扫描器所在网络到节点地址的 TCP 建连
- 被动 TCP 证据仅覆盖当前节点
- 最终公网可达性仍受 ACL、防火墙、NAT、WAF 等因素影响
- 不支持 `UDP`

## 维护约定

- 当前保留版本：`0.1.8`
- [VERSION](VERSION) 固定为 `0.1.8`
- `dist/` 仅保留 [k8s-port-audit-local-0.1.8](dist/k8s-port-audit-local-0.1.8)
- 打包脚本生成新 bundle 时自动清理旧版本目录
