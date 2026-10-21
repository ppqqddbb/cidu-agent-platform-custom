import type { GraphRetrievalConfig } from '../knowledge-graph-retrieval/types'
import type { HybridRetrievalNodeType } from './types'
import type { ValueSelector } from '@/app/components/workflow/types'
import type { KnowledgeGraph } from '@/models/knowledge-graph'
import { useQuery } from '@tanstack/react-query'
import { produce } from 'immer'
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
} from 'react'
import { ModelTypeEnum } from '@/app/components/header/account-setting/model-provider-page/declarations'
import { useCurrentProviderAndModel, useModelListAndDefaultModelAndCurrentProviderAndModel } from '@/app/components/header/account-setting/model-provider-page/hooks'
import useNodeCrud from '@/app/components/workflow/nodes/_base/hooks/use-node-crud'
import { DATASET_DEFAULT } from '@/config'
import { consoleQuery } from '@/service/client'
import { RETRIEVE_TYPE } from '@/types/app'
import { useDatasetsDetailStore } from '../../datasets-detail-store/store'
import {
  useIsChatMode,
  useNodesReadOnly,
  useWorkflow,
} from '../../hooks'
import { BlockEnum } from '../../types'
import useKnowledgeDatasetSelection from '../knowledge-retrieval/hooks/use-knowledge-dataset-selection'
import useKnowledgeMetadataConfig from '../knowledge-retrieval/hooks/use-knowledge-metadata-config'
import useKnowledgeModelConfig from '../knowledge-retrieval/hooks/use-knowledge-model-config'

