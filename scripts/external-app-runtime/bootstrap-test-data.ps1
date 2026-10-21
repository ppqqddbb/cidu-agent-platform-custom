param(
  [string]$BaseUrl = 'http://localhost',
  [string]$Email = '1781401015@qq.com',
  [string]$Password = 'Phase6@Admin1',
  [string]$TenantAId = '',
  [string]$TenantBId = '',
  [switch]$UseDefaultTenantAsA
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
  $encodedPassword = ConvertTo-Base64Text -Text $Password
  $payload = @{
    email       = $Email
    password    = $encodedPassword
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
    $candidateTenantId = $TenantId
    if ([string]::IsNullOrWhiteSpace($candidateTenantId)) {
      $candidateTenantId = $resp.selected_tenant_id
      if ([string]::IsNullOrWhiteSpace($candidateTenantId) -and $resp.tenants -and $resp.tenants.Count -gt 0) {
        $candidateTenantId = $resp.tenants[0].id
      }
    }
    if ([string]::IsNullOrWhiteSpace($candidateTenantId)) {
      throw 'Login failed: account has multiple tenants but no tenant_id was resolved.'
    }

    $payload['tenant_id'] = $candidateTenantId
    $retryResp = Invoke-ConsoleApi -Method 'POST' -Path '/login' -Body $payload -Session $session -RootUrl $RootUrl -SkipCsrf
    if ($retryResp.result -ne 'success') {
      throw "Second login failed: $($retryResp | ConvertTo-Json -Depth 10 -Compress)"
    }
    return $session
  }

  throw "Login failed: $($resp | ConvertTo-Json -Depth 10 -Compress)"
}

function Switch-Tenant {
  param(
    [Microsoft.PowerShell.Commands.WebRequestSession]$Session,
    [string]$RootUrl,
    [string]$TenantId
  )
  if ([string]::IsNullOrWhiteSpace($TenantId)) {
    return
  }
  $resp = Invoke-ConsoleApi -Method 'POST' -Path '/workspaces/switch' -Body @{ tenant_id = $TenantId } -Session $Session -RootUrl $RootUrl
  if ($resp.result -ne 'success') {
    throw "Switch tenant failed: tenant_id=$TenantId resp=$($resp | ConvertTo-Json -Depth 10 -Compress)"
  }
}

function Get-AppByName {
  param(
    [Microsoft.PowerShell.Commands.WebRequestSession]$Session,
    [string]$RootUrl,
    [string]$Name
  )
  $resp = Invoke-ConsoleApi -Method 'GET' -Path '/workspaces/current/external-apps?page=1&page_size=200' -Session $Session -RootUrl $RootUrl
  return @($resp.apps | Where-Object { $_.name -eq $Name })[0]
}

function Upsert-App {
  param(
    [Microsoft.PowerShell.Commands.WebRequestSession]$Session,
    [string]$RootUrl,
    [hashtable]$Payload
  )
  $existing = Get-AppByName -Session $Session -RootUrl $RootUrl -Name $Payload.name
  if ($null -eq $existing) {
    $createResp = Invoke-ConsoleApi -Method 'POST' -Path '/workspaces/current/external-apps' -Body $Payload -Session $Session -RootUrl $RootUrl
    Write-Host "√ Created app: $($Payload.name)" -ForegroundColor Green
    return $createResp.app
  }

  $updateResp = Invoke-ConsoleApi -Method 'PUT' -Path "/workspaces/current/external-apps/$($existing.id)" -Body $Payload -Session $Session -RootUrl $RootUrl
  Write-Host "√ Updated app: $($Payload.name)" -ForegroundColor Yellow
  return $updateResp.app
}

function Get-ApiByMethodPath {
  param(
    [Microsoft.PowerShell.Commands.WebRequestSession]$Session,
    [string]$RootUrl,
    [string]$AppId,
    [string]$Method,
    [string]$Path
  )
  $resp = Invoke-ConsoleApi -Method 'GET' -Path "/workspaces/current/external-apps/$AppId/apis?page=1&page_size=200" -Session $Session -RootUrl $RootUrl
  return @($resp.apis | Where-Object { $_.http_method -eq $Method -and $_.path -eq $Path })[0]
}

