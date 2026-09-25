[CmdletBinding()]
param(
    [string] $Release = "deetrader",
    [string] $Namespace = "deetrader",
    [Parameter(Mandatory)] [string] $ValuesFile
)

$ErrorActionPreference = "Stop"
$workspace = Split-Path -Parent $PSScriptRoot
$chart = Join-Path $workspace "deploy\helm\deetrader"

foreach ($command in "kubectl", "helm") {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command '$command' is not installed."
    }
}

$resolvedValues = (Resolve-Path -LiteralPath $ValuesFile).Path
helm upgrade --install $Release $chart `
    --namespace $Namespace `
    --create-namespace `
    --values $resolvedValues `
    --atomic `
    --timeout 10m `
    --wait
if ($LASTEXITCODE -ne 0) { throw "Kubernetes deployment failed." }

kubectl rollout status "deployment/$Release-frontend" --namespace $Namespace --timeout=5m
kubectl rollout status "deployment/$Release-backend" --namespace $Namespace --timeout=5m
kubectl rollout status "deployment/$Release-worker" --namespace $Namespace --timeout=5m
