# 架构说明

保留版本：`0.1.9`

本文件只说明代码分层和运行流程。部署命令见 [README-DEPLOY.md](README-DEPLOY.md)。

## 目标

唯一目标：识别宿主机地址上的 TCP 暴露端口，并给出 Kubernetes 归因。

不包含：

- `ClusterIP`
- `Endpoint / EndpointSlice`
- 普通 `PodIP`
- `UDP`

## 运行流程

单轮扫描顺序如下：

1. 读取配置并初始化 Kubernetes client
2. 发现宿主机暴露路径对应的候选目标
3. 对候选目标执行 TCP 建连
4. 对节点地址执行 full-node TCP 扫描
5. 读取 `/proc` TCP 表补充监听与活跃连接证据
6. 归并结果并生成 dashboard 摘要
7. 监听 `Pod / Service / Node` 变更
   - `Service / Pod` 事件默认走局部刷新
   - `Node` 事件、手动刷新、周期兜底走完整扫描
8. 更新内存报告并通过 HTTP API 提供给前端

## 分层结构

### 入口层

- [main.py](main.py)
  - 兼容入口，保留 `python3 main.py`
- [k8s_port_audit/__main__.py](k8s_port_audit/__main__.py)
  - 支持 `python -m k8s_port_audit`
- [k8s_port_audit/app.py](k8s_port_audit/app.py)
  - 参数解析
  - 配置覆盖
  - 启动重试
  - 周期扫描调度
  - Web 服务启动和关闭

### 配置与依赖层

- [k8s_port_audit/settings/config.py](k8s_port_audit/settings/config.py)
  - YAML 解析
  - 端口范围解析
  - 配置校验
- [k8s_port_audit/runtime/dependencies.py](k8s_port_audit/runtime/dependencies.py)
  - 第三方依赖探测
  - 集群内配置 / 本地 kubeconfig 加载
- [k8s_port_audit/runtime/watcher.py](k8s_port_audit/runtime/watcher.py)
  - Kubernetes watch 事件监听
  - 只对真正影响暴露面的变更发起刷新请求

### 数据模型层

- [k8s_port_audit/domain/models.py](k8s_port_audit/domain/models.py)
  - 探测目标
  - 节点候选地址
  - 暴露候选项与页面对象

### 扫描核心层

- [k8s_port_audit/scan/discovery.py](k8s_port_audit/scan/discovery.py)
  - 将 `Service / Pod / Node` 转换为宿主机地址上的候选目标
- [k8s_port_audit/scan/probe.py](k8s_port_audit/scan/probe.py)
  - 异步 TCP 建连与状态分类
- [k8s_port_audit/scan/traffic.py](k8s_port_audit/scan/traffic.py)
  - 解析 `/proc` TCP 表并生成被动证据索引
- [k8s_port_audit/scan/scanner.py](k8s_port_audit/scan/scanner.py)
  - 编排单轮扫描

### 汇总与状态层

- [k8s_port_audit/report/exposure.py](k8s_port_audit/report/exposure.py)
  - 暴露类型标签
  - 优先级规则
  - 状态排序规则
- [k8s_port_audit/report/platform.py](k8s_port_audit/report/platform.py)
  - Kubernetes 系统组件识别
  - `platformRole` 计算
  - `NV_SYSTEM_GROUPS` 追加规则解析
- [k8s_port_audit/report/exposure_summary.py](k8s_port_audit/report/exposure_summary.py)
  - `address:port` 级别对象归并
  - 主分类选择
  - 对象分组与摘要聚合
- [k8s_port_audit/report/reporting.py](k8s_port_audit/report/reporting.py)
  - 顶层报告结构装配
  - 节点清单整理
  - JSON 输出
- [k8s_port_audit/runtime/state.py](k8s_port_audit/runtime/state.py)
  - 完整报告缓存
  - 面板快照缓存
  - 手动刷新、周期兜底与事件局部刷新协调
- [k8s_port_audit/core.py](k8s_port_audit/core.py)
  - 兼容导出层

### 展示层

- [k8s_port_audit/api/dashboard.py](k8s_port_audit/api/dashboard.py)
  - `/api/dashboard`
  - `/api/scan`
  - `/healthz`
  - 静态资源分发
- [web/app.js](web/app.js)
  - 页面状态、标签页与轮询
- [web/app-data.js](web/app-data.js)
  - 数据归一化、分组、筛选
- [web/app-render.js](web/app-render.js)
  - 页面渲染流程
- [web/render-fragments.js](web/render-fragments.js)
  - 节点卡片
  - 对象卡片
  - 明细表格行
- [web/styles.css](web/styles.css)
  - 样式

## 数据模型

基础键：

- `address`
- `port`
- `status`
- `sources`

`address:port` 为去重维度，`sources` 用于保留多条暴露路径。

示例：同一端口可能同时命中 `NodePort` 与 `LoadBalancer`；主分类只显示一类，但说明字段保留全部命中路径。

## 暴露类型优先级

1. `ExternalIP`
2. `LoadBalancer`
3. `NodePort`
4. `HostPort`
5. `HostNetworkPod`
6. `NodeListener`

## dashboard 摘要缓存

完整报告适合落盘，不适合浏览器高频轮询。

[state.py](k8s_port_audit/runtime/state.py) 同时维护两份数据：

- 完整报告
- 面板快照

这样可以降低 `/api/dashboard` 体积，减轻前端轮询和渲染负担。

## 刷新机制

刷新来源有三类：

1. Kubernetes 事件触发
2. 手动点击“立即刷新”
3. `scan.interval_seconds` 周期兜底

`ScanCoordinator` 负责把这些请求合并到同一个等待入口，避免重复并发扫描。

事件刷新规则：

- `Service` 变化：只刷新对应 `ExternalIP / LoadBalancer / NodePort`
- `Pod` 变化：只刷新对应 `HostPort / HostNetworkPod`
- `Node` 变化：执行完整扫描
- 同一时间窗口内的多条事件会先合并，再进入下一轮刷新

## 交付目录

当前保留目录：

- `config/`
- `k8s_port_audit/`
- `manifests/`
- `scripts/`
- `web/`
- `dist/k8s-port-audit-local-0.1.9/`

当前约定：

- `dist/` 仅保留当前版本 bundle
- 打包脚本生成新 bundle 时自动清理旧版本目录
