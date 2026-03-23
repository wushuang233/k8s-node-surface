$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Version = (Get-Content (Join-Path $RepoRoot "VERSION") | Select-Object -First 1).Trim()
$Image = "local/k8s-port-audit:$Version"
$BundleDir = Join-Path $RepoRoot "dist/k8s-port-audit-local-$Version"
$TarPath = Join-Path $BundleDir "k8s-port-audit-$Version.tar"
$ManifestSource = Join-Path $RepoRoot "manifests/k8s-port-audit-local.yaml"
$ManifestPath = Join-Path $BundleDir "k8s-port-audit-local.yaml"
$ImportScriptSource = Join-Path $RepoRoot "scripts/import-and-apply.sh"
$ImportScriptPath = Join-Path $BundleDir "import-and-apply.sh"
$QuickstartSource = Join-Path $RepoRoot "README-DEPLOY.md"
$QuickstartPath = Join-Path $BundleDir "README.md"
$VersionPath = Join-Path $BundleDir "VERSION"
$DeployDocPath = Join-Path $BundleDir "DEPLOY.md"

function Assert-LastExitCode {
    param(
        [string]$Step
    )

    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

docker info | Out-Null
Assert-LastExitCode "docker info"

if (-not (Test-Path $ManifestSource)) {
    throw "缺少清单文件: $ManifestSource"
}

if (-not (Select-String -Path $ManifestSource -Pattern "image:\s+local/k8s-port-audit:$Version" -Quiet)) {
    throw "清单里的镜像标签与 VERSION ($Version) 不一致: $ManifestSource"
}

# dist 目录只保留当前版本的 bundle，避免离线交付时误拿旧包。
Get-ChildItem -Path (Join-Path $RepoRoot "dist") -Directory -Filter "k8s-port-audit-local-*" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne "k8s-port-audit-local-$Version" } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Force -Path $BundleDir | Out-Null

if (-not $env:KEEP_DOCKER_PROXY) {
    Remove-Item Env:HTTP_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:HTTPS_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:http_proxy -ErrorAction SilentlyContinue
    Remove-Item Env:https_proxy -ErrorAction SilentlyContinue
}

if ($env:SKIP_DOCKER_BUILD -ne "1") {
    docker build -t $Image $RepoRoot
    Assert-LastExitCode "docker build"
} else {
    docker image inspect $Image | Out-Null
    Assert-LastExitCode "docker image inspect"
}

docker save -o $TarPath $Image
Assert-LastExitCode "docker save"

Copy-Item $ManifestSource $ManifestPath -Force
Copy-Item $ImportScriptSource $ImportScriptPath -Force
Copy-Item $QuickstartSource $QuickstartPath -Force
Set-Content -Path $VersionPath -Value $Version

@"
# 离线部署说明

Bundle 版本：$Version

目录内容：

- k8s-port-audit-$Version.tar
- k8s-port-audit-local.yaml
- import-and-apply.sh
- VERSION

目标机器执行：

```bash
sudo ctr -n k8s.io images import ./k8s-port-audit-$Version.tar
kubectl apply -f ./k8s-port-audit-local.yaml
kubectl -n port-audit rollout status deployment/k8s-port-audit --timeout=180s
```

或直接执行：

```bash
chmod +x ./import-and-apply.sh
./import-and-apply.sh
```
"@ | Set-Content -Path $DeployDocPath

Write-Host "离线 bundle 已生成: $BundleDir"
Write-Host "清单文件: $ManifestPath"
Write-Host "镜像归档: $TarPath"
