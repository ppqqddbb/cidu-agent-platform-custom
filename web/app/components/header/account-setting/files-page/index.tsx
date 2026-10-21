'use client'

import type { ChangeEvent } from 'react'
import { Button } from '@langgenius/dify-ui/button'
import { Checkbox } from '@langgenius/dify-ui/checkbox'
import { cn } from '@langgenius/dify-ui/cn'
import { toast } from '@langgenius/dify-ui/toast'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import FileTypeIcon from '@/app/components/base/file-uploader/file-type-icon'
import { getFileAppearanceType } from '@/app/components/base/file-uploader/utils'
import { SearchInput } from '@/app/components/base/search-input'
import { useAppContext } from '@/context/app-context'
import {
  downloadWorkspaceFile,
  useBatchDeleteWorkspaceFiles,
  useDeleteWorkspaceFile,
  useUploadWorkspaceFile,
  useWorkspaceFiles,
} from '@/service/use-workspace-files'
import { downloadBlob } from '@/utils/download'
import { formatFileSize } from '@/utils/format'

const PAGE_SIZE = 20
const QUERY_KEY = ['workspace-files', 'list']

const formatTimestamp = (timestamp: number | null | undefined): string => {
  if (!timestamp)
    return '-'
  return new Date(timestamp * 1000).toLocaleString()
}

