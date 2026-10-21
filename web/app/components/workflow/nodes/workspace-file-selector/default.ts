import type { NodeDefault } from '../../types'
import type { WorkspaceFileSelectorNodeType } from './types'
import { BlockClassification } from '@/app/components/workflow/block-selector/types'
import { WORKSPACE_FILE_SELECTOR_OUTPUT_STRUCT } from '@/app/components/workflow/constants'
import { BlockEnum } from '@/app/components/workflow/types'
import { genNodeMetaData } from '@/app/components/workflow/utils'

const i18nPrefix = 'errorMsg'

const metaData = genNodeMetaData({
  classification: BlockClassification.Transform,
  sort: 3.9,
  type: BlockEnum.WorkspaceFileSelector,
})

const nodeDefault: NodeDefault<WorkspaceFileSelectorNodeType> = {
  metaData,
  defaultValue: {
    file_id: '',
    selected_file: undefined,
  },
  checkValid(payload, t) {
    const legacyT = t as unknown as (key: string, options?: Record<string, unknown>) => string
    let errorMessage = ''
    if (!payload.file_id)
      errorMessage = legacyT(`${i18nPrefix}.fieldRequired`, { ns: 'workflow', field: legacyT('nodes.workspaceFileSelector.file', { ns: 'workflow' }) })

    return {
      isValid: !errorMessage,
      errorMessage,
    }
  },
  getOutputVars() {
    return WORKSPACE_FILE_SELECTOR_OUTPUT_STRUCT
  },
}

export default nodeDefault
