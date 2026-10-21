export type KnowledgeGraph = {
  id: string
  tenant_id: string
  name: string
  description: string
  created_by: string
  updated_by: string
  created_at: string
  updated_at: string
}

export type KnowledgeGraphListResponse = {
  data: KnowledgeGraph[]
  has_more: boolean
  limit: number
  total: number
  page: number
}

export type KnowledgeGraphSearchResult = {
  graph_id: string
  title: string
  content: string
  score: number
  metadata: Record<string, unknown>
}

export type KnowledgeGraphSearchResponse = {
  data: KnowledgeGraphSearchResult[]
}

export type KnowledgeGraphOverviewNode = {
  id: string
  name: string
  type: string
  description: string
  labels: string[]
  properties: Record<string, unknown>
}

export type KnowledgeGraphOverviewRelationship = {
  id: string
  source_id?: string
  source_name: string
  relation_type: string
  target_id?: string
  target_name: string
  confidence: number
  properties: Record<string, unknown>
}

export type KnowledgeGraphOverview = {
  node_count: number
  relationship_count: number
  nodes: KnowledgeGraphOverviewNode[]
  relationships: KnowledgeGraphOverviewRelationship[]
}

export type KnowledgeGraphImportNode = {
  id: string
  name: string
  type?: string
  description?: string
  labels?: string[]
  properties?: Record<string, unknown>
}

export type KnowledgeGraphImportRelationship = {
  id?: string
  source_id: string
  target_id: string
  relation_type: string
  confidence?: number
  properties?: Record<string, unknown>
}

export type KnowledgeGraphImportTemplate = {
  nodes: KnowledgeGraphImportNode[]
  relationships?: KnowledgeGraphImportRelationship[]
}

export type KnowledgeGraphImportResult = {
  node_count: number
  relationship_count: number
}
