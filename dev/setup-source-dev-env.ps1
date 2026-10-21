param(
  [string]$DevServerHost = "",
  [string]$ApiPublicHost = "localhost",
  [string]$ApiCallbackHost = "host.docker.internal",
  [string]$MiddlewareDbHost = "host.docker.internal",
  [string]$DbUsername = "",
  [string]$DbPassword = "",
  [string]$DbName = "",
  [string]$RedisPassword = "",
  [switch]$Force,
  [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
  @"
Generate local development env files for source-run web/api with middleware on a dev server.

Usage:
  powershell -ExecutionPolicy Bypass -File dev/setup-source-dev-env.ps1 -DevServerHost 192.168.3.201 -Force

Common options:
  -DevServerHost   Host/IP where Docker middleware ports are exposed.
  -ApiPublicHost   Browser-visible API host for web env. Use localhost when web/api run on this machine.
  -ApiCallbackHost Hostname that middleware containers use to call the source API.
                   Use host.docker.internal when API runs on the same Docker host.
                   Use your workstation LAN IP when API runs outside the dev server.
  -MiddlewareDbHost Hostname that middleware containers use to connect PostgreSQL.
                    Use host.docker.internal when PostgreSQL runs on the dev server host.
  -Force           Overwrite existing ignored env files.

Generated files:
  api/.env
  web/.env.local
  docker/dev/middleware.env

The generated middleware env assumes PostgreSQL is an existing external service,
not a Docker Compose service.
"@
  exit 0
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$ExistingMiddlewareEnvPath = Join-Path $Root "docker/dev/middleware.env"

function Read-DevEnvFile {
  param([string]$Path)

  $Values = @{}
  if (-not (Test-Path -LiteralPath $Path)) {
    return $Values
  }

  foreach ($Line in Get-Content -LiteralPath $Path) {
    $Trimmed = $Line.Trim()
    if ($Trimmed.Length -eq 0 -or $Trimmed.StartsWith("#")) {
      continue
    }

    $Parts = $Trimmed.Split("=", 2)
    if ($Parts.Count -eq 2) {
      $Values[$Parts[0]] = $Parts[1]
    }
  }

  return $Values
}

function Write-DevEnvFile {
  param(
    [string]$Path,
    [string]$Content
  )

  if ((Test-Path -LiteralPath $Path) -and -not $Force) {
    Write-Warning "$Path already exists; use -Force to overwrite it."
    return
  }

  $Directory = Split-Path -Parent $Path
  if (-not (Test-Path -LiteralPath $Directory)) {
    New-Item -ItemType Directory -Path $Directory | Out-Null
  }

  Set-Content -LiteralPath $Path -Value $Content.TrimStart() -Encoding UTF8
  Write-Host "Wrote $Path"
}

$ExistingMiddlewareEnv = Read-DevEnvFile -Path $ExistingMiddlewareEnvPath

if (-not $DevServerHost) {
  $ExistingDbHost = $ExistingMiddlewareEnv["DB_HOST"]
  if ($ExistingDbHost -and $ExistingDbHost -notin @("db_postgres", "db_mysql", "localhost", "127.0.0.1", "redis")) {
    $DevServerHost = $ExistingDbHost
  }
  else {
    $DevServerHost = "192.168.3.201"
  }
}

if (-not $DbUsername) {
  $DbUsername = if ($ExistingMiddlewareEnv["DB_USERNAME"]) { $ExistingMiddlewareEnv["DB_USERNAME"] } else { "postgres" }
}

if (-not $DbPassword) {
  $DbPassword = if ($ExistingMiddlewareEnv["DB_PASSWORD"]) { $ExistingMiddlewareEnv["DB_PASSWORD"] } else { "difyai123456" }
}

if (-not $DbName) {
  $DbName = if ($ExistingMiddlewareEnv["DB_DATABASE"]) { $ExistingMiddlewareEnv["DB_DATABASE"] } else { "dify" }
}

if (-not $RedisPassword) {
  $RedisPassword = if ($ExistingMiddlewareEnv["REDIS_PASSWORD"]) { $ExistingMiddlewareEnv["REDIS_PASSWORD"] } else { "difyai123456" }
}

$ApiBaseUrl = "http://${ApiPublicHost}:5001"
$WebBaseUrl = "http://${ApiPublicHost}:3000"
$ApiCallbackUrl = "http://${ApiCallbackHost}:5001"

$ApiEnv = @"
SECRET_KEY=dify-source-dev-secret-key-change-me
DEPLOY_ENV=DEVELOPMENT
EDITION=SELF_HOSTED
DEBUG=true
FLASK_DEBUG=true

CONSOLE_API_URL=$ApiBaseUrl
CONSOLE_WEB_URL=$WebBaseUrl
SERVICE_API_URL=$ApiBaseUrl
APP_WEB_URL=$WebBaseUrl
FILES_URL=$ApiBaseUrl
INTERNAL_FILES_URL=$ApiCallbackUrl
TRIGGER_URL=$ApiBaseUrl

WEB_API_CORS_ALLOW_ORIGINS=http://localhost:3000,http://${ApiPublicHost}:3000,*
CONSOLE_CORS_ALLOW_ORIGINS=http://localhost:3000,http://${ApiPublicHost}:3000,*

DB_TYPE=postgresql
DB_USERNAME=$DbUsername
DB_PASSWORD=$DbPassword
DB_HOST=$DevServerHost
DB_PORT=5432
DB_DATABASE=$DbName

REDIS_HOST=$DevServerHost
REDIS_PORT=16379
REDIS_PASSWORD=$RedisPassword
REDIS_USE_SSL=false
REDIS_DB=0
CELERY_BROKER_URL=redis://:$RedisPassword@${DevServerHost}:16379/1
CELERY_BACKEND=redis

VECTOR_STORE=weaviate
WEAVIATE_ENDPOINT=http://${DevServerHost}:8080
WEAVIATE_API_KEY=WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih
WEAVIATE_BATCH_SIZE=100
WEAVIATE_TOKENIZATION=word

CODE_EXECUTION_ENDPOINT=http://${DevServerHost}:8194
CODE_EXECUTION_API_KEY=dify-sandbox
CODE_EXECUTION_SSL_VERIFY=True

SSRF_PROXY_HTTP_URL=http://${DevServerHost}:3128
SSRF_PROXY_HTTPS_URL=http://${DevServerHost}:3128

PLUGIN_DAEMON_KEY=lYkiYYT6owG+71oLerGzA7GXCgOT++6ovaezWAjpCjf+Sjc3ZtU+qUEi
PLUGIN_DAEMON_URL=http://${DevServerHost}:5002
PLUGIN_REMOTE_INSTALL_HOST=$DevServerHost
PLUGIN_REMOTE_INSTALL_PORT=5003
INNER_API_KEY_FOR_PLUGIN=QaHbTe77CtuXmsfyhR7+vRjI/+XbV1AaFy691iy+kGDv2Jvy0/eAh8Y1
ENDPOINT_URL_TEMPLATE=http://${DevServerHost}:5002/e/{hook_id}

STORAGE_TYPE=opendal
OPENDAL_SCHEME=fs
OPENDAL_FS_ROOT=storage

MARKETPLACE_ENABLED=true
MARKETPLACE_API_URL=https://marketplace.dify.ai
SWAGGER_UI_ENABLED=true
"@

$WebEnv = @"
NEXT_PUBLIC_DEPLOY_ENV=DEVELOPMENT
NEXT_PUBLIC_EDITION=SELF_HOSTED
NEXT_PUBLIC_BASE_PATH=
NEXT_PUBLIC_API_PREFIX=$ApiBaseUrl/console/api
NEXT_PUBLIC_PUBLIC_API_PREFIX=$ApiBaseUrl/api
NEXT_PUBLIC_SOCKET_URL=ws://${ApiPublicHost}:5001
NEXT_PUBLIC_COOKIE_DOMAIN=

NEXT_PUBLIC_MARKETPLACE_API_PREFIX=https://marketplace.dify.ai/api/v1
NEXT_PUBLIC_MARKETPLACE_URL_PREFIX=https://marketplace.dify.ai
NEXT_TELEMETRY_DISABLED=1

NEXT_PUBLIC_UPLOAD_IMAGE_AS_ICON=false
NEXT_PUBLIC_TEXT_GENERATION_TIMEOUT_MS=60000
TEXT_GENERATION_TIMEOUT_MS=60000
NEXT_PUBLIC_ALLOW_UNSAFE_DATA_SCHEME=false
NEXT_PUBLIC_TOP_K_MAX_VALUE=10
NEXT_PUBLIC_INDEXING_MAX_SEGMENTATION_TOKENS_LENGTH=4000
INDEXING_MAX_SEGMENTATION_TOKENS_LENGTH=4000
NEXT_PUBLIC_LOOP_NODE_MAX_COUNT=100
NEXT_PUBLIC_MAX_TOOLS_NUM=10
NEXT_PUBLIC_MAX_PARALLEL_LIMIT=10
NEXT_PUBLIC_MAX_ITERATIONS_NUM=99
NEXT_PUBLIC_ENABLE_WEBSITE_JINAREADER=true
NEXT_PUBLIC_ENABLE_WEBSITE_FIRECRAWL=true
NEXT_PUBLIC_ENABLE_WEBSITE_WATERCRAWL=true
NEXT_PUBLIC_ENABLE_SINGLE_DOLLAR_LATEX=false
NEXT_PUBLIC_MAX_TREE_DEPTH=50
NEXT_PUBLIC_BATCH_CONCURRENCY=5
"@

$MiddlewareEnv = @"
DB_TYPE=postgresql
DB_USERNAME=$DbUsername
DB_PASSWORD=$DbPassword
DB_HOST=$MiddlewareDbHost
DB_PORT=5432
DB_DATABASE=$DbName
DB_PLUGIN_DATABASE=dify_plugin

PGDATA=/var/lib/postgresql/data/pgdata
PGDATA_HOST_VOLUME=./volumes/db/data
POSTGRES_MAX_CONNECTIONS=100
POSTGRES_SHARED_BUFFERS=128MB
POSTGRES_WORK_MEM=4MB
POSTGRES_MAINTENANCE_WORK_MEM=64MB
POSTGRES_EFFECTIVE_CACHE_SIZE=4096MB
POSTGRES_STATEMENT_TIMEOUT=0
POSTGRES_IDLE_IN_TRANSACTION_SESSION_TIMEOUT=0

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_HOST_VOLUME=./volumes/redis/data
REDIS_PASSWORD=$RedisPassword
REDIS_MAX_CONNECTIONS=

SANDBOX_API_KEY=dify-sandbox
SANDBOX_GIN_MODE=release
SANDBOX_WORKER_TIMEOUT=15
SANDBOX_ENABLE_NETWORK=true
SANDBOX_HTTP_PROXY=http://ssrf_proxy:3128
SANDBOX_HTTPS_PROXY=http://ssrf_proxy:3128
SANDBOX_PORT=8194

SSRF_HTTP_PORT=3128
SSRF_COREDUMP_DIR=/var/spool/squid
SSRF_REVERSE_PROXY_PORT=8194
SSRF_SANDBOX_HOST=sandbox

VECTOR_STORE=weaviate
WEAVIATE_QUERY_DEFAULTS_LIMIT=25
WEAVIATE_AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=false
WEAVIATE_DEFAULT_VECTORIZER_MODULE=none
WEAVIATE_CLUSTER_HOSTNAME=node1
WEAVIATE_AUTHENTICATION_APIKEY_ENABLED=true
WEAVIATE_AUTHENTICATION_APIKEY_ALLOWED_KEYS=WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih
WEAVIATE_AUTHENTICATION_APIKEY_USERS=hello@dify.ai
WEAVIATE_AUTHORIZATION_ADMINLIST_ENABLED=true
WEAVIATE_AUTHORIZATION_ADMINLIST_USERS=hello@dify.ai
WEAVIATE_DISABLE_TELEMETRY=false
WEAVIATE_HOST_VOLUME=./volumes/weaviate

COMPOSE_PROFILES=weaviate
EXPOSE_POSTGRES_PORT=5432
EXPOSE_REDIS_PORT=16379
EXPOSE_SANDBOX_PORT=8194
EXPOSE_SSRF_PROXY_PORT=3128
EXPOSE_WEAVIATE_PORT=8080
EXPOSE_WEAVIATE_GRPC_PORT=50051
EXPOSE_PLUGIN_DAEMON_PORT=5002
EXPOSE_PLUGIN_DEBUGGING_PORT=5003

PLUGIN_DAEMON_PORT=5002
PLUGIN_DAEMON_KEY=lYkiYYT6owG+71oLerGzA7GXCgOT++6ovaezWAjpCjf+Sjc3ZtU+qUEi
PLUGIN_DAEMON_URL=http://${DevServerHost}:5002
PLUGIN_MAX_PACKAGE_SIZE=52428800
PLUGIN_PPROF_ENABLED=false
PLUGIN_WORKING_PATH=/app/storage/cwd
PLUGIN_DEBUGGING_HOST=0.0.0.0
PLUGIN_DEBUGGING_PORT=5003
PLUGIN_DIFY_INNER_API_KEY=QaHbTe77CtuXmsfyhR7+vRjI/+XbV1AaFy691iy+kGDv2Jvy0/eAh8Y1
PLUGIN_DIFY_INNER_API_URL=$ApiCallbackUrl
ENDPOINT_URL_TEMPLATE=http://${DevServerHost}:5002/e/{hook_id}

MARKETPLACE_ENABLED=true
MARKETPLACE_API_URL=https://marketplace.dify.ai
FORCE_VERIFYING_SIGNATURE=false
PLUGIN_PYTHON_ENV_INIT_TIMEOUT=120
PLUGIN_MAX_EXECUTION_TIMEOUT=600
PIP_MIRROR_URL=
"@

Write-DevEnvFile -Path (Join-Path $Root "api/.env") -Content $ApiEnv
Write-DevEnvFile -Path (Join-Path $Root "web/.env.local") -Content $WebEnv
Write-DevEnvFile -Path (Join-Path $Root "docker/dev/middleware.env") -Content $MiddlewareEnv

Write-Host ""
Write-Host "Next:"
Write-Host "  1. Start middleware on the dev server from docker/dev:"
Write-Host "     docker compose --env-file middleware.env -f docker-compose.yaml -p dify up -d redis sandbox plugin_daemon ssrf_proxy weaviate"
Write-Host "  2. Start source API: ./dev/start-api"
Write-Host "  3. Start source worker when needed: ./dev/start-worker"
Write-Host "  4. Start source web: ./dev/start-web"
