import type {
  ExternalAppListQuery,
  ExternalAppApiCreatePayload,
  ExternalAppApiCreateResponse,
  ExternalAppApiUpdatePayload,
  ExternalAppApiUpdateResponse,
  ExternalAppCreatePayload,
  ExternalAppCreateResponse,
  ExternalAppOpenAPIImportPayload,
  ExternalAppOpenAPIImportResponse,
  ExternalAppRuntimeAvailableApisPayload,
  ExternalAppRuntimeAvailableApisResponse,
  ExternalAppRuntimeInvokePayload,
  ExternalAppRuntimeInvokeResponse,
  ExternalAppUpdatePayload,
  ExternalAppUpdateResponse,
} from '@/models/common'
import { skipToken, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { consoleClient, consoleQuery } from './client'

type UpdateExternalAppInput = {
  appId: string
  body: ExternalAppUpdatePayload
}

type DeleteExternalAppInput = {
  appId: string
}

type CreateExternalAppApiInput = {
  appId: string
  body: ExternalAppApiCreatePayload
}

type UpdateExternalAppApiInput = {
  appId: string
  apiId: string
  body: ExternalAppApiUpdatePayload
}

type DeleteExternalAppApiInput = {
  appId: string
  apiId: string
}

type ImportExternalAppOpenAPIInput = {
  appId: string
  body: ExternalAppOpenAPIImportPayload
}

export const useExternalApps = (query?: ExternalAppListQuery, enabled = true) => {
  return useQuery(consoleQuery.externalAppManagement.listApps.queryOptions({
    input: { query },
    enabled,
  }))
}

export const useExternalAppApis = (appId?: string, query?: ExternalAppListQuery, enabled = true) => {
  return useQuery(consoleQuery.externalAppManagement.listApis.queryOptions({
    input: appId
      ? {
          params: { appId },
          query,
        }
      : skipToken,
    enabled,
  }))
}

export const useCreateExternalApp = () => {
  const queryClient = useQueryClient()
  return useMutation<ExternalAppCreateResponse, Error, ExternalAppCreatePayload>({
    mutationKey: consoleQuery.externalAppManagement.createApp.mutationKey(),
    mutationFn: body => consoleClient.externalAppManagement.createApp({ body }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: consoleQuery.externalAppManagement.listApps.key(),
      })
    },
  })
}

export const useUpdateExternalApp = () => {
  const queryClient = useQueryClient()
  return useMutation<ExternalAppUpdateResponse, Error, UpdateExternalAppInput>({
    mutationKey: consoleQuery.externalAppManagement.updateApp.mutationKey(),
    mutationFn: ({ appId, body }) =>
      consoleClient.externalAppManagement.updateApp({
        params: { appId },
        body,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: consoleQuery.externalAppManagement.listApps.key(),
      })
    },
  })
}

export const useDeleteExternalApp = () => {
  const queryClient = useQueryClient()
  return useMutation<void, Error, DeleteExternalAppInput>({
    mutationKey: consoleQuery.externalAppManagement.deleteApp.mutationKey(),
    mutationFn: async ({ appId }) => {
      await consoleClient.externalAppManagement.deleteApp({
        params: { appId },
      })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: consoleQuery.externalAppManagement.listApps.key(),
      })
    },
  })
}

export const useCreateExternalAppApi = () => {
  const queryClient = useQueryClient()
  return useMutation<ExternalAppApiCreateResponse, Error, CreateExternalAppApiInput>({
    mutationKey: consoleQuery.externalAppManagement.createApi.mutationKey(),
    mutationFn: ({ appId, body }) =>
      consoleClient.externalAppManagement.createApi({
        params: { appId },
        body,
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: consoleQuery.externalAppManagement.listApps.key(),
        }),
        queryClient.invalidateQueries({
          queryKey: consoleQuery.externalAppManagement.listApis.key(),
        }),
      ])
    },
  })
}

export const useUpdateExternalAppApi = () => {
  const queryClient = useQueryClient()
  return useMutation<ExternalAppApiUpdateResponse, Error, UpdateExternalAppApiInput>({
    mutationKey: consoleQuery.externalAppManagement.updateApi.mutationKey(),
    mutationFn: ({ appId, apiId, body }) =>
      consoleClient.externalAppManagement.updateApi({
        params: { appId, apiId },
        body,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: consoleQuery.externalAppManagement.listApis.key(),
      })
    },
  })
}

export const useDeleteExternalAppApi = () => {
  const queryClient = useQueryClient()
  return useMutation<void, Error, DeleteExternalAppApiInput>({
    mutationKey: consoleQuery.externalAppManagement.deleteApi.mutationKey(),
    mutationFn: async ({ appId, apiId }) => {
      await consoleClient.externalAppManagement.deleteApi({
        params: { appId, apiId },
      })
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: consoleQuery.externalAppManagement.listApps.key(),
        }),
        queryClient.invalidateQueries({
          queryKey: consoleQuery.externalAppManagement.listApis.key(),
        }),
      ])
    },
  })
}

export const useImportExternalAppOpenAPI = () => {
  const queryClient = useQueryClient()
  return useMutation<ExternalAppOpenAPIImportResponse, Error, ImportExternalAppOpenAPIInput>({
    mutationKey: consoleQuery.externalAppManagement.importOpenAPI.mutationKey(),
    mutationFn: ({ appId, body }) =>
      consoleClient.externalAppManagement.importOpenAPI({
        params: { appId },
        body,
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: consoleQuery.externalAppManagement.listApps.key(),
        }),
        queryClient.invalidateQueries({
          queryKey: consoleQuery.externalAppManagement.listApis.key(),
        }),
      ])
    },
  })
}

export const useListExternalAppRuntimeAvailableApis = () => {
  return useMutation<ExternalAppRuntimeAvailableApisResponse, Error, ExternalAppRuntimeAvailableApisPayload>({
    mutationKey: consoleQuery.externalAppManagement.listAvailableRuntimeApis.mutationKey(),
    mutationFn: body => consoleClient.externalAppManagement.listAvailableRuntimeApis({ body }),
  })
}

export const useExternalAppGovernanceRiskReport = (enabled = true) => {
  return useQuery(consoleQuery.externalAppManagement.governanceRiskReport.queryOptions({
    input: {},
    enabled,
  }))
}

export const useExternalAppGovernanceCredentialAlerts = (withinHours?: number, enabled = true) => {
  return useQuery(consoleQuery.externalAppManagement.governanceCredentialAlerts.queryOptions({
    input: {
      query: withinHours
        ? {
            within_hours: withinHours,
          }
        : undefined,
    },
    enabled,
  }))
}

export const useInvokeExternalAppRuntimeApi = () => {
  return useMutation<ExternalAppRuntimeInvokeResponse, Error, ExternalAppRuntimeInvokePayload>({
    mutationKey: consoleQuery.externalAppManagement.invokeRuntimeApi.mutationKey(),
    mutationFn: body => consoleClient.externalAppManagement.invokeRuntimeApi({ body }),
  })
}
