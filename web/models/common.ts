import type { GetAccountProfileResponse } from '@dify/contracts/api/console/account/types.gen'
import type { GetVersionResponse } from '@dify/contracts/api/console/version/types.gen'
import type { Role } from './access-control'
import type { I18nText } from '@/i18n-config/language'
import type { Model } from '@/types/app'

export type CommonResponse = {
  result: 'success' | 'fail'
}

export type SetupStatusResponse = {
  step: 'finished' | 'not_started'
  setup_at?: Date
}

export type InitValidateStatusResponse = {
  status: 'finished' | 'not_started'
}

export type Member = Pick<GetAccountProfileResponse, 'id' | 'name' | 'email' | 'avatar_url'> & {
  avatar: string
  last_login_at?: string
  last_active_at?: string
  created_at?: string
  status: 'pending' | 'active' | 'banned' | 'closed'
  role: 'owner' | 'admin' | 'editor' | 'normal' | 'dataset_operator'
  roles: Role[]
}

const ProviderName = {
  OPENAI: 'openai',
  AZURE_OPENAI: 'azure_openai',
  ANTHROPIC: 'anthropic',
  Replicate: 'replicate',
  HuggingfaceHub: 'huggingface_hub',
  MiniMax: 'minimax',
  Spark: 'spark',
  Tongyi: 'tongyi',
  ChatGLM: 'chatglm',
} as const
type ProviderName = (typeof ProviderName)[keyof typeof ProviderName]
type ProviderAzureToken = {
  openai_api_base?: string
  openai_api_key?: string
}
type ProviderAnthropicToken = {
  anthropic_api_key?: string
}
type Provider = {
  [Name in ProviderName]: {
    provider_name: Name
  } & {
    provider_type: 'custom' | 'system'
    is_valid: boolean
    is_enabled: boolean
    last_used: string
    token?: string | ProviderAzureToken | ProviderAnthropicToken
  }
}[ProviderName]

export type IWorkspace = {
  id: string
  name: string
  plan: string
  status: string
  created_at: number
  last_opened_at?: number | null
  current: boolean
}

export type ICurrentWorkspace = Omit<IWorkspace, 'current'> & {
  role: 'owner' | 'admin' | 'editor' | 'dataset_operator' | 'normal'
  is_super_admin?: boolean
  management_mode?: 'local_managed' | 'external_managed'
  allow_local_member_override?: boolean
  capabilities?: string[]
  providers: Provider[]
  trial_credits: number
  trial_credits_used: number
  trial_credits_exhausted_at: number
  next_credit_reset_date: number
  trial_end_reason?: string
  custom_config?: {
    remove_webapp_brand?: boolean
    replace_webapp_logo?: string
  }
}

export type LangGeniusVersionResponse = GetVersionResponse & {
  current_version: string
  latest_version: string
  current_env: string
}

export type TenantManagementMode = 'local_managed' | 'external_managed'

export type TenantExternalBinding = {
  external_tenant_id: string
  source_version: number
  last_synced_at: number | null
}

export type TenantManagementInfo = {
  tenant_id: string
  management_mode: TenantManagementMode
  allow_local_member_override: boolean
  has_external_binding: boolean
  external_tenant_binding: TenantExternalBinding | null
}

export type TenantAdminTenant = {
  id: string
  name: string
  status: string
  created_at: number | null
  is_default_tenant: boolean
  member_count: number
  management_mode: TenantManagementMode
  allow_local_member_override: boolean
  external_tenant_id: string | null
}

export type TenantAdminTenantsResponse = {
  tenants: TenantAdminTenant[]
}

export type TenantAdminCreateTenantPayload = {
  name: string
  management_mode: TenantManagementMode
  allow_local_member_override: boolean
  external_tenant_id?: string
}

export type TenantAdminCreateTenantResponse = CommonResponse & {
  tenant: TenantAdminTenant
}

export type TenantManagementUpdatePayload = {
  management_mode: TenantManagementMode
  allow_local_member_override: boolean
  external_tenant_id?: string
}

export type TenantManagementUpdateResponse = CommonResponse & {
  tenant_management: TenantManagementInfo
}

export type TenantManagementSyncResponse = CommonResponse & {
  resolve: {
    tenant_id: string
    account_id: string
    external_tenant_id: string
    external_user_id: string
    management_mode: TenantManagementMode
    allow_local_member_override: boolean
    membership_active: boolean
    display_role: 'owner' | 'admin' | 'editor' | 'dataset_operator' | 'normal' | null
    capabilities: string[]
    projection_source_version: number | null
    projection_expires_at: string | null
  }
}