function Upsert-Api {
  param(
    [Microsoft.PowerShell.Commands.WebRequestSession]$Session,
    [string]$RootUrl,
    [string]$AppId,
    [hashtable]$Payload
  )
  $existing = Get-ApiByMethodPath -Session $Session -RootUrl $RootUrl -AppId $AppId -Method $Payload.http_method -Path $Payload.path
  if ($null -eq $existing) {
    $createResp = Invoke-ConsoleApi -Method 'POST' -Path "/workspaces/current/external-apps/$AppId/apis" -Body $Payload -Session $Session -RootUrl $RootUrl
    Write-Host "  √ Created API: [$($Payload.http_method)] $($Payload.path)" -ForegroundColor Green
    return $createResp.api
  }

  $updateResp = Invoke-ConsoleApi -Method 'PUT' -Path "/workspaces/current/external-apps/$AppId/apis/$($existing.id)" -Body $Payload -Session $Session -RootUrl $RootUrl
  Write-Host "  √ Updated API: [$($Payload.http_method)] $($Payload.path)" -ForegroundColor Yellow
  return $updateResp.api
}

$rootUrl = Get-BaseUri -Url $BaseUrl
Write-Host "==> Login console: $rootUrl" -ForegroundColor Cyan
$session = Login-Console -RootUrl $rootUrl -Email $Email -Password $Password -TenantId $(if ($UseDefaultTenantAsA) { '' } else { $TenantAId })

$tenantMatrix = @()
if ($UseDefaultTenantAsA) {
  $tenantMatrix += @{ Alias = 'A'; TenantId = '' }
}
elseif (-not [string]::IsNullOrWhiteSpace($TenantAId)) {
  $tenantMatrix += @{ Alias = 'A'; TenantId = $TenantAId }
}
if (-not [string]::IsNullOrWhiteSpace($TenantBId)) {
  $tenantMatrix += @{ Alias = 'B'; TenantId = $TenantBId }
}
if ($tenantMatrix.Count -eq 0) {
  throw 'Please provide at least TenantAId, or use -UseDefaultTenantAsA.'
}

