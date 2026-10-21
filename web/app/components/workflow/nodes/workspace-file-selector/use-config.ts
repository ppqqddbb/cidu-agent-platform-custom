import type { WorkspaceFileSelectorNodeType } from './types'
import type { WorkspaceFile } from '@/service/use-workspace-files'
import { produce } from 'immer'
import { useCallback } from 'react'
import { useNodesReadOnly } from '@/app/components/workflow/hooks'
import useNodeCrud from '@/app/components/workflow/nodes/_base/hooks/use-node-crud'

const toSelectedFile = (file: WorkspaceFile) => ({
  id: file.id,
  name: file.name,
  size: file.size,
  mime_type: file.mime_type,
  created_at: file.created_at,
})

export const useConfig = (id: string, payload: WorkspaceFileSelectorNodeType) => {
  const { nodesReadOnly: readOnly } = useNodesReadOnly()
  const { inputs, setInputs } = useNodeCrud<WorkspaceFileSelectorNodeType>(id, payload)

  const handleFileSelect = useCallback((file: WorkspaceFile) => {
    if (readOnly)
      return

    const nextInputs = produce(inputs, (draft) => {
      draft.file_id = file.id
      draft.selected_file = toSelectedFile(file)
    })
    setInputs(nextInputs)
  }, [inputs, readOnly, setInputs])

  const handleClear = useCallback(() => {
    if (readOnly)
      return

    const nextInputs = produce(inputs, (draft) => {
      draft.file_id = ''
      draft.selected_file = undefined
    })
    setInputs(nextInputs)
  }, [inputs, readOnly, setInputs])

  return {
    readOnly,
    inputs,
    handleFileSelect,
    handleClear,
  }
}

export default useConfig