export type ExternalAppAuthMode =
  | 'none'
  | 'static_bearer'
  | 'oauth2_client_credentials'
  | 'oauth2_authorization_code'
  | 'custom'

export type ExternalAppCallMode = 'gateway' | 'direct'

export type ExternalAppApiSource = 'manual' | 'openapi_import'

export type ExternalApp = {
  id: string
  tenant_id: string
  name: string
  description: string | null
  app_purpose: string | null
  call_mode: ExternalAppCallMode
  auth_mode: ExternalAppAuthMode
  auth_config: Record<string, unknown>
  is_enabled: boolean
  created_at: number | null
  updated_at: number | null
  api_count?: number
}

export type ExternalAppPagination = {
  page: number
  page_size: number
  total: number
  has_more: boolean
}

export type ExternalAppListQuery = {
  page?: number
  page_size?: number
  query?: string
}

export type ExternalAppListResponse = {
  apps: ExternalApp[]
  pagination: ExternalAppPagination
}

export type ExternalAppCreatePayload = {
  name: string
  description?: string
  app_purpose?: string
  call_mode: ExternalAppCallMode
  auth_mode: ExternalAppAuthMode
  auth_config: Record<string, unknown>
  is_enabled: boolean
}

export type ExternalAppUpdatePayload = {
  name?: string
  description?: string
  app_purpose?: string
  call_mode?: ExternalAppCallMode
  auth_mode?: ExternalAppAuthMode
  auth_config?: Record<string, unknown>
  is_enabled?: boolean
}

export type ExternalAppCreateResponse = CommonResponse & {
  app: ExternalApp
}

export type ExternalAppUpdateResponse = CommonResponse & {
  app: ExternalApp
}

export type ExternalAppApi = {
  id: string
  tenant_id: string
  app_id: string
  name: string
  http_method: string
  path: string
  summary: string | null
  description: string | null
  api_purpose: string | null
  source: ExternalAppApiSource
  source_version: number
  required_permissions: string[]
  request_schema: Record<string, unknown>
  response_schema: Record<string, unknown>
  is_confirmed: boolean
  is_enabled: boolean
  imported_at: number | null
  created_at: number | null
  updated_at: number | null
}

export type ExternalAppApiListResponse = {
  apis: ExternalAppApi[]
  pagination: ExternalAppPagination
}

export type ExternalAppApiCreatePayload = {
  name: string
  http_method: string
  path: string
  summary?: string
  description?: string
  api_purpose?: string
  required_permissions: string[]
  request_schema: Record<string, unknown>
  response_schema: Record<string, unknown>
  is_confirmed: boolean
  is_enabled: boolean
}

export type ExternalAppApiUpdatePayload = {
  name?: string
  http_method?: string
  path?: string
  summary?: string
  description?: string
  api_purpose?: string
  required_permissions?: string[]
  request_schema?: Record<string, unknown>
  response_schema?: Record<string, unknown>
  is_confirmed?: boolean
  is_enabled?: boolean
}

export type ExternalAppApiCreateResponse = CommonResponse & {
  api: ExternalAppApi
}

export type ExternalAppApiUpdateResponse = CommonResponse & {
  api: ExternalAppApi
}

export type ExternalAppOpenAPIImportPayload = {
  spec: Record<string, unknown> | string
  overwrite_existing?: boolean
  import_as_unconfirmed?: boolean
  source_version?: number
}

export type ExternalAppOpenAPIImportResponse = CommonResponse & {
  summary: {
    created: number
    updated: number
    skipped: number
    source_version: number
  }
}

export type ExternalAppRuntimePermissionLevel = 'user_scoped' | 'tenant_scoped' | 'app_scoped' | 'unverified'

export type ExternalAppRuntimeApiItem = {
  app_id: string
  app_name: string
  api_id: string
  api_name: string
  http_method: string
  path: string
  summary: string | null
  description: string | null
  api_purpose: string | null
  required_permissions: string[]
  allowed: boolean
  permission_level: ExternalAppRuntimePermissionLevel
  call_mode: ExternalAppCallMode
  routing_score: number
  routing_reason: string[]
  warnings: string[]
}

export type ExternalAppRuntimeAvailableApisPayload = {
  query?: string
  context_token?: string
  max_results?: number
}