$seedDefinitions = @{
  A = @(
    @{
      app = @{
        name        = 'CRM System A'
        description = 'Tenant A CRM'
        app_purpose = 'Customer and order query'
        call_mode   = 'gateway'
        auth_mode   = 'static_bearer'
        auth_config = @{
          call_mode = 'gateway'
          base_url  = 'https://mock-crm-a.local'
          token     = 'REPLACE_ME_BEARER_TOKEN'
        }
        is_enabled = $true
      }
      apis = @(
        @{
          name                 = 'Get Customer Detail'
          http_method          = 'GET'
          path                 = '/v1/customers/{customer_id}'
          summary              = 'Get customer detail by customer_id'
          description          = 'Return base customer profile'
          api_purpose          = 'Read customer profile'
          required_permissions = @('crm.customer.read')
          request_schema       = @{
            path    = @(@{ name = 'customer_id'; type = 'string'; required = $true; description = 'Customer id' })
            query   = @()
            body    = @()
            headers = @()
          }
          response_schema = @{}
          is_confirmed    = $true
          is_enabled      = $true
        },
        @{
          name                 = 'List Customer Orders'
          http_method          = 'GET'
          path                 = '/v1/customers/{customer_id}/orders'
          summary              = 'List orders by customer_id'
          description          = 'Return customer order list'
          api_purpose          = 'Read customer orders'
          required_permissions = @('crm.order.read')
          request_schema       = @{
            path    = @(@{ name = 'customer_id'; type = 'string'; required = $true; description = 'Customer id' })
            query   = @(@{ name = 'month'; type = 'string'; required = $true; description = 'Month YYYY-MM' })
            body    = @()
            headers = @()
          }
          response_schema = @{}
          is_confirmed    = $true
          is_enabled      = $true
        },
        @{
          name                 = 'Create Order Note'
          http_method          = 'POST'
          path                 = '/v1/orders/{order_id}/notes'
          summary              = 'Create order note'
          description          = 'Write one note into order'
          api_purpose          = 'Write order note'
          required_permissions = @('crm.order.write')
          request_schema       = @{
            path    = @(@{ name = 'order_id'; type = 'string'; required = $true; description = 'Order id' })
            query   = @()
            body    = @(@{ name = 'note'; type = 'string'; required = $true; description = 'Note content' })
            headers = @()
          }
          response_schema = @{}
          is_confirmed    = $true
          is_enabled      = $true
        }
      )
    },
    @{
      app = @{
        name        = 'ERP System A'
        description = 'Tenant A ERP'
        app_purpose = 'Invoice summary'
        call_mode   = 'gateway'
        auth_mode   = 'oauth2_client_credentials'
        auth_config = @{
          call_mode     = 'gateway'
          base_url      = 'https://mock-erp-a.local'
          token_url     = 'https://mock-erp-a.local/oauth/token'
          client_id     = 'erp_client_id'
          client_secret = 'erp_client_secret'
          scope         = 'invoice.read'
        }
        is_enabled = $true
      }
      apis = @(
        @{
          name                 = 'Get Invoice Summary'
          http_method          = 'GET'
          path                 = '/v1/invoices/summary'
          summary              = 'Get monthly invoice summary'
          description          = 'Return invoice summary data'
          api_purpose          = 'Read invoice summary'
          required_permissions = @('erp.invoice.read')
          request_schema       = @{
            path    = @()
            query   = @(@{ name = 'month'; type = 'string'; required = $true; description = 'Month YYYY-MM' })
            body    = @()
            headers = @()
          }
          response_schema = @{}
          is_confirmed    = $true
          is_enabled      = $true
        }
      )
    }
  )
  B = @(
    @{
      app = @{
        name        = 'Ticket System B'
        description = 'Tenant B Ticket System'
        app_purpose = 'Ticket query and update'
        call_mode   = 'gateway'
        auth_mode   = 'custom'
        auth_config = @{
          call_mode   = 'gateway'
          base_url    = 'https://mock-ticket-b.local'
          type        = 'api_key'
          api_key_in  = 'header'
          api_key_name = 'X-API-Key'
          api_key     = 'REPLACE_ME_API_KEY'
        }
        is_enabled = $true
      }
      apis = @(
        @{
          name                 = 'List Tickets'
          http_method          = 'GET'
          path                 = '/v1/tickets'
          summary              = 'List visible tickets'
          description          = 'Return visible tickets for current user'
          api_purpose          = 'Read tickets'
          required_permissions = @('ticket.read')
          request_schema       = @{
            path    = @()
            query   = @(@{ name = 'status'; type = 'string'; required = $false; description = 'Status filter' })
            body    = @()
            headers = @()
          }
          response_schema = @{}
          is_confirmed    = $true
          is_enabled      = $true
        },
        @{
          name                 = 'Update Ticket Status'
          http_method          = 'PATCH'
          path                 = '/v1/tickets/{ticket_id}'
          summary              = 'Update ticket status'
          description          = 'Update status by ticket id'
          api_purpose          = 'Write ticket status'
          required_permissions = @('ticket.write')
          request_schema       = @{
            path    = @(@{ name = 'ticket_id'; type = 'string'; required = $true; description = 'Ticket id' })
            query   = @()
            body    = @(@{ name = 'status'; type = 'string'; required = $true; description = 'Target status' })
            headers = @()
          }
          response_schema = @{}
          is_confirmed    = $true
          is_enabled      = $true
        }
      )
    }
  )
}

foreach ($tenant in $tenantMatrix) {
  $alias = $tenant.Alias
  $tenantId = $tenant.TenantId

  if (-not [string]::IsNullOrWhiteSpace($tenantId)) {
    Write-Host "==> Switch tenant: $alias ($tenantId)" -ForegroundColor Cyan
    Switch-Tenant -Session $session -RootUrl $rootUrl -TenantId $tenantId
  }
  else {
    Write-Host "==> Use current tenant as alias: $alias" -ForegroundColor Cyan
  }

  $definitions = $seedDefinitions[$alias]
  if ($null -eq $definitions) {
    Write-Host "Skip alias ${alias}: no seed definitions." -ForegroundColor DarkYellow
    continue
  }

  foreach ($entry in $definitions) {
    $app = Upsert-App -Session $session -RootUrl $rootUrl -Payload $entry.app
    foreach ($api in $entry.apis) {
      [void](Upsert-Api -Session $session -RootUrl $rootUrl -AppId $app.id -Payload $api)
    }
  }
}

Write-Host '==> Seed completed.' -ForegroundColor Green
