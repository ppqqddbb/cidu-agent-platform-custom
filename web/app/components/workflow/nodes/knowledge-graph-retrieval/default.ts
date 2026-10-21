import type { TFunction } from 'i18next'
import type { NodeDefault } from '../../types'
import type { KnowledgeGraphRetrievalNodeType } from './types'
import { BlockEnum } from '@/app/components/workflow/types'
import { genNodeMetaData } from '@/app/components/workflow/utils'

const metaData = genNodeMetaData({
  sort: 3,
  type: BlockEnum.KnowledgeGraphRetrieval,
})

const nodeDefault: NodeDefault<KnowledgeGraphRetrievalNodeType> = {
  metaData,
  defaultValue: {
    query_variable_selector: [],
    graph_ids: [],
    top_k: 5,
    retrieval_config: {
      strategy: 'node',
      target_node_types: ['ProductModel'],
      match_mode: 'any',
      include_paths: true,
      path_depth: 8,
      include_parameters: true,
      parameter_relation_types: ['DEFINES_PARAMETER'],
      deduplicate: true,
    },
  },
  checkValid(payload: KnowledgeGraphRetrievalNodeType, t: TFunction) {
    const legacyT = t as unknown as (key: string, options?: Record<string, unknown>) => string
    let errorMessages = ''

    if (!errorMessages && (!payload.query_variable_selector || payload.query_variable_selector.length === 0))
      errorMessages = legacyT('errorMsg.fieldRequired', { ns: 'workflow', field: legacyT('nodes.knowledgeGraphRetrieval.queryText', { ns: 'workflow' }) })

    if (!errorMessages && (!payload.graph_ids || payload.graph_ids.length === 0))
      errorMessages = legacyT('errorMsg.fieldRequired', { ns: 'workflow', field: legacyT('nodes.knowledgeGraphRetrieval.knowledgeGraph', { ns: 'workflow' }) })

    return {
      isValid: !errorMessages,
      errorMessage: errorMessages,
    }
  },
}

export default nodeDefault