const FilesPage = () => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const {
    currentWorkspace,
    hasCurrentWorkspaceCapability,
    isCurrentWorkspaceDatasetOperator,
    isCurrentWorkspaceEditor,
    isCurrentWorkspaceManager,
    isCurrentWorkspaceOwner,
    isCurrentWorkspaceSuperAdmin,
  } = useAppContext()
  const hasFileManageCapability = hasCurrentWorkspaceCapability?.('workspace.file.manage') ?? false
  const canManageFilesByRole = isCurrentWorkspaceSuperAdmin === true
    || isCurrentWorkspaceOwner
    || isCurrentWorkspaceManager
    || isCurrentWorkspaceEditor
    || currentWorkspace.role === 'normal'
  const canManageFiles = !isCurrentWorkspaceDatasetOperator && (hasFileManageCapability || canManageFilesByRole)
  const queryClient = useQueryClient()

  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [selectedFileIds, setSelectedFileIds] = useState<Set<string>>(() => new Set())
  const [fileTypeFilter, setFileTypeFilter] = useState<'all' | 'formal' | 'temporary'>('all')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data, isPending } = useWorkspaceFiles(
    { page, limit: PAGE_SIZE, keyword: searchKeyword || undefined, file_type: fileTypeFilter === 'all' ? undefined : fileTypeFilter },
    canManageFiles,
  )
  const deleteMutation = useDeleteWorkspaceFile()
  const uploadMutation = useUploadWorkspaceFile()
  const batchDeleteMutation = useBatchDeleteWorkspaceFiles()

  const files = data?.data ?? []
  const total = data?.total ?? 0
  const hasMore = data?.has_more ?? false
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const handleSearch = useCallback(() => {
    setPage(1)
    setSelectedFileIds(new Set())
    setSearchKeyword(keyword.trim())
  }, [keyword])

  const handleUploadClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file)
      return

    const formData = new FormData()
    formData.append('file', file)
    // Files uploaded from document management page are "formal" files
    formData.append('file_type', 'formal')

    setIsUploading(true)
    try {
      await uploadMutation.mutateAsync(formData)
      toast.success(t('workspaceFiles.uploadSuccess', { ns: 'common' }))
      setPage(1)
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    }
    catch {
      toast.error(t('workspaceFiles.uploadFailed', { ns: 'common' }))
    }
    finally {
      setIsUploading(false)
    }
  }

  const handleDelete = async (fileId: string, fileName: string) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(t('workspaceFiles.deleteConfirm', { ns: 'common', name: fileName })))
      return

    try {
      await deleteMutation.mutateAsync(fileId)
      toast.success(t('actionMsg.modifiedSuccessfully', { ns: 'common' }))
      if (files.length === 1 && page > 1)
        setPage(page - 1)
      setSelectedFileIds((prev) => {
        const next = new Set(prev)
        next.delete(fileId)
        return next
      })
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    }
    catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('actionMsg.modifiedUnsuccessfully', { ns: 'common' })
      toast.error(message)
    }
  }

  const handleBatchDelete = async () => {
    if (selectedFileIds.size === 0)
      return

    // eslint-disable-next-line no-alert
    if (!window.confirm(t('workspaceFiles.batchDeleteConfirm', { ns: 'common', count: selectedFileIds.size })))
      return

    try {
      const result = await batchDeleteMutation.mutateAsync(Array.from(selectedFileIds))
      toast.success(t('workspaceFiles.batchDeleteSuccess', { ns: 'common', count: result.deleted_count }))
      setSelectedFileIds(new Set())
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    }
    catch (error: unknown) {
      const message = error instanceof Error ? error.message : t('actionMsg.modifiedUnsuccessfully', { ns: 'common' })
      toast.error(message)
    }
  }

  const handleDownload = async (fileId: string, fileName: string) => {
    try {
      const blob = await downloadWorkspaceFile(fileId)
      downloadBlob({ data: blob, fileName })
    }
    catch (error) {
      console.error('Download error:', error)
      toast.error(t('workspaceFiles.downloadFailed', { ns: 'common' }))
    }
  }

  const toggleSelectFile = (fileId: string) => {
    setSelectedFileIds((prev) => {
      const next = new Set(prev)
      if (next.has(fileId))
        next.delete(fileId)
      else
        next.add(fileId)
      return next
    })
  }

  const toggleSelectAll = () => {
    const currentPageIds = files.map(file => file.id)
    const selectedCurrentPageIds = currentPageIds.filter(id => selectedFileIds.has(id))
    if (selectedCurrentPageIds.length === currentPageIds.length && currentPageIds.length > 0) {
      setSelectedFileIds((prev) => {
        const next = new Set(prev)
        currentPageIds.forEach(id => next.delete(id))
        return next
      })
    }
    else {
      setSelectedFileIds((prev) => {
        const next = new Set(prev)
        currentPageIds.forEach(id => next.add(id))
        return next
      })
    }
  }

  const handleFileTypeFilterChange = (fileType: 'all' | 'formal' | 'temporary') => {
    setFileTypeFilter(fileType)
    setPage(1)
    setSelectedFileIds(new Set())
  }

  const currentPageSelectedCount = files.filter(file => selectedFileIds.has(file.id)).length
  const isAllSelected = files.length > 0 && currentPageSelectedCount === files.length
  const isSomeSelected = currentPageSelectedCount > 0 && currentPageSelectedCount < files.length

  const handlePageChange = (nextPage: number) => {
    if (nextPage === page)
      return
    setPage(nextPage)
    setSelectedFileIds(new Set())
  }

  if (!canManageFiles) {
    return (
      <div className="rounded-xl border border-divider-subtle bg-background-section p-6 system-sm-regular text-text-secondary">
        {t('workspaceFiles.noPermission', { ns: 'common' })}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="system-sm-regular text-text-secondary">
        {t('workspaceFiles.description', { ns: 'common' })}
      </p>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <SearchInput
            className="w-full max-w-[280px]"
            value={keyword}
            onValueChange={setKeyword}
          />
          <Button variant="secondary" onClick={handleSearch}>
            {t('operation.search', { ns: 'common' })}
          </Button>
          <select
            className="rounded-lg border border-divider-subtle bg-background-section px-3 py-1.5 system-sm-regular text-text-secondary"
            value={fileTypeFilter}
            onChange={e => handleFileTypeFilterChange(e.target.value as 'all' | 'formal' | 'temporary')}
          >
            <option value="all">{t('workspaceFiles.allTypes', { ns: 'common' })}</option>
            <option value="formal">{t('workspaceFiles.formalFile', { ns: 'common' })}</option>
            <option value="temporary">{t('workspaceFiles.temporaryFile', { ns: 'common' })}</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          {selectedFileIds.size > 0 && (
            <>
              <span className="system-sm-regular text-text-secondary">
                {t('workspaceFiles.selectedCount', { ns: 'common', count: selectedFileIds.size })}
              </span>
              <Button
                variant="ghost"
                size="small"
                className="text-text-destructive"
                disabled={batchDeleteMutation.isPending}
                onClick={handleBatchDelete}
              >
                {batchDeleteMutation.isPending
                  ? t('workspaceFiles.deleting', { ns: 'common' })
                  : t('workspaceFiles.batchDelete', { ns: 'common' })}
              </Button>
            </>
          )}
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleFileChange}
          />
          <Button onClick={handleUploadClick} disabled={isUploading}>
            {isUploading ? t('workspaceFiles.uploading', { ns: 'common' }) : t('workspaceFiles.upload', { ns: 'common' })}
          </Button>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-divider-subtle">
        <table className="w-full min-w-[720px] border-collapse">
          <thead className="bg-background-section-burn">
            <tr>
              <th className="w-10 px-4 py-3">
                <Checkbox
                  checked={isAllSelected}
                  indeterminate={isSomeSelected}
                  onCheckedChange={toggleSelectAll}
                />
              </th>
              <th className="px-4 py-3 text-left system-xs-medium-uppercase text-text-tertiary">{t('workspaceFiles.tableName', { ns: 'common' })}</th>
              <th className="px-4 py-3 text-left system-xs-medium-uppercase text-text-tertiary">{t('workspaceFiles.tableType', { ns: 'common' })}</th>
              <th className="px-4 py-3 text-left system-xs-medium-uppercase text-text-tertiary">{t('workspaceFiles.tableSize', { ns: 'common' })}</th>
              <th className="px-4 py-3 text-left system-xs-medium-uppercase text-text-tertiary">{t('workspaceFiles.tableCreatedAt', { ns: 'common' })}</th>
              <th className="px-4 py-3 text-right system-xs-medium-uppercase text-text-tertiary">{t('workspaceFiles.tableActions', { ns: 'common' })}</th>
            </tr>
          </thead>
          <tbody>
            {isPending && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center system-sm-regular text-text-tertiary">
                  {t('loading', { ns: 'common' })}
                </td>
              </tr>
            )}
            {!isPending && files.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center system-sm-regular text-text-tertiary">
                  {t('workspaceFiles.empty', { ns: 'common' })}
                </td>
              </tr>
            )}
            {!isPending && files.map(file => (
              <tr key={file.id} className="border-t border-divider-subtle">
                <td className="px-4 py-3">
                  <Checkbox
                    checked={selectedFileIds.has(file.id)}
                    onCheckedChange={() => toggleSelectFile(file.id)}
                  />
                </td>
                <td className="px-4 py-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <FileTypeIcon type={getFileAppearanceType(file.name, file.mime_type || '')} size="md" />
                    <span className="truncate system-sm-medium text-text-primary" title={file.name}>{file.name}</span>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={cn(
                      'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                      file.file_type === 'formal' ? 'bg-blue-50 text-blue-700' : 'bg-orange-50 text-orange-700',
                    )}
                  >
                    {file.file_type === 'formal'
                      ? t('workspaceFiles.formalFile', { ns: 'common' })
                      : t('workspaceFiles.temporaryFile', { ns: 'common' })}
                  </span>
                </td>
                <td className="px-4 py-3 system-sm-regular text-text-secondary">{formatFileSize(file.size)}</td>
                <td className="px-4 py-3 system-sm-regular text-text-secondary">{formatTimestamp(file.created_at)}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      type="button"
                      className="cursor-pointer border-none bg-transparent p-0 system-sm-medium text-text-accent hover:underline"
                      onClick={() => handleDownload(file.id, file.name)}
                    >
                      {t('workspaceFiles.download', { ns: 'common' })}
                    </button>
                    <Button
                      variant="ghost"
                      size="small"
                      className="text-text-destructive"
                      disabled={deleteMutation.isPending}
                      onClick={() => handleDelete(file.id, file.name)}
                    >
                      {t('operation.delete', { ns: 'common' })}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <div className="system-xs-regular text-text-tertiary">
            {t('workspaceFiles.paginationInfo', { ns: 'common', total, page, totalPages })}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="small"
              disabled={page <= 1}
              onClick={() => handlePageChange(page - 1)}
            >
              {t('operation.previousPage', { ns: 'common' })}
            </Button>
            <Button
              variant="secondary"
              size="small"
              disabled={!hasMore}
              onClick={() => handlePageChange(page + 1)}
            >
              {t('operation.nextPage', { ns: 'common' })}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

export default FilesPage
