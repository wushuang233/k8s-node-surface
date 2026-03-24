# 离线部署速查

离线部署速查，仅保留必要步骤。

## 1. 进入 bundle 目录

```bash
cd k8s-port-audit-local-0.2.1
```

## 2. 导入镜像

普通 Kubernetes：

```bash
sudo ctr -n k8s.io images import ./k8s-port-audit-0.2.1.tar
```

`k3s`：

```bash
sudo k3s ctr -n k8s.io images import ./k8s-port-audit-0.2.1.tar
```

## 3. 应用清单

```bash
kubectl apply -f ./k8s-port-audit-local.yaml
```

## 4. 等待启动

```bash
kubectl -n port-audit rollout status deployment/k8s-port-audit --timeout=180s
```

## 5. 查看 Pod

```bash
kubectl get pods -n port-audit -o wide
```

## 6. 打开面板

```bash
kubectl -n port-audit port-forward svc/k8s-port-audit 8080:8080
```

访问地址：

```text
http://127.0.0.1:8080
```

## 常见问题

### ErrImageNeverPull

含义：调度目标节点未找到本地镜像。

常见原因：

1. 导入到了错误的 containerd

普通 Kubernetes：

```bash
sudo ctr -n k8s.io images ls | grep k8s-port-audit
```

`k3s`：

```bash
sudo k3s ctr -n k8s.io images ls | grep k8s-port-audit
```

2. 集群有多个节点，但只在其中一台节点导入了镜像

先查看调度节点：

```bash
kubectl get pods -n port-audit -o wide
```

若事件中出现：

```text
Scheduled ... to tdx-worker1
ErrImageNeverPull
```

说明 `tdx-worker1` 节点未导入 `local/k8s-port-audit:0.2.1`。

建议做法：对每个可调度节点导入同一个 tar。

## 一次执行完

```bash
cd k8s-port-audit-local-0.2.1
sudo ctr -n k8s.io images import ./k8s-port-audit-0.2.1.tar
kubectl apply -f ./k8s-port-audit-local.yaml
kubectl -n port-audit rollout status deployment/k8s-port-audit --timeout=180s
kubectl get pods -n port-audit -o wide
```