const useConfig = (id: string, payload: HybridRetrievalNodeType) => {
  const { nodesReadOnly: readOnly } = useNodesReadOnly()
  const isChatMode = useIsChatMode()
  const { getBeforeNodesInSameBranch } = useWorkflow()
  const startNode = getBeforeNodesInSameBranch(id).find(node => node.data.type === BlockEnum.Start)
  const startNodeId = startNode?.id
  const { inputs, setInputs: doSetInputs } = useNodeCrud<HybridRetrievalNodeType>(id, payload)
  const updateDatasetsDetail = useDatasetsDetailStore(s => s.updateDatasetsDetail)
  const inputRef = useRef(inputs)

  useEffect(() => {
    inputRef.current = inputs
  }, [inputs])

  const setInputs = useCallback((nextInputs: HybridRetrievalNodeType) => {
    const normalizedInputs = produce(nextInputs, (draft) => {
      if (nextInputs.dataset_ids.length > 0) {
        if (nextInputs.retrieval_mode === RETRIEVE_TYPE.multiWay)
          delete draft.single_retrieval_config
        else
          delete draft.multiple_retrieval_config
      }
    })
    doSetInputs(normalizedInputs)
    inputRef.current = normalizedInputs
  }, [doSetInputs])

  const handleQueryVarChange = useCallback((newVar: ValueSelector | string) => {
    setInputs(produce(inputRef.current, (draft) => {
      draft.query_variable_selector = newVar as ValueSelector
    }))
  }, [setInputs])

  const handleQueryAttachmentChange = useCallback((newVar: ValueSelector | string) => {
    setInputs(produce(inputRef.current, (draft) => {
      draft.query_attachment_selector = newVar as ValueSelector
    }))
  }, [setInputs])

  const {
    currentProvider,
    currentModel,
  } = useModelListAndDefaultModelAndCurrentProviderAndModel(ModelTypeEnum.textGeneration)

  const {
    modelList: rerankModelList,
    defaultModel: rerankDefaultModel,
  } = useModelListAndDefaultModelAndCurrentProviderAndModel(ModelTypeEnum.rerank)

  const {
    currentModel: currentRerankModel,
    currentProvider: currentRerankProvider,
  } = useCurrentProviderAndModel(
    rerankModelList,
    rerankDefaultModel
      ? {
          ...rerankDefaultModel,
          provider: rerankDefaultModel.provider.provider,
        }
      : undefined,
  )

  const fallbackRerankModel = useMemo(() => ({
    provider: currentRerankProvider?.provider,
    model: currentRerankModel?.model,
  }), [currentRerankModel?.model, currentRerankProvider?.provider])

  const {
    selectedDatasets,
    selectedDatasetsLoaded,
    rerankModelOpen,
    setRerankModelOpen,
    handleOnDatasetsChange,
    showImageQueryVarSelector,
  } = useKnowledgeDatasetSelection({
    inputs,
    inputRef,
    setInputs,
    payloadRetrievalMode: payload.retrieval_mode,
    updateDatasetsDetail,
    fallbackRerankModel,
  })

  const {
    handleModelChanged,
    handleCompletionParamsChange,
    handleRetrievalModeChange,
    handleMultipleRetrievalConfigChange,
  } = useKnowledgeModelConfig({
    inputs,
    inputRef,
    setInputs,
    selectedDatasets,
    currentProvider,
    currentModel,
    fallbackRerankModel,
    hasRerankDefaultModel: Boolean(currentRerankModel && rerankDefaultModel),
  })

  useEffect(() => {
    const currentInputs = inputRef.current
    let nextQueryVariableSelector: ValueSelector = currentInputs.query_variable_selector
    if (isChatMode && currentInputs.query_variable_selector.length === 0 && startNodeId)
      nextQueryVariableSelector = [startNodeId, 'sys.query']

    setInputs(produce(currentInputs, (draft) => {
      draft.query_variable_selector = nextQueryVariableSelector
    }))
  }, [inputRef, isChatMode, setInputs, startNodeId])

  const metadataConfig = useKnowledgeMetadataConfig({
    id,
    inputRef,
    setInputs,
  })

  const graphQuery = useQuery(consoleQuery.knowledgeGraphs.list.queryOptions({
    input: {
      query: {
        page: 1,
        limit: 100,
      },
    },
  }))

  const selectedGraphs = useMemo(() => {
    const graphs = [...(inputs._knowledgeGraphs || []), ...(graphQuery.data?.data || [])]
    return inputs.graph_ids.reduce<KnowledgeGraph[]>((acc, graphId) => {
      const graph = graphs.find(item => item.id === graphId)
      if (graph)
        acc.push(graph)
      return acc
    }, [])
  }, [graphQuery.data?.data, inputs._knowledgeGraphs, inputs.graph_ids])

  const handleGraphsChange = useCallback((graphs: KnowledgeGraph[]) => {
    setInputs(produce(inputRef.current, (draft) => {
      draft.graph_ids = graphs.map(graph => graph.id)
      draft._knowledgeGraphs = graphs
    }))
  }, [inputRef, setInputs])

  const handleGraphTopKChange = useCallback((topK: number) => {
    setInputs(produce(inputRef.current, (draft) => {
      draft.graph_top_k = topK || DATASET_DEFAULT.top_k
    }))
  }, [inputRef, setInputs])

  const handleGraphRetrievalConfigChange = useCallback((retrievalConfig: GraphRetrievalConfig) => {
    setInputs(produce(inputRef.current, (draft) => {
      draft.graph_retrieval_config = retrievalConfig
    }))
  }, [inputRef, setInputs])

  return {
    readOnly,
    inputs,
    handleQueryVarChange,
    handleQueryAttachmentChange,
    filterStringVar: metadataConfig.filterStringVar,
    filterFileVar: metadataConfig.filterFileVar,
    handleRetrievalModeChange,
    handleMultipleRetrievalConfigChange,
    handleModelChanged,
    handleCompletionParamsChange,
    selectedDatasets: selectedDatasets.filter(d => d.name),
    selectedDatasetsLoaded,
    handleOnDatasetsChange,
    rerankModelOpen,
    setRerankModelOpen,
    handleMetadataFilterModeChange: metadataConfig.handleMetadataFilterModeChange,
    handleUpdateCondition: metadataConfig.handleUpdateCondition,
    handleAddCondition: metadataConfig.handleAddCondition,
    handleRemoveCondition: metadataConfig.handleRemoveCondition,
    handleToggleConditionLogicalOperator: metadataConfig.handleToggleConditionLogicalOperator,
    handleMetadataModelChange: metadataConfig.handleMetadataModelChange,
    handleMetadataCompletionParamsChange: metadataConfig.handleMetadataCompletionParamsChange,
    availableStringVars: metadataConfig.availableStringVars,
    availableStringNodesWithParent: metadataConfig.availableStringNodesWithParent,
    availableNumberVars: metadataConfig.availableNumberVars,
    availableNumberNodesWithParent: metadataConfig.availableNumberNodesWithParent,
    showImageQueryVarSelector,
    graphs: graphQuery.data?.data || [],
    graphsLoading: graphQuery.isLoading,
    selectedGraphs,
    handleGraphsChange,
    handleGraphTopKChange,
    handleGraphRetrievalConfigChange,
  }
}

export default useConfig
