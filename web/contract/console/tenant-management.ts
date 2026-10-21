import type {
  TenantAdminCreateTenantPayload,
  TenantAdminCreateTenantResponse,
  TenantAdminTenantsResponse,
  TenantManagementInfo,
  TenantManagementSyncResponse,
  TenantManagementUpdatePayload,
  TenantManagementUpdateResponse,
} from '@/models/common'
import { type } from '@orpc/contract'
import { base } from '../base'

export const tenantManagementInfoContract = base
  .route({
    path: '/workspaces/current/tenant-management',
    method: 'GET',
  })
  .input(type<unknown>())
  .output(type<TenantManagementInfo>())

export const tenantManagementUpdateContract = base
  .route({
    path: '/workspaces/current/tenant-management',
    method: 'POST',
  })
  .input(type<{
    body: TenantManagementUpdatePayload
  }>())
  .output(type<TenantManagementUpdateResponse>())

export const tenantManagementSyncContract = base
  .route({
    path: '/workspaces/current/tenant-management/sync',
    method: 'POST',
  })
  .input(type<unknown>())
  .output(type<TenantManagementSyncResponse>())

export const tenantAdminTenantsContract = base
  .route({
    path: '/workspaces/tenant-management/tenants',
    method: 'GET',
  })
  .input(type<unknown>())
  .output(type<TenantAdminTenantsResponse>())

export const tenantAdminCreateTenantContract = base
  .route({
    path: '/workspaces/tenant-management/tenants',
    method: 'POST',
  })
  .input(type<{
    body: TenantAdminCreateTenantPayload
  }>())
  .output(type<TenantAdminCreateTenantResponse>())
