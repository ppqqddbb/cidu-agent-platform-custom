import type { ValueSelector } from '../../types'
import type { GraphRetrievalConfig, KnowledgeGraphRetrievalNodeType } from './types'
import type { KnowledgeGraph } from '@/models/knowledge-graph'
import { useQuery } from '@tanstack/react-query'
import { produce } from 'immer'
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
} from 'react'
import useNodeCrud from '@/app/components/workflow/nodes/_base/hooks/use-node-crud'
import { consoleQuery } from '@/service/client'
import { useIsChatMode, useNodesReadOnly, useWorkflow } from '../../hooks'
import { BlockEnum, VarType } from '../../types'

const filterStringVar = (varPayload: { type: VarType }) => varPayload.type === VarType.string

const useConfig = (id: string, payload: KnowledgeGraphRetrievalNodeType) => {
  const { nodesReadOnly: readOnly } = useNodesReadOnly()
  const isChatMode = useIsChatMode()
  const { getBeforeNodesInSameBranch } = useWorkflow()
  const startNode = getBeforeNodesInSameBranch(id).find(node => node.data.type === BlockEnum.Start)
  const startNodeId = startNode?.id
  const { inputs, setInputs: doSetInputs } = useNodeCrud<KnowledgeGraphRetrievalNodeType>(id, payload)
  const inputRef = useRef(inputs)

  useEffect(() => {
    inputRef.current = inputs
  }, [inputs])

  const setInputs = useCallback((nextInputs: KnowledgeGraphRetrievalNodeType) => {
    doSetInputs(nextInputs)
    inputRef.current = nextInputs
  }, [doSetInputs])

  const handleQueryVarChange = useCallback((newVar: ValueSelector | string) => {
    setInputs(produce(inputRef.current, (draft) => {
      draft.query_variable_selector = newVar as ValueSelector
    }))
  }, [setInputs])

  const handleGraphsChange = useCallback((graphs: KnowledgeGraph[]) => {
    setInputs(produce(inputRef.current, (draft) => {
      draft.graph_ids = graphs.map(graph => graph.id)
      draft._knowledgeGraphs = graphs
    }))
  }, [setInputs])

  const handleTopKChange = useCallback((topK: number) => {
    setInputs(produce(inputRef.current, (draft) => {
      draft.top_k = topK
    }))
  }, [setInputs])

  const handleRetrievalConfigChange = useCallback((retrievalConfig: GraphRetrievalConfig) => {
    setInputs(produce(inputRef.current, (draft) => {
      draft.retrieval_config = retrievalConfig
    }))
  }, [setInputs])

  useEffect(() => {
    const currentInputs = inputRef.current
    if (!isChatMode || currentInputs.query_variable_selector.length > 0 || !startNodeId)
      return

    setInputs(produce(currentInputs, (draft) => {
      draft.query_variable_selector = [startNodeId, 'sys.query']
    }))
  }, [inputRef, isChatMode, setInputs, startNodeId])

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

  return {
    readOnly,
    inputs,
    handleQueryVarChange,
    handleGraphsChange,
    handleTopKChange,
    handleRetrievalConfigChange,
    filterStringVar,
    graphs: graphQuery.data?.data || [],
    graphsLoading: graphQuery.isLoading,
    selectedGraphs,
  }
}

export default useConfig
