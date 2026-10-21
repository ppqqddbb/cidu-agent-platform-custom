import type { FC } from 'react'
import type { WorkspaceFileSelectorNodeType } from './types'
import type { NodePanelProps } from '@/app/components/workflow/types'
import { Button } from '@langgenius/dify-ui/button'
import { cn } from '@langgenius/dify-ui/cn'
import * as React from 'react'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import FileTypeIcon from '@/app/components/base/file-uploader/file-type-icon'
import { getFileAppearanceType } from '@/app/components/base/file-uploader/utils'
import { SearchInput } from '@/app/components/base/search-input'
import Field from '@/app/components/workflow/nodes/_base/components/field'
import OutputVars, { VarItem } from '@/app/components/workflow/nodes/_base/components/output-vars'
import Split from '@/app/components/workflow/nodes/_base/components/split'
import { VarType } from '@/app/components/workflow/types'
import { useWorkspaceFiles } from '@/service/use-workspace-files'
import { formatFileSize } from '@/utils/format'
import useConfig from './use-config'

const PAGE_SIZE = 20
const i18nPrefix = 'nodes.workspaceFileSelector'

const formatTimestamp = (timestamp?: number | null) => {
  if (!timestamp)
    return ''
  return new Date(timestamp * 1000).toLocaleString()
}

const Panel: FC<NodePanelProps<WorkspaceFileSelectorNodeType>> = ({
  id,
  data,
}) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const {
    readOnly,
    inputs,
    handleFileSelect,
    handleClear,
  } = useConfig(id, data)

  const { data: filesResponse, isPending, isError } = useWorkspaceFiles({
    page,
    limit: PAGE_SIZE,
    keyword: searchKeyword || undefined,
  })

  const files = filesResponse?.data || []
  const hasMore = filesResponse?.has_more || false
  const selectedFile = inputs.selected_file
  const selectedFileId = inputs.file_id

  const handleSearch = useCallback(() => {
    setPage(1)
    setSearchKeyword(keyword.trim())
  }, [keyword])

  return (
    <div className="mt-2">
      <div className="space-y-4 px-4 pb-4">
        <Field title={t(`${i18nPrefix}.file`, { ns: 'workflow' })} required>
          <>
            <div className="flex items-center gap-2">
              <SearchInput
                className="min-w-0 grow"
                value={keyword}
                onValueChange={setKeyword}
                placeholder={t(`${i18nPrefix}.searchPlaceholder`, { ns: 'workflow' })}
              />
              <Button variant="secondary" onClick={handleSearch}>
                {t('operation.search', { ns: 'common' })}
              </Button>
            </div>
            {selectedFile && (
              <div className="mt-2 flex min-w-0 items-center gap-2 rounded-lg border border-components-option-card-option-selected-border bg-state-accent-hover px-2 py-1.5">
                <FileTypeIcon type={getFileAppearanceType(selectedFile.name, selectedFile.mime_type || '')} size="sm" />
                <div className="min-w-0 grow">
                  <div className="truncate system-xs-medium text-text-secondary" title={selectedFile.name}>{selectedFile.name}</div>
                  <div className="system-2xs-regular text-text-tertiary">
                    {formatFileSize(selectedFile.size)}
                    {selectedFile.created_at ? ` - ${formatTimestamp(selectedFile.created_at)}` : ''}
                  </div>
                </div>
                <Button size="small" variant="ghost" disabled={readOnly} onClick={handleClear}>
                  {t('operation.clear', { ns: 'common' })}
                </Button>
              </div>
            )}
            <div className="mt-2 overflow-hidden rounded-lg border border-divider-subtle bg-background-section">
              <div className="max-h-[320px] overflow-y-auto">
                {isPending && (
                  <div className="px-3 py-8 text-center system-sm-regular text-text-tertiary">
                    {t(`${i18nPrefix}.loading`, { ns: 'workflow' })}
                  </div>
                )}
                {isError && (
                  <div className="px-3 py-8 text-center system-sm-regular text-text-tertiary">
                    {t(`${i18nPrefix}.loadFailed`, { ns: 'workflow' })}
                  </div>
                )}
                {!isPending && !isError && files.length === 0 && (
                  <div className="px-3 py-8 text-center system-sm-regular text-text-tertiary">
                    {t(`${i18nPrefix}.empty`, { ns: 'workflow' })}
                  </div>
                )}
                {!isPending && !isError && files.map((file) => {
                  const selected = selectedFileId === file.id

                  return (
                    <button
                      key={file.id}
                      type="button"
                      className={cn(
                        'flex w-full min-w-0 cursor-pointer items-center gap-2 border-0 border-t border-divider-subtle bg-transparent px-3 py-2 text-left first:border-t-0 hover:bg-state-base-hover',
                        selected && 'bg-state-accent-hover',
                        readOnly && 'cursor-not-allowed opacity-60',
                      )}
                      disabled={readOnly}
                      onClick={() => handleFileSelect(file)}
                    >
                      <FileTypeIcon type={getFileAppearanceType(file.name, file.mime_type || '')} size="md" />
                      <div className="min-w-0 grow">
                        <div className="truncate system-sm-medium text-text-primary" title={file.name}>{file.name}</div>
                        <div className="system-xs-regular text-text-tertiary">
                          {formatFileSize(file.size)}
                          {file.created_at ? ` - ${formatTimestamp(file.created_at)}` : ''}
                        </div>
                      </div>
                      <div className={cn(
                        'shrink-0 rounded-md px-2 py-1 system-xs-medium text-text-tertiary',
                        selected && 'bg-state-accent-active text-text-accent',
                      )}
                      >
                        {selected ? t(`${i18nPrefix}.selected`, { ns: 'workflow' }) : t(`${i18nPrefix}.select`, { ns: 'workflow' })}
                      </div>
                    </button>
                  )
                })}
              </div>
              {(page > 1 || hasMore) && (
                <div className="flex items-center justify-between border-t border-divider-subtle px-3 py-2">
                  <div className="system-xs-regular text-text-tertiary">
                    {t(`${i18nPrefix}.page`, { ns: 'workflow', page })}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="secondary"
                      size="small"
                      disabled={page <= 1}
                      onClick={() => setPage(page - 1)}
                    >
                      {t(`${i18nPrefix}.prev`, { ns: 'workflow' })}
                    </Button>
                    <Button
                      variant="secondary"
                      size="small"
                      disabled={!hasMore}
                      onClick={() => setPage(page + 1)}
                    >
                      {t(`${i18nPrefix}.next`, { ns: 'workflow' })}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </>
        </Field>
      </div>
      <Split />
      <OutputVars>
        <VarItem
          name="file"
          type={VarType.file}
          description={t(`${i18nPrefix}.outputVars.file`, { ns: 'workflow' })}
        />
      </OutputVars>
    </div>
  )
}

export default React.memo(Panel)
