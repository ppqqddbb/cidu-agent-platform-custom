import { useMutation, useQuery } from '@tanstack/react-query'
import { del, get, post } from './base'
import { useInvalid } from './use-base'

export const downloadWorkspaceFile = async (fileId: string): Promise<Blob> => {
  const response = await get<Response>(`/workspaces/current/files/${fileId}`, {}, {
    needAllResponseContent: true,
    silent: true,
  })
  if (!(response instanceof Response))
    throw new Error('Invalid response')
  if (!response.ok) {
    let message = `Download failed: ${response.status}`
    try {
      const errorData = await response.clone().json() as { message?: string }
      if (errorData.message)
        message = errorData.message
    }
    catch {
      // ignore non-json error bodies
    }
    throw new Error(message)
  }
  return response.blob()
}

const NAME_SPACE = 'workspace-files'

export type WorkspaceFile = {
  id: string
  name: string
  size: number
  mime_type: string
  created_at: number
  created_by: string
  file_type: 'formal' | 'temporary'
}

export type WorkspaceFilesResponse = {
  data: WorkspaceFile[]
  total: number
  has_more: boolean
}

export type WorkspaceFilesParams = {
  page: number
  limit: number
  keyword?: string
  file_type?: 'formal' | 'temporary'
}

export const useWorkspaceFiles = (
  params: WorkspaceFilesParams,
  enabled: boolean = true,
) => {
  return useQuery({
    queryKey: [NAME_SPACE, 'list', params],
    queryFn: () => get<WorkspaceFilesResponse>('/workspaces/current/files', {
      params: {
        page: params.page,
        limit: params.limit,
        keyword: params.keyword,
        file_type: params.file_type,
      },
    }),
    retry: 0,
    enabled,
  })
}

export const useInvalidWorkspaceFiles = () => {
  return useInvalid([NAME_SPACE, 'list'])
}

export const useUploadWorkspaceFile = () => {
  return useMutation({
    mutationKey: [NAME_SPACE, 'upload'],
    mutationFn: async (formData: FormData) => {
      return post<WorkspaceFile>('/workspaces/current/files', {
        body: formData,
      }, {
        bodyStringify: false,
        deleteContentType: true,
      })
    },
  })
}

export const useDeleteWorkspaceFile = () => {
  return useMutation({
    mutationKey: [NAME_SPACE, 'delete'],
    mutationFn: (fileId: string) => del(`/workspaces/current/files/${fileId}`),
  })
}

export type BatchDeleteResponse = {
  deleted_count: number
  failed_ids: string[]
}

export const useBatchDeleteWorkspaceFiles = () => {
  return useMutation({
    mutationKey: [NAME_SPACE, 'batch-delete'],
    mutationFn: (fileIds: string[]) => {
      return post<BatchDeleteResponse>('/workspaces/current/files/batch-delete', {
        body: { file_ids: fileIds },
      })
    },
  })
}
