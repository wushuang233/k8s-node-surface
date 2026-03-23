# 本地镜像打包说明

本文档只说明两件事：

- 如何从源码构建本地镜像
- 如何导出镜像 tar 或生成完整离线 bundle

部署步骤见 [README-DEPLOY.md](README-DEPLOY.md)。

## 前提

- 当前目录为项目根目录
- 本机已安装 Docker
- [VERSION](/home/wushuang/test-py/snake/VERSION) 与 [manifests/k8s-port-audit-local.yaml](/home/wushuang/test-py/snake/manifests/k8s-port-audit-local.yaml) 里的镜像标签保持一致

当前版本：

```text
0.1.8
```

默认本地镜像名：

```text
local/k8s-port-audit:0.1.8
```

## 1. 仅构建本地镜像

在项目根目录执行：

```bash
docker build -t local/k8s-port-audit:0.1.8 .
```

可选校验：

```bash
docker image inspect local/k8s-port-audit:0.1.8 >/dev/null
docker run --rm local/k8s-port-audit:0.1.8 --help
```

## 2. 只导出镜像 tar

先完成镜像构建，再执行：

```bash
mkdir -p dist/k8s-port-audit-local-0.1.8
docker save -o dist/k8s-port-audit-local-0.1.8/k8s-port-audit-0.1.8.tar local/k8s-port-audit:0.1.8
```

生成结果：

```text
dist/k8s-port-audit-local-0.1.8/k8s-port-audit-0.1.8.tar
```

## 3. 生成完整离线 bundle

完整离线 bundle 包含：

- 镜像 tar
- 本地部署清单
- 导入并应用脚本
- 部署速查文档
- 版本文件

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

## 4. 只刷新 bundle 文档，不重新构建镜像

如果镜像已经存在，本次只想同步文档、清单和脚本，可以执行：

```bash
SKIP_DOCKER_BUILD=1 ./scripts/build-local-bundle.sh
```

这个模式会直接复用本地已有镜像：

```text
local/k8s-port-audit:0.1.8
```

## 5. 常用检查

检查本地镜像是否存在：

```bash
docker images | grep k8s-port-audit
```

检查 tar 是否生成：

```bash
ls -lh dist/k8s-port-audit-local-0.1.8/
```

校验项目结构：

```bash
./scripts/verify-project.sh
```

## 常见问题

### 1. Dockerfile 能构建，但 bundle 脚本失败

先确认：

- Docker daemon 正常
- `VERSION` 与本地部署清单镜像标签一致
- 本机已存在 `local/k8s-port-audit:0.1.8`

只想复用已有镜像时，优先使用：

```bash
SKIP_DOCKER_BUILD=1 ./scripts/build-local-bundle.sh
```

### 2. 基础镜像拉取失败

可先手工测试：

```bash
docker pull python:3.13-slim
```

如果当前环境走代理，bundle 脚本默认会清理常见代理变量。确实需要保留代理时，可显式设置：

```bash
KEEP_DOCKER_PROXY=1 ./scripts/build-local-bundle.sh
```

### 3. 修改了版本号，但脚本报镜像标签不一致

需要同时更新：

- [VERSION](/home/wushuang/test-py/snake/VERSION)
- [manifests/k8s-port-audit-local.yaml](/home/wushuang/test-py/snake/manifests/k8s-port-audit-local.yaml)
- 如有需要，也更新 [manifests/k8s-port-audit.yaml](/home/wushuang/test-py/snake/manifests/k8s-port-audit.yaml)

## 建议流程

推荐顺序：

1. 先运行 [scripts/verify-project.sh](/home/wushuang/test-py/snake/scripts/verify-project.sh)
2. 再构建本地镜像
3. 再生成离线 bundle
4. 最后按 [README-DEPLOY.md](/home/wushuang/test-py/snake/README-DEPLOY.md) 部署
