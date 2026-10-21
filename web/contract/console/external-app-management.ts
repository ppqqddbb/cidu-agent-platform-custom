import type {
  CommonResponse,
  ExternalAppApiCreatePayload,
  ExternalAppApiCreateResponse,
  ExternalAppApiListResponse,
  ExternalAppApiUpdatePayload,
  ExternalAppApiUpdateResponse,
  ExternalAppCreatePayload,
  ExternalAppCreateResponse,
  ExternalAppGovernanceCredentialAlertsResponse,
  ExternalAppGovernanceRiskReportResponse,
  ExternalAppListQuery,
  ExternalAppListResponse,
  ExternalAppOpenAPIImportPayload,
  ExternalAppOpenAPIImportResponse,
  ExternalAppRuntimeAvailableApisPayload,
  ExternalAppRuntimeAvailableApisResponse,
  ExternalAppRuntimeInvokePayload,
  ExternalAppRuntimeInvokeResponse,
  ExternalAppUpdatePayload,
  ExternalAppUpdateResponse,
} from '@/models/common'
import { type } from '@orpc/contract'
import { base } from '../base'

export const externalAppListContract = base
  .route({
    path: '/workspaces/current/external-apps',
    method: 'GET',
  })
  .input(type<{ query?: ExternalAppListQuery }>())
  .output(type<ExternalAppListResponse>())

export const externalAppCreateContract = base
  .route({
    path: '/workspaces/current/external-apps',
    method: 'POST',
  })
  .input(type<{
    body: ExternalAppCreatePayload
  }>())
  .output(type<ExternalAppCreateResponse>())

export const externalAppUpdateContract = base
  .route({
    path: '/workspaces/current/external-apps/{appId}',
    method: 'PUT',
  })
  .input(type<{
    params: {
      appId: string
    }
    body: ExternalAppUpdatePayload
  }>())
  .output(type<ExternalAppUpdateResponse>())

export const externalAppDeleteContract = base
  .route({
    path: '/workspaces/current/external-apps/{appId}',
    method: 'DELETE',
  })
  .input(type<{
    params: {
      appId: string
    }
  }>())
  .output(type<CommonResponse>())

export const externalAppApiListContract = base
  .route({
    path: '/workspaces/current/external-apps/{appId}/apis',
    method: 'GET',
  })
  .input(type<{
    params: {
      appId: string
    }
    query?: ExternalAppListQuery
  }>())
  .output(type<ExternalAppApiListResponse>())

export const externalAppApiCreateContract = base
  .route({
    path: '/workspaces/current/external-apps/{appId}/apis',
    method: 'POST',
  })
  .input(type<{
    params: {
      appId: string
    }
    body: ExternalAppApiCreatePayload
  }>())
  .output(type<ExternalAppApiCreateResponse>())

export const externalAppApiUpdateContract = base
  .route({
    path: '/workspaces/current/external-apps/{appId}/apis/{apiId}',
    method: 'PUT',
  })
  .input(type<{
    params: {
      appId: string
      apiId: string
    }
    body: ExternalAppApiUpdatePayload
  }>())
  .output(type<ExternalAppApiUpdateResponse>())

export const externalAppApiDeleteContract = base
  .route({
    path: '/workspaces/current/external-apps/{appId}/apis/{apiId}',
    method: 'DELETE',
  })
  .input(type<{
    params: {
      appId: string
      apiId: string
    }
  }>())
  .output(type<CommonResponse>())

export const externalAppOpenAPIImportContract = base
  .route({
    path: '/workspaces/current/external-apps/{appId}/openapi/import',
    method: 'POST',
  })
  .input(type<{
    params: {
      appId: string
    }
    body: ExternalAppOpenAPIImportPayload
  }>())
  .output(type<ExternalAppOpenAPIImportResponse>())

export const externalAppRuntimeAvailableApisContract = base
  .route({
    path: '/workspaces/current/external-apps/runtime/available-apis',
    method: 'POST',
  })
  .input(type<{
    body: ExternalAppRuntimeAvailableApisPayload
  }>())
  .output(type<ExternalAppRuntimeAvailableApisResponse>())

export const externalAppGovernanceRiskReportContract = base
  .route({
    path: '/workspaces/current/external-apps/governance/risk-report',
    method: 'GET',
  })
  .input(type<{}>())
  .output(type<ExternalAppGovernanceRiskReportResponse>())

export const externalAppGovernanceCredentialAlertsContract = base
  .route({
    path: '/workspaces/current/external-apps/governance/credential-alerts',
    method: 'GET',
  })
  .input(type<{
    query?: {
      within_hours?: number
    }
  }>())
  .output(type<ExternalAppGovernanceCredentialAlertsResponse>())

export const externalAppRuntimeInvokeContract = base
  .route({
    path: '/workspaces/current/external-apps/runtime/invoke',
    method: 'POST',
  })
  .input(type<{
    body: ExternalAppRuntimeInvokePayload
  }>())
  .output(type<ExternalAppRuntimeInvokeResponse>())
