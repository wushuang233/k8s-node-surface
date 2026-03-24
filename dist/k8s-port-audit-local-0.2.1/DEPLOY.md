# 离线部署说明

Bundle 版本：0.2.1

目录内容：

- k8s-port-audit-0.2.1.tar
- k8s-port-audit-local.yaml
- import-and-apply.sh
- VERSION

目标机器执行：

```bash
sudo ctr -n k8s.io images import ./k8s-port-audit-0.2.1.tar
kubectl apply -f ./k8s-port-audit-local.yaml
kubectl -n port-audit rollout status deployment/k8s-port-audit --timeout=180s
```

或直接执行：

```bash
chmod +x ./import-and-apply.sh
./import-and-apply.sh
```
