# OpenZiti + Port-Audit 单镜像安装

这份说明对应的是“外部不跑仓库脚本，只导入一个镜像，再 `kubectl apply` 一个 installer manifest” 的用法。
用户侧只需要镜像 tar 和 yaml，不需要再执行仓库里的 shell 脚本。

## 产物

- bundle 镜像：`local/k8s-port-audit-stack:0.2.2`
- installer manifest：[manifests/openziti-stack-installer-local.yaml](/home/wushuang/test-py/k8s-node-surface/manifests/openziti-stack-installer-local.yaml)
- app manifest：[manifests/k8s-port-audit-stack-local.yaml](/home/wushuang/test-py/k8s-node-surface/manifests/k8s-port-audit-stack-local.yaml)
- 构建脚本：[scripts/build-stack-image-bundle.sh](/home/wushuang/test-py/k8s-node-surface/scripts/build-stack-image-bundle.sh)
- 镜像内安装入口：[scripts/run-stack-installer-image.sh](/home/wushuang/test-py/k8s-node-surface/scripts/run-stack-installer-image.sh)

## 这个镜像里包含什么

同一个镜像里已经放了：

- `port-audit` 后端
- 原端口审计前端
- `/ziti/` 管理页
- OpenZiti 安装脚本和清单
- `kubectl / helm / jq`

所以它既能作为：

- `k8s-port-audit` 的业务镜像

也能作为：

- `openziti-stack-installer` 的安装镜像

## 构建 bundle

```bash
bash scripts/build-stack-image-bundle.sh
```

这条脚本现在会先计算“真正参与 bundle 的文件摘要”：

- 如果源码摘要没变化，会直接复用本地已有镜像，只重新导出 tar 和清单
- 如果源码变化了，但本地已经有上一版 bundle，会走 refresh Dockerfile，只覆盖应用代码和清单，不再重复跑 apt/pip
- 只有第一次本地完全没有 bundle 镜像时，才会走完整 `docker build`

如果你就是想强制重建镜像：

```bash
FORCE_DOCKER_BUILD=1 bash scripts/build-stack-image-bundle.sh
```

产物目录类似：

```text
dist/k8s-port-audit-stack-local-0.2.2/
```

## 安装方式

1. 导入镜像

```bash
sudo k3s ctr -n k8s.io images import ./dist/k8s-port-audit-stack-local-0.2.2/k8s-port-audit-stack-0.2.2.tar
```

2. 校验离线包

```bash
sha256sum -c ./dist/k8s-port-audit-stack-local-0.2.2/SHA256SUMS
```

3. 启动 installer Job

```bash
kubectl apply -f ./dist/k8s-port-audit-stack-local-0.2.2/openziti-stack-installer-local.yaml
kubectl logs -n openziti-installer job/openziti-stack-installer -f
```

如果你想让 `/ziti/` 页面默认使用预设 controller 凭据，可以先创建这个可选 Secret：

```bash
kubectl apply -f ./manifests/k8s-port-audit-ziti-admin-secret.example.yaml
```

示例文件在：

- [manifests/k8s-port-audit-ziti-admin-secret.example.yaml](/home/wushuang/test-py/k8s-node-surface/manifests/k8s-port-audit-ziti-admin-secret.example.yaml)

支持的键：

- `ZITI_DEFAULT_CONTROLLER_URL`
- `ZITI_DEFAULT_USERNAME`
- `ZITI_DEFAULT_PASSWORD`

配置后，`port-audit` 登录页可以直接使用这些默认值；密码留空时，后端会自动回退到 Pod 内预设密码。

这个 Job 会在集群里完成：

- `cert-manager`
- `trust-manager`
- `ziti-controller`
- `ziti-router`
- `port-audit` 业务清单
- `port-audit` 对应的 Ziti service / config / policy / identity
- `port-audit-ziti-host`

## 访问

```bash
kubectl -n port-audit port-forward svc/k8s-port-audit 8080:8080
```

打开：

```text
http://127.0.0.1:8080
http://127.0.0.1:8080/ziti/
```

## 注意

- 这套本地 bundle 默认面向单节点或“你已经把同一镜像导入到所有节点”的集群。
- `openziti-stack-installer-local.yaml` 会给 installer Job 绑定 `cluster-admin`，因为它需要安装 chart 和创建跨 namespace 资源。
- 这条安装路径的外部入口不再要求你手动运行仓库里的部署脚本；脚本只存在于镜像内部，作为 installer 的执行逻辑。
