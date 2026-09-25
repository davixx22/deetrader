[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Registry,
    [Parameter(Mandatory)] [string] $DockerRepository,
    [Parameter(Mandatory)] [string] $HelmRepository,
    [Parameter(Mandatory)] [string] $JfrogServerId,
    [string] $Tag = "0.1.0",
    [string] $ChartVersion = "0.1.0",
    [switch] $SkipDockerLogin
)

$ErrorActionPreference = "Stop"
$workspace = Split-Path -Parent $PSScriptRoot
$artifacts = Join-Path $workspace "artifacts"
$chart = Join-Path $workspace "deploy\helm\deetrader"
$frontendImage = "$Registry/$DockerRepository/deetrader-frontend`:$Tag"
$backendImage = "$Registry/$DockerRepository/deetrader-backend`:$Tag"

foreach ($command in "docker", "helm", "jf") {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command '$command' is not installed."
    }
}

if (-not $SkipDockerLogin) {
    if (-not $env:JFROG_USER -or -not $env:JFROG_TOKEN) {
        throw "Set JFROG_USER and JFROG_TOKEN before publishing."
    }
    $env:JFROG_TOKEN | docker login $Registry --username $env:JFROG_USER --password-stdin
    if ($LASTEXITCODE -ne 0) { throw "Docker login failed." }
}

docker build --pull --tag $backendImage (Join-Path $workspace "backend")
if ($LASTEXITCODE -ne 0) { throw "Backend image build failed." }

docker build --pull --build-arg NEXT_PUBLIC_API_URL= --build-arg NEXT_PUBLIC_WS_URL= --tag $frontendImage (Join-Path $workspace "frontend")
if ($LASTEXITCODE -ne 0) { throw "Frontend image build failed." }

docker push $backendImage
if ($LASTEXITCODE -ne 0) { throw "Backend image push failed." }
docker push $frontendImage
if ($LASTEXITCODE -ne 0) { throw "Frontend image push failed." }

New-Item -ItemType Directory -Path $artifacts -Force | Out-Null
helm lint $chart
if ($LASTEXITCODE -ne 0) { throw "Helm lint failed." }
helm package $chart --destination $artifacts --version $ChartVersion --app-version $Tag
if ($LASTEXITCODE -ne 0) { throw "Helm package failed." }

$package = Get-ChildItem -LiteralPath $artifacts -Filter "deetrader-$ChartVersion.tgz" | Select-Object -First 1
if (-not $package) { throw "Packaged Helm chart was not found." }
jf rt upload $package.FullName "$HelmRepository/" --flat=true --server-id=$JfrogServerId
if ($LASTEXITCODE -ne 0) { throw "Helm chart upload failed." }

Write-Output "Published $backendImage"
Write-Output "Published $frontendImage"
Write-Output "Published $($package.Name) to $HelmRepository"
