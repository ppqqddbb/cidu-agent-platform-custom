param(
  [ValidateSet('build', 'host-build', 'package', 'up', 'refresh', 'package-refresh', 'host-refresh', 'logs', 'ps')]
  [string]$Action = 'refresh',
  [string]$ImageTag = 'dify-web:local',
  [switch]$NoCache
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir '..')).Path
$dockerDir = Join-Path $repoRoot 'docker'
$webDir = Join-Path $repoRoot 'web'
$localRuntimeDockerfile = Join-Path $dockerDir 'Dockerfile.web-local-runtime'
$composeArgs = @('-f', 'docker-compose.yaml', '-f', 'docker-compose.local-web.yaml')

function Invoke-Step {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Label,
    [Parameter(Mandatory = $true)]
    [string[]]$Command
  )

  Write-Host "==> $Label" -ForegroundColor Cyan
  Write-Host ($Command -join ' ') -ForegroundColor DarkGray
  & $Command[0] $Command[1..($Command.Length - 1)]
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE."
  }
}

function Invoke-Build {
  $command = @('docker', 'build', '-t', $ImageTag, '--build-arg', 'COMMIT_SHA=local-dev')
  if ($NoCache) {
    $command += '--no-cache'
  }
  $command += @('-f', (Join-Path 'web' 'Dockerfile'), $repoRoot)
  Invoke-Step -Label 'Build local web image' -Command $command
}

function Invoke-HostBuild {
  Push-Location $webDir
  try {
    $env:NEXT_PUBLIC_API_PREFIX = '/console/api'
    $env:NEXT_PUBLIC_PUBLIC_API_PREFIX = '/api'
    Invoke-Step -Label 'Build web app on host' -Command @('pnpm', 'build')
  }
  finally {
    Remove-Item Env:NEXT_PUBLIC_API_PREFIX -ErrorAction SilentlyContinue
    Remove-Item Env:NEXT_PUBLIC_PUBLIC_API_PREFIX -ErrorAction SilentlyContinue
    Pop-Location
  }
}

function Invoke-Up {
  Push-Location $dockerDir
  try {
    $env:LOCAL_DIFY_WEB_IMAGE = $ImageTag
    Invoke-Step -Label 'Recreate web container with local image' -Command @(
      'docker', 'compose', $composeArgs[0], $composeArgs[1], $composeArgs[2], $composeArgs[3],
      'up', '-d', '--no-deps', '--force-recreate', 'web'
    )
  }
  finally {
    Pop-Location
  }
}

function Invoke-Package {
  $standaloneDir = Join-Path $webDir '.next\standalone'
  $staticDir = Join-Path $webDir '.next\static'
  $publicDir = Join-Path $webDir 'public'

  if (-not (Test-Path $standaloneDir)) {
    throw "Missing $standaloneDir. Run a local web build first, then package the Docker image."
  }

  if (-not (Test-Path $staticDir)) {
    throw "Missing $staticDir. Run a local web build first, then package the Docker image."
  }

  if (-not (Test-Path $publicDir)) {
    throw "Missing $publicDir."
  }

  $command = @('docker', 'build', '-t', $ImageTag, '-f', $localRuntimeDockerfile)
  if ($NoCache) {
    $command += '--no-cache'
  }
  $command += $repoRoot
  Invoke-Step -Label 'Package local web image from host build artifacts' -Command $command
}

function Invoke-Logs {
  Push-Location $dockerDir
  try {
    $env:LOCAL_DIFY_WEB_IMAGE = $ImageTag
    Invoke-Step -Label 'Tail web logs' -Command @(
      'docker', 'compose', $composeArgs[0], $composeArgs[1], $composeArgs[2], $composeArgs[3],
      'logs', '--tail', '120', 'web'
    )
  }
  finally {
    Pop-Location
  }
}

function Invoke-Ps {
  Push-Location $dockerDir
  try {
    $env:LOCAL_DIFY_WEB_IMAGE = $ImageTag
    Invoke-Step -Label 'Show web service status' -Command @(
      'docker', 'compose', $composeArgs[0], $composeArgs[1], $composeArgs[2], $composeArgs[3],
      'ps', 'web'
    )
  }
  finally {
    Pop-Location
  }
}

switch ($Action) {
  'build' { Invoke-Build }
  'host-build' { Invoke-HostBuild }
  'package' { Invoke-Package }
  'up' { Invoke-Up }
  'refresh' {
    Invoke-Build
    Invoke-Up
  }
  'package-refresh' {
    Invoke-Package
    Invoke-Up
  }
  'host-refresh' {
    Invoke-HostBuild
    Invoke-Package
    Invoke-Up
  }
  'logs' { Invoke-Logs }
  'ps' { Invoke-Ps }
}
