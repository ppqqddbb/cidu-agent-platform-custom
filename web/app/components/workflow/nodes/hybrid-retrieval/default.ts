import type { TFunction } from 'i18next'
import type { NodeDefault } from '../../types'
import type { HybridRetrievalNodeType } from './types'
import { BlockEnum } from '@/app/components/workflow/types'
import { genNodeMetaData } from '@/app/components/workflow/utils'
import { DATASET_DEFAULT } from '@/config'
import { RETRIEVE_TYPE } from '@/types/app'
import { checkoutRerankModelConfiguredInRetrievalSettings } from '../knowledge-retrieval/utils'

const metaData = genNodeMetaData({
  sort: 4,
  type: BlockEnum.HybridRetrieval,
})

const nodeDefault: NodeDefault<HybridRetrievalNodeType> = {
  metaData,
  defaultValue: {
    query_variable_selector: [],
    query_attachment_selector: [],
    dataset_ids: [],
    graph_ids: [],
    graph_top_k: 5,
    graph_retrieval_config: {
      strategy: 'node',
      target_node_types: ['ProductModel'],
      match_mode: 'any',
      include_paths: true,
      path_depth: 8,
      include_parameters: true,
      parameter_relation_types: ['DEFINES_PARAMETER'],
      deduplicate: true,
    },
    retrieval_mode: RETRIEVE_TYPE.multiWay,
    multiple_retrieval_config: {
      top_k: DATASET_DEFAULT.top_k,
      score_threshold: undefined,
      reranking_enable: false,
    },
  },
  checkValid(payload: HybridRetrievalNodeType, t: TFunction) {
    const legacyT = t as unknown as (key: string, options?: Record<string, unknown>) => string
    let errorMessages = ''

    if (!errorMessages && (!payload.query_variable_selector || payload.query_variable_selector.length === 0))
      errorMessages = legacyT('errorMsg.fieldRequired', { ns: 'workflow', field: legacyT('nodes.hybridRetrieval.queryText', { ns: 'workflow' }) })

    const hasDatasets = payload.dataset_ids && payload.dataset_ids.length > 0
    const hasGraphs = payload.graph_ids && payload.graph_ids.length > 0
    if (!errorMessages && !hasDatasets && !hasGraphs)
      errorMessages = legacyT('errorMsg.fieldRequired', { ns: 'workflow', field: legacyT('nodes.hybridRetrieval.retrievalSources', { ns: 'workflow' }) })

    if (!errorMessages && payload.retrieval_mode === RETRIEVE_TYPE.oneWay && hasDatasets && !payload.single_retrieval_config?.model?.provider)
      errorMessages = legacyT('errorMsg.fieldRequired', { ns: 'workflow', field: legacyT('modelProvider.systemReasoningModel.key', { ns: 'common' }) })

    if (payload.retrieval_mode === RETRIEVE_TYPE.multiWay && hasDatasets) {
      const checked = checkoutRerankModelConfiguredInRetrievalSettings(
        payload._datasets || [],
        payload.multiple_retrieval_config,
      )

      if (!errorMessages && !checked)
        errorMessages = legacyT('errorMsg.fieldRequired', { ns: 'workflow', field: legacyT('errorMsg.fields.rerankModel', { ns: 'workflow' }) })
    }

    return {
      isValid: !errorMessages,
      errorMessage: errorMessages,
    }
  },
}

export default nodeDefault