export type ExternalAppRuntimeAvailableApisResponse = {
  apis: ExternalAppRuntimeApiItem[]
  summary: {
    total: number
    token_verified: boolean
  }
}

export type ExternalAppRuntimeInvokePayload = {
  app_id: string
  api_id: string
  context_token?: string
  params?: Record<string, unknown>
  dry_run?: boolean
  timeout_seconds?: number
}

export type ExternalAppRuntimeInvokeResponse = CommonResponse & {
  trace_id: string
  permission_level_actual: ExternalAppRuntimePermissionLevel
  call_mode_actual: ExternalAppCallMode
  warnings: string[]
  dry_run?: boolean
  target?: {
    app_id: string
    app_name: string
    api_id: string
    api_name: string
    method: string
    url: string
  }
  status_code?: number
  data?: unknown
}

export type ExternalAppGovernanceRiskReason =
  | 'direct_call_mode'
  | 'required_permissions_present'
  | 'write_operation'
  | 'api_not_confirmed'

export type ExternalAppGovernanceRiskRecommendation = {
  app_id: string
  app_name: string
  api_id: string
  api_name: string
  http_method: string
  path: string
  risk_reasons: ExternalAppGovernanceRiskReason[]
  recommended_call_mode: ExternalAppCallMode
}

export type ExternalAppGovernanceRiskReportResponse = {
  summary: {
    total_apps: number
    total_apis: number
    direct_mode_apps: number
    high_risk_api_candidates: number
    gateway_only_recommendations: number
  }
  gateway_only_recommendations: ExternalAppGovernanceRiskRecommendation[]
}

export type ExternalAppGovernanceCredentialAlertLevel = 'expired' | 'critical' | 'warning' | 'info'

export type ExternalAppGovernanceCredentialAlert = {
  app_id: string
  app_name: string
  auth_mode: string
  credential_expires_at: number
  remaining_seconds: number
  alert_level: ExternalAppGovernanceCredentialAlertLevel
}

export type ExternalAppGovernanceCredentialAlertsResponse = {
  summary: {
    within_hours: number
    total_alerts: number
  }
  alerts: ExternalAppGovernanceCredentialAlert[]
}

export type DataSourceNotionPage = {
  page_icon: null | {
    type: string | null
    url: string | null
    emoji: string | null
  }
  page_id: string
  page_name: string
  parent_id: string
  type: string
  is_bound: boolean
}

export type NotionPage = DataSourceNotionPage & {
  workspace_id: string
}

export type DataSourceNotionPageMap = Record<
  string,
  DataSourceNotionPage & { workspace_id: string }
>

export type DataSourceNotionWorkspace = {
  workspace_name: string
  workspace_id: string
  workspace_icon: string | null
  total?: number
  pages: DataSourceNotionPage[]
}

export const DataSourceProvider = {
  fireCrawl: 'firecrawl',
  jinaReader: 'jinareader',
  waterCrawl: 'watercrawl',
} as const
export type DataSourceProvider = (typeof DataSourceProvider)[keyof typeof DataSourceProvider]

export type FileUploadConfigResponse = {
  batch_count_limit: number
  image_file_size_limit?: number | string // default is 10MB
  image_file_batch_limit: number // default is 10, for dataset attachment upload only
  single_chunk_attachment_limit: number // default is 10, for dataset attachment upload only
  attachment_image_file_size_limit: number // default is 2MB, for dataset attachment upload only
  file_size_limit: number // default is 15MB
  audio_file_size_limit?: number // default is 50MB
  video_file_size_limit?: number // default is 100MB
  workflow_file_upload_limit?: number // default is 10
  file_upload_limit: number // default is 5
}

export type CodeBasedExtensionForm = {
  type: string
  label: I18nText
  variable: string
  required: boolean
  options: { label: I18nText; value: string }[]
  default: string
  placeholder: string
  max_length?: number
}

export type CodeBasedExtensionItem = {
  name: string
  label: I18nText
  form_schema: CodeBasedExtensionForm[]
}
export type CodeBasedExtension = {
  module: string
  data: CodeBasedExtensionItem[]
}

export type ExternalDataTool = {
  type?: string
  label?: string
  icon?: string
  icon_background?: string
  variable?: string
  enabled?: boolean
  config?: {
    api_based_extension_id?: string
  } & Partial<Record<string, string | undefined>>
}

export type StructuredOutputRulesRequestBody = {
  instruction: string
  model_config: Model
}

export type StructuredOutputRulesResponse = {
  output: string
  error?: string
}
