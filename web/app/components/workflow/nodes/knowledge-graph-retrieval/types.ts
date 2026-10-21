import type { CommonNodeType, ValueSelector } from '@/app/components/workflow/types'
import type { KnowledgeGraph } from '@/models/knowledge-graph'

export type GraphRetrievalConfig = {
  strategy: 'path' | 'node'
  target_node_types?: string[]
  match_mode?: 'any' | 'all'
  include_paths?: boolean
  path_depth?: number
  include_parameters?: boolean
  parameter_relation_types?: string[]
  deduplicate?: boolean
}

export type KnowledgeGraphRetrievalNodeType = CommonNodeType & {
  query_variable_selector: ValueSelector
  graph_ids: string[]
  top_k?: number
  retrieval_config?: GraphRetrievalConfig
  _knowledgeGraphs?: KnowledgeGraph[]
}
