import type {
  TenantAdminCreateTenantPayload,
  TenantAdminCreateTenantResponse,
  TenantManagementSyncResponse,
  TenantManagementUpdatePayload,
  TenantManagementUpdateResponse,
} from '@/models/common'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { consoleClient, consoleQuery } from './client'

export const useTenantManagementInfo = (enabled = true) => {
  return useQuery({
    queryKey: consoleQuery.tenantManagement.info.queryKey({ input: {} }),
    queryFn: () => consoleClient.tenantManagement.info({}),
    enabled,
  })
}

export const useUpdateTenantManagement = () => {
  const queryClient = useQueryClient()
  return useMutation<TenantManagementUpdateResponse, Error, TenantManagementUpdatePayload>({
    mutationKey: consoleQuery.tenantManagement.update.mutationKey(),
    mutationFn: body => consoleClient.tenantManagement.update({ body }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: consoleQuery.tenantManagement.info.queryKey({ input: {} }) }),
        queryClient.invalidateQueries({ queryKey: ['current-workspace'] }),
      ])
    },
  })
}

export const useSyncTenantManagement = () => {
  const queryClient = useQueryClient()
  return useMutation<TenantManagementSyncResponse, Error, void>({
    mutationKey: consoleQuery.tenantManagement.sync.mutationKey(),
    mutationFn: () => consoleClient.tenantManagement.sync({}),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: consoleQuery.tenantManagement.info.queryKey({ input: {} }) }),
        queryClient.invalidateQueries({ queryKey: ['current-workspace'] }),
      ])
    },
  })
}

export const useTenantAdminTenants = (enabled = true) => {
  return useQuery({
    queryKey: consoleQuery.tenantManagement.tenants.queryKey({ input: {} }),
    queryFn: () => consoleClient.tenantManagement.tenants({}),
    enabled,
  })
}

export const useCreateTenantBySuperAdmin = () => {
  const queryClient = useQueryClient()
  return useMutation<TenantAdminCreateTenantResponse, Error, TenantAdminCreateTenantPayload>({
    mutationKey: consoleQuery.tenantManagement.createTenant.mutationKey(),
    mutationFn: body => consoleClient.tenantManagement.createTenant({ body }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: consoleQuery.tenantManagement.tenants.queryKey({ input: {} }) }),
        queryClient.invalidateQueries({ queryKey: ['workspaces'] }),
      ])
    },
  })
}
