param(
  [string]$BaseUrl = 'http://localhost',
  [string]$CasesFile = '.\scripts\external-app-runtime\sample-regression-cases.json',
  [switch]$StopOnError
)

$ErrorActionPreference = 'Stop'

function Get-BaseUri {
  param([string]$Url)
  $uri = [Uri]$Url
  return '{0}://{1}{2}' -f $uri.Scheme, $uri.Host, ($(if ($uri.IsDefaultPort) { '' } else { ':' + $uri.Port }))
}

function ConvertTo-Base64Text {
  param([string]$Text)
  return [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Text))
}

function Get-CsrfToken {
  param(
    [Microsoft.PowerShell.Commands.WebRequestSession]$Session,
    [string]$RootUrl
  )
  $cookies = $Session.Cookies.GetCookies([Uri]$RootUrl)
  foreach ($name in @('csrf_token', '__Host-csrf_token')) {
    $cookie = $cookies[$name]
    if ($null -ne $cookie -and -not [string]::IsNullOrWhiteSpace($cookie.Value)) {
      return $cookie.Value
    }
  }
  throw 'csrf_token not found. Please verify login success first.'
}

function Invoke-ConsoleApi {
  param(
    [Parameter(Mandatory = $true)][string]$Method,
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter()][object]$Body = $null,
    [Parameter(Mandatory = $true)][Microsoft.PowerShell.Commands.WebRequestSession]$Session,
    [Parameter(Mandatory = $true)][string]$RootUrl,
    [switch]$SkipCsrf
  )

  $url = "$RootUrl/console/api$Path"
  $headers = @{}
  if (-not $SkipCsrf -and $Method -ne 'GET') {
    $headers['X-CSRF-Token'] = Get-CsrfToken -Session $Session -RootUrl $RootUrl
  }
  $invokeParams = @{
    Method      = $Method
    Uri         = $url
    WebSession  = $Session
    Headers     = $headers
    ContentType = 'application/json'
  }
  if ($null -ne $Body) {
    $invokeParams['Body'] = ($Body | ConvertTo-Json -Depth 30 -Compress)
  }
  return Invoke-RestMethod @invokeParams
}

function Login-Console {
  param(
    [string]$RootUrl,
    [string]$Email,
    [string]$Password,
    [string]$TenantId
  )

  $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
  $payload = @{
    email       = $Email
    password    = ConvertTo-Base64Text -Text $Password
    remember_me = $false
  }
  if (-not [string]::IsNullOrWhiteSpace($TenantId)) {
    $payload['tenant_id'] = $TenantId
  }

  $resp = Invoke-ConsoleApi -Method 'POST' -Path '/login' -Body $payload -Session $session -RootUrl $RootUrl -SkipCsrf
  if ($resp.result -eq 'success') {
    return $session
  }

  if ($resp.code -eq 'tenant_selection_required') {
    $selectedTenant = $TenantId
    if ([string]::IsNullOrWhiteSpace($selectedTenant)) {
      $selectedTenant = $resp.selected_tenant_id
      if ([string]::IsNullOrWhiteSpace($selectedTenant) -and $resp.tenants -and $resp.tenants.Count -gt 0) {
        $selectedTenant = $resp.tenants[0].id
      }
    }
    if ([string]::IsNullOrWhiteSpace($selectedTenant)) {
        throw 'Login failed: account has multiple tenants but no tenant_id was resolved.'
    }
    $payload['tenant_id'] = $selectedTenant
    $retry = Invoke-ConsoleApi -Method 'POST' -Path '/login' -Body $payload -Session $session -RootUrl $RootUrl -SkipCsrf
    if ($retry.result -ne 'success') {
      throw "Second login failed: $($retry | ConvertTo-Json -Depth 10 -Compress)"
    }
    return $session
  }

  throw "Login failed: $($resp | ConvertTo-Json -Depth 10 -Compress)"
}

function Build-CaseResult {
  param(
    [string]$Name,
    [bool]$Passed,
    [string]$Message
  )
  return [PSCustomObject]@{
    name    = $Name
    passed  = $Passed
    message = $Message
  }
}

$rootUrl = Get-BaseUri -Url $BaseUrl
if (-not (Test-Path -LiteralPath $CasesFile)) {
  throw "Regression cases file not found: $CasesFile"
}

