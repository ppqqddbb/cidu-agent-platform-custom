import type { GraphRetrievalConfig } from '../knowledge-graph-retrieval/types'
import type { KnowledgeRetrievalNodeType } from '../knowledge-retrieval/types'
import type { KnowledgeGraph } from '@/models/knowledge-graph'

export type HybridRetrievalNodeType = KnowledgeRetrievalNodeType & {
  graph_ids: string[]
  graph_top_k?: number
  graph_retrieval_config?: GraphRetrievalConfig
  _knowledgeGraphs?: KnowledgeGraph[]
}
