import type { FC } from 'react'
import type { WorkspaceFileSelectorNodeType } from './types'
import type { NodeProps } from '@/app/components/workflow/types'
import * as React from 'react'
import FileTypeIcon from '@/app/components/base/file-uploader/file-type-icon'
import { getFileAppearanceType } from '@/app/components/base/file-uploader/utils'
import { formatFileSize } from '@/utils/format'

const Node: FC<NodeProps<WorkspaceFileSelectorNodeType>> = ({
  data,
}) => {
  const selectedFile = data.selected_file

  if (!selectedFile)
    return null

  return (
    <div className="relative mb-1 px-3 py-1">
      <div className="flex min-w-0 items-center gap-2 rounded-lg bg-components-input-bg-normal px-2 py-1.5">
        <FileTypeIcon type={getFileAppearanceType(selectedFile.name, selectedFile.mime_type || '')} size="sm" />
        <div className="min-w-0 grow">
          <div className="truncate system-xs-medium text-text-secondary" title={selectedFile.name}>{selectedFile.name}</div>
          <div className="system-2xs-regular text-text-tertiary">{formatFileSize(selectedFile.size)}</div>
        </div>
      </div>
    </div>
  )
}

export default React.memo(Node)