$cases = Get-Content -LiteralPath $CasesFile -Raw -Encoding UTF8 | ConvertFrom-Json
if ($null -eq $cases -or $cases.Count -eq 0) {
  throw 'Regression cases are empty.'
}

$results = New-Object System.Collections.Generic.List[object]

foreach ($case in $cases) {
  $name = [string]$case.name
  Write-Host "==> Run case: $name" -ForegroundColor Cyan
  try {
    $session = Login-Console -RootUrl $rootUrl -Email $case.email -Password $case.password -TenantId $case.tenant_id

    $contextToken = $null
    if ($case.context_token_env) {
      $contextToken = [Environment]::GetEnvironmentVariable([string]$case.context_token_env)
    }
    if ($case.require_context_token -eq $true -and [string]::IsNullOrWhiteSpace($contextToken)) {
      throw "Missing context token env var: $($case.context_token_env)"
    }

    $availableBody = @{
      query       = [string]$case.query
      max_results = 200
    }
    if (-not [string]::IsNullOrWhiteSpace($contextToken)) {
      $availableBody['context_token'] = $contextToken
    }

    $available = Invoke-ConsoleApi -Method 'POST' -Path '/workspaces/current/external-apps/runtime/available-apis' -Body $availableBody -Session $session -RootUrl $rootUrl
    if ($null -eq $available.apis -or $available.apis.Count -eq 0) {
      throw 'list_available_apis returned empty results.'
    }

    $selectedApi = $null
    if ($case.app_name -and $case.api_name) {
      $selectedApi = @($available.apis | Where-Object { $_.app_name -eq $case.app_name -and $_.api_name -eq $case.api_name })[0]
    }
    else {
      $selectedApi = @($available.apis | Where-Object { $_.allowed -eq $true } | Sort-Object -Property @{ Expression = 'routing_score'; Descending = $true })[0]
    }

    if ($null -eq $selectedApi) {
      throw 'No matching candidate API found.'
    }

    if ($null -ne $case.expect_allowed) {
      $expectedAllowed = [bool]$case.expect_allowed
      if ([bool]$selectedApi.allowed -ne $expectedAllowed) {
        throw "allowed assertion failed. expected=$expectedAllowed actual=$($selectedApi.allowed)"
      }
    }

    if ($case.skip_invoke -eq $true) {
      $results.Add((Build-CaseResult -Name $name -Passed $true -Message 'Checked available_apis only, invoke skipped.'))
      continue
    }

    $invokeBody = @{
      app_id  = [string]$selectedApi.app_id
      api_id  = [string]$selectedApi.api_id
      dry_run = $(if ($null -ne $case.dry_run) { [bool]$case.dry_run } else { $true })
      params  = $(if ($case.params) { $case.params } else { @{} })
    }
    if (-not [string]::IsNullOrWhiteSpace($contextToken)) {
      $invokeBody['context_token'] = $contextToken
    }

    $invoke = Invoke-ConsoleApi -Method 'POST' -Path '/workspaces/current/external-apps/runtime/invoke' -Body $invokeBody -Session $session -RootUrl $rootUrl
    if ($invoke.result -ne 'success') {
      throw "invoke_api failed: $($invoke | ConvertTo-Json -Depth 10 -Compress)"
    }

    if ($case.expect_permission_level) {
      $expectedLevel = [string]$case.expect_permission_level
      if ([string]$invoke.permission_level_actual -ne $expectedLevel) {
        throw "permission_level_actual assertion failed. expected=$expectedLevel actual=$($invoke.permission_level_actual)"
      }
    }

    $results.Add((Build-CaseResult -Name $name -Passed $true -Message "passed; trace_id=$($invoke.trace_id)"))
  }
  catch {
    $results.Add((Build-CaseResult -Name $name -Passed $false -Message $_.Exception.Message))
    if ($StopOnError) {
      break
    }
  }
}

$failed = @($results | Where-Object { $_.passed -eq $false })
Write-Host ''
Write-Host '==> Regression summary' -ForegroundColor Cyan
$results | Format-Table -AutoSize

if ($failed.Count -gt 0) {
  Write-Host "Failed cases: $($failed.Count)." -ForegroundColor Red
  exit 1
}

Write-Host 'All cases passed.' -ForegroundColor Green
