import type {
  KnowledgeGraph,
  KnowledgeGraphImportResult,
  KnowledgeGraphImportTemplate,
  KnowledgeGraphListResponse,
  KnowledgeGraphOverview,
  KnowledgeGraphSearchResponse,
} from '@/models/knowledge-graph'
import { type } from '@orpc/contract'
import { base } from '../base'

export const knowledgeGraphsContract = base
  .route({
    path: '/knowledge-graphs',
    method: 'GET',
  })
  .input(type<{
    query?: {
      page?: number
      limit?: number
      keyword?: string
    }
  }>())
  .output(type<KnowledgeGraphListResponse>())

export const knowledgeGraphCreateContract = base
  .route({
    path: '/knowledge-graphs',
    method: 'POST',
  })
  .input(type<{
    body: {
      name: string
      description?: string
    }
  }>())
  .output(type<KnowledgeGraph>())

export const knowledgeGraphDeleteContract = base
  .route({
    path: '/knowledge-graphs/{graphId}',
    method: 'DELETE',
  })
  .input(type<{
    params: {
      graphId: string
    }
  }>())
  .output(type<unknown>())

export const knowledgeGraphDetailContract = base
  .route({
    path: '/knowledge-graphs/{graphId}',
    method: 'GET',
  })
  .input(type<{
    params: {
      graphId: string
    }
  }>())
  .output(type<KnowledgeGraph>())

export const knowledgeGraphSearchContract = base
  .route({
    path: '/knowledge-graphs/{graphId}/search',
    method: 'GET',
  })
  .input(type<{
    params: {
      graphId: string
    }
    query: {
      query: string
      top_k?: number
    }
  }>())
  .output(type<KnowledgeGraphSearchResponse>())

export const knowledgeGraphOverviewContract = base
  .route({
    path: '/knowledge-graphs/{graphId}/overview',
    method: 'GET',
  })
  .input(type<{
    params: {
      graphId: string
    }
    query?: {
      limit?: number
    }
  }>())
  .output(type<KnowledgeGraphOverview>())

export const knowledgeGraphImportTemplateContract = base
  .route({
    path: '/knowledge-graphs/{graphId}/import',
    method: 'POST',
  })
  .input(type<{
    params: {
      graphId: string
    }
    body: KnowledgeGraphImportTemplate
  }>())
  .output(type<KnowledgeGraphImportResult>())
