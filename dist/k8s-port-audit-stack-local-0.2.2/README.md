# OpenZiti + Port-Audit 单镜像离线包

版本：0.2.2

镜像：

```text
local/k8s-port-audit-stack:0.2.2
```

目录内容：

- k8s-port-audit-stack-0.2.2.tar
- openziti-stack-installer-local.yaml
- k8s-port-audit-stack-local.yaml
- SHA256SUMS
- VERSION

使用方式：

1. 导入镜像到 k3s/containerd

```bash
sudo k3s ctr -n k8s.io images import ./k8s-port-audit-stack-0.2.2.tar
```

2. 一次性安装整套

```bash
kubectl apply -f ./openziti-stack-installer-local.yaml
kubectl logs -n openziti-installer job/openziti-stack-installer -f
```

这条路径面向单节点 k3s。
用户侧不需要运行仓库脚本，只需要“导入镜像 + apply 一个 installer 清单”。

完成后访问：

```bash
kubectl -n port-audit port-forward svc/k8s-port-audit 8080:8080
```

```text
http://127.0.0.1:8080
http://127.0.0.1:8080/ziti/
```
