'use client'

import type {
  KnowledgeGraphOverviewNode,
  KnowledgeGraphOverviewRelationship,
  KnowledgeGraphSearchResult,
} from '@/models/knowledge-graph'
import { Button } from '@langgenius/dify-ui/button'
import { skipToken, useQuery } from '@tanstack/react-query'
import { useDebounceFn } from 'ahooks'
import {
  useCallback,
  useMemo,
  useState,
} from 'react'
import { useTranslation } from 'react-i18next'
import Input from '@/app/components/base/input'
import Loading from '@/app/components/base/loading'
import useDocumentTitle from '@/hooks/use-document-title'
import { consoleQuery } from '@/service/client'
import KnowledgeGraphCanvas from './graph-canvas'
import ImportTemplateModal from './import-template-modal'

type KnowledgeGraphDetailProps = {
  graphId: string
}

const DEFAULT_NODE_LIMIT = 100
const MAX_NODE_LIMIT = 2000

const normalizeNodeLimit = (value: string) => {
  const limit = Number.parseInt(value, 10)

  if (!Number.isFinite(limit) || limit <= 0)
    return DEFAULT_NODE_LIMIT

  return Math.min(limit, MAX_NODE_LIMIT)
}

const OverviewStatCard = ({
  label,
  value,
}: {
  label: string
  value: number
}) => (
  <div className="rounded-lg border-[0.5px] border-components-card-border bg-components-card-bg p-4 shadow-xs">
    <div className="system-xs-regular text-text-tertiary">{label}</div>
    <div className="mt-2 title-2xl-semi-bold text-text-primary">{value}</div>
  </div>
)

type ProductParameter = {
  param_name?: string
  field_name?: string
}

const getProductParameters = (properties: Record<string, unknown>): ProductParameter[] => {
  const parameters = properties.parameters
  if (!Array.isArray(parameters))
    return []

  return parameters.filter((item): item is ProductParameter => {
    return !!item && typeof item === 'object'
  })
}

const NodeCard = ({ node }: { node: KnowledgeGraphOverviewNode }) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const labels = node.labels.length ? node.labels.join(' / ') : node.type
  const parameters = getProductParameters(node.properties)
  const parameterCount = typeof node.properties.parameter_count === 'number'
    ? node.properties.parameter_count
    : parameters.length
  const previewParameters = parameters.slice(0, 6)

  return (
    <div className="rounded-lg border-[0.5px] border-components-card-border bg-components-card-bg p-4 shadow-xs">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate system-md-semibold text-text-primary" title={node.name}>{node.name}</div>
          <div className="mt-1 truncate system-xs-regular text-text-tertiary" title={labels || node.id}>
            {labels || node.id}
          </div>
        </div>
        {!!node.type && (
          <div className="shrink-0 rounded-md bg-background-default-dimmed px-2 py-1 system-xs-medium text-text-tertiary">
            {node.type}
          </div>
        )}
      </div>
      <div className="mt-3 line-clamp-2 h-10 body-sm-regular text-text-secondary">
        {node.description || t('knowledgeGraphEmptyDescription', { ns: 'dataset' })}
      </div>
      {!!parameterCount && (
        <div className="mt-3 rounded-lg bg-background-default-subtle p-3">
          <div className="system-xs-medium text-text-secondary">
            {t('knowledgeGraphModelParameters', { ns: 'dataset', defaultValue: '模型参数' })}
            <span className="ml-1 text-text-tertiary">
              {parameterCount}
            </span>
          </div>
          {!!previewParameters.length && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {previewParameters.map(parameter => (
                <span
                  key={`${parameter.param_name || ''}-${parameter.field_name || ''}`}
                  className="max-w-full truncate rounded-md bg-components-card-bg px-2 py-1 system-xs-regular text-text-tertiary"
                  title={[parameter.param_name, parameter.field_name].filter(Boolean).join(' / ')}
                >
                  {parameter.param_name || parameter.field_name}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const RelationshipCard = ({ relationship }: { relationship: KnowledgeGraphOverviewRelationship }) => (
  <div className="rounded-lg border-[0.5px] border-components-card-border bg-components-card-bg p-4 shadow-xs">
    <div className="flex min-w-0 items-center gap-2">
      <span className="truncate system-sm-medium text-text-primary" title={relationship.source_name}>
        {relationship.source_name}
      </span>
      <span className="shrink-0 rounded-md bg-util-colors-blue-blue-50 px-2 py-1 system-xs-medium text-util-colors-blue-blue-600">
        {relationship.relation_type}
      </span>
      <span className="truncate system-sm-medium text-text-primary" title={relationship.target_name}>
        {relationship.target_name}
      </span>
    </div>
    <div className="mt-2 system-xs-regular text-text-tertiary">
      {relationship.confidence.toFixed(2)}
    </div>
  </div>
)

const getRelationshipSourceId = (
  relationship: KnowledgeGraphOverviewRelationship,
  nodeLookup: Map<string, KnowledgeGraphOverviewNode>,
) => relationship.source_id || nodeLookup.get(relationship.source_name)?.id

const getRelationshipTargetId = (
  relationship: KnowledgeGraphOverviewRelationship,
  nodeLookup: Map<string, KnowledgeGraphOverviewNode>,
) => relationship.target_id || nodeLookup.get(relationship.target_name)?.id

type SearchPath = {
  sourceId?: string
  relationId?: string
  targetId?: string
}

const metadataText = (metadata: Record<string, unknown>, key: string) => {
  const value = metadata[key]
  return typeof value === 'string' ? value : undefined
}

const getSearchPathFromResult = (
  result: KnowledgeGraphSearchResult,
  relationships: KnowledgeGraphOverviewRelationship[],
  nodeLookup: Map<string, KnowledgeGraphOverviewNode>,
): SearchPath => {
  const sourceId = metadataText(result.metadata, 'source_id')
  const relationId = metadataText(result.metadata, 'relation_id')
  const targetId = metadataText(result.metadata, 'target_id')

  if (sourceId || relationId || targetId) {
    return {
      sourceId,
      relationId,
      targetId,
    }
  }

  const matchedRelationship = relationships.find((relationship) => {
    const sourceName = relationship.source_name
    const targetName = relationship.target_name
    return result.content.includes(sourceName)
      && result.content.includes(relationship.relation_type)
      && result.content.includes(targetName)
  })

  if (!matchedRelationship)
    return {}

  return {
    sourceId: getRelationshipSourceId(matchedRelationship, nodeLookup),
    relationId: matchedRelationship.id,
    targetId: getRelationshipTargetId(matchedRelationship, nodeLookup),
  }
}

const SearchResultCard = ({
  result,
  onSelect,
}: {
  result: KnowledgeGraphSearchResult
  onSelect: () => void
}) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )

  return (
    <button
      type="button"
      className="w-full rounded-lg border-[0.5px] border-components-card-border bg-components-card-bg p-4 text-left shadow-xs transition-colors hover:bg-components-card-bg-alt"
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate system-md-semibold text-text-primary" title={result.title}>{result.title}</div>
          <div className="mt-1 body-sm-regular text-text-secondary">{result.content}</div>
        </div>
        <div className="shrink-0 rounded-md bg-background-default-dimmed px-2 py-1 system-xs-medium text-text-tertiary">
          {t('knowledgeGraphScore', { ns: 'dataset' })}
          {' '}
          {result.score.toFixed(2)}
        </div>
      </div>
    </button>
  )
}

const KnowledgeGraphDetail = ({ graphId }: KnowledgeGraphDetailProps) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const [keywords, setKeywords] = useState('')
  const [searchKeywords, setSearchKeywords] = useState('')
  const [selectedNodeId, setSelectedNodeId] = useState<string>()
  const [showImportModal, setShowImportModal] = useState(false)
  const [nodeLimit, setNodeLimit] = useState(DEFAULT_NODE_LIMIT)
  const [nodeLimitInput, setNodeLimitInput] = useState(String(DEFAULT_NODE_LIMIT))
  const graphQuery = useQuery(consoleQuery.knowledgeGraphs.detail.queryOptions({
    input: {
      params: {
        graphId,
      },
    },
  }))
  const title = graphQuery.data?.name || t('knowledgeGraphTitle', { ns: 'dataset' })
  useDocumentTitle(title)
  const overviewQuery = useQuery(consoleQuery.knowledgeGraphs.overview.queryOptions({
    input: {
      params: {
        graphId,
      },
      query: {
        limit: nodeLimit,
      },
    },
  }))

  const { run: handleSearch } = useDebounceFn((value: string) => {
    setSearchKeywords(value.trim())
  }, { wait: 500 })
  const handleKeywordsChange = (value: string) => {
    setKeywords(value)
    handleSearch(value)
  }
  const handleNodeLimitApply = useCallback(() => {
    const nextLimit = normalizeNodeLimit(nodeLimitInput)
    setNodeLimitInput(String(nextLimit))
    setNodeLimit(nextLimit)
    setSelectedNodeId(undefined)
  }, [nodeLimitInput])

  const searchQuery = useQuery(consoleQuery.knowledgeGraphs.search.queryOptions({
    input: searchKeywords
      ? {
          params: {
            graphId,
          },
          query: {
            query: searchKeywords,
            top_k: 20,
          },
        }
      : skipToken,
  }))
  const searchResults = useMemo(() => searchQuery.data?.data || [], [searchQuery.data?.data])
  const overview = overviewQuery.data
  const nodes = useMemo(() => overview?.nodes || [], [overview?.nodes])
  const relationships = useMemo(() => overview?.relationships || [], [overview?.relationships])
  const nodeLookup = useMemo(() => {
    const lookup = new Map<string, KnowledgeGraphOverviewNode>()
    nodes.forEach((node) => {
      lookup.set(node.id, node)
      lookup.set(node.name, node)
    })
    return lookup
  }, [nodes])
  const searchPaths = useMemo(() => {
    return searchResults.map(result => getSearchPathFromResult(result, relationships, nodeLookup))
  }, [nodeLookup, relationships, searchResults])
  const highlightedNodeIds = useMemo(() => {
    if (!searchKeywords)
      return undefined

    const nodeIds = new Set<string>()
    searchPaths.forEach((path) => {
      if (path.sourceId)
        nodeIds.add(path.sourceId)
      if (path.targetId)
        nodeIds.add(path.targetId)
    })
    return nodeIds
  }, [searchKeywords, searchPaths])
  const highlightedRelationshipIds = useMemo(() => {
    if (!searchKeywords)
      return undefined

    const relationshipIds = new Set<string>()
    searchPaths.forEach((path) => {
      if (path.relationId)
        relationshipIds.add(path.relationId)
    })
    return relationshipIds
  }, [searchKeywords, searchPaths])
  const selectedNode = selectedNodeId ? nodeLookup.get(selectedNodeId) : undefined
  const relatedRelationships = useMemo(() => {
    if (!selectedNodeId)
      return []

    return relationships.filter((relationship) => {
      const sourceId = getRelationshipSourceId(relationship, nodeLookup)
      const targetId = getRelationshipTargetId(relationship, nodeLookup)
      return sourceId === selectedNodeId || targetId === selectedNodeId
    })
  }, [nodeLookup, relationships, selectedNodeId])
  const relatedNodes = useMemo(() => {
    if (!selectedNodeId)
      return []

    const relatedNodeIds = new Set<string>()
    relatedRelationships.forEach((relationship) => {
      const sourceId = getRelationshipSourceId(relationship, nodeLookup)
      const targetId = getRelationshipTargetId(relationship, nodeLookup)

      if (sourceId && sourceId !== selectedNodeId)
        relatedNodeIds.add(sourceId)
      if (targetId && targetId !== selectedNodeId)
        relatedNodeIds.add(targetId)
    })

    return Array.from(relatedNodeIds)
      .map(nodeId => nodeLookup.get(nodeId))
      .filter((node): node is KnowledgeGraphOverviewNode => !!node)
  }, [nodeLookup, relatedRelationships, selectedNodeId])

  return (
    <div className="relative flex grow flex-col overflow-y-auto bg-background-body">
      <div className="sticky top-0 z-10 flex items-center justify-between gap-3 bg-background-body px-12 pt-4 pb-2">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-util-colors-blue-blue-50 text-util-colors-blue-blue-600">
              <span className="i-ri-git-branch-line h-5 w-5" />
            </span>
            <div className="min-w-0">
              <h1 className="truncate title-2xl-semi-bold text-text-primary">{title}</h1>
              <p className="mt-0.5 truncate system-xs-regular text-text-tertiary">
                {t('knowledgeGraphId', { ns: 'dataset' })}
                :
                {' '}
                {graphId}
              </p>
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Input
            showLeftIcon
            showClearIcon
            wrapperClassName="w-[320px]"
            value={keywords}
            onChange={e => handleKeywordsChange(e.target.value)}
            onClear={() => handleKeywordsChange('')}
          />
          <Button variant="secondary" onClick={() => setShowImportModal(true)}>
            <span className="mr-1 i-ri-file-upload-line h-4 w-4" />
            {t('knowledgeGraphImport', { ns: 'dataset' })}
          </Button>
        </div>
      </div>
      {graphQuery.isLoading && <Loading />}
      {!graphQuery.isLoading && (
        <div className="px-12 pt-2">
          <section className="rounded-xl bg-background-default-dimmed p-4">
            <div className="system-sm-medium text-text-secondary">{t('knowledgeGraphDescription', { ns: 'dataset' })}</div>
            <p className="mt-1 body-sm-regular text-text-primary">
              {graphQuery.data?.description || t('knowledgeGraphEmptyDescription', { ns: 'dataset' })}
            </p>
          </section>
          <section className="mt-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="system-md-semibold text-text-primary">{t('knowledgeGraphOverview', { ns: 'dataset' })}</h2>
            </div>
            {overviewQuery.isFetching && <Loading />}
            {!overviewQuery.isFetching && (
              <>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <OverviewStatCard label={t('knowledgeGraphNodeCount', { ns: 'dataset' })} value={overview?.node_count || 0} />
                  <OverviewStatCard
                    label={t('knowledgeGraphRelationshipCount', { ns: 'dataset' })}
                    value={overview?.relationship_count || 0}
                  />
                </div>
                <section className="mt-4">
                  <div className="mb-2 flex items-center justify-between">
                    <h2 className="system-md-semibold text-text-primary">{t('knowledgeGraphSearchResults', { ns: 'dataset' })}</h2>
                    {searchKeywords && (
                      <div className="system-xs-regular text-text-tertiary">
                        {t('knowledgeGraphSearchKeyword', { ns: 'dataset' })}
                        :
                        {' '}
                        {searchKeywords}
                      </div>
                    )}
                  </div>
                  {searchQuery.isFetching && <Loading />}
                  {!searchKeywords && (
                    <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-divider-regular text-text-tertiary">
                      {t('knowledgeGraphSearchPlaceholder', { ns: 'dataset' })}
                    </div>
                  )}
                  {searchKeywords && !searchQuery.isFetching && !searchResults.length && (
                    <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-divider-regular text-text-tertiary">
                      {t('knowledgeGraphSearchEmpty', { ns: 'dataset' })}
                    </div>
                  )}
                  {!!searchResults.length && (
                    <div className="grid grid-cols-1 gap-3">
                      {searchResults.map((result, index) => (
                        <SearchResultCard
                          key={`${result.graph_id}-${result.title}-${result.content}`}
                          result={result}
                          onSelect={() => setSelectedNodeId(searchPaths[index]?.sourceId || searchPaths[index]?.targetId)}
                        />
                      ))}
                    </div>
                  )}
                </section>
                {!!nodes.length && (
                  <div className="mt-4">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <div className="system-sm-medium text-text-secondary">
                        {t('knowledgeGraphVisualization', { ns: 'dataset' })}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="system-xs-regular text-text-tertiary">
                          {t('knowledgeGraphDisplayNodeLimit', { ns: 'dataset', defaultValue: '显示节点' })}
                        </span>
                        <input
                          aria-label={t('knowledgeGraphDisplayNodeLimit', { ns: 'dataset', defaultValue: '显示节点' })}
                          className="h-8 w-[96px] rounded-lg border border-components-card-border bg-components-input-bg-normal px-2 system-sm-regular text-components-input-text-filled outline-none hover:bg-state-base-hover-alt focus:border-components-input-border-active"
                          inputMode="numeric"
                          pattern="[0-9]*"
                          value={nodeLimitInput}
                          onBlur={handleNodeLimitApply}
                          onChange={event => setNodeLimitInput(event.target.value.replace(/\D/g, ''))}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter')
                              event.currentTarget.blur()
                          }}
                        />
                      </div>
                    </div>
                    <KnowledgeGraphCanvas
                      nodes={nodes}
                      relationships={relationships}
                      selectedNodeId={selectedNodeId}
                      highlightedNodeIds={highlightedNodeIds}
                      highlightedRelationshipIds={highlightedRelationshipIds}
                      onNodeSelect={setSelectedNodeId}
                    />
                  </div>
                )}
                <div className="mt-4">
                  {!selectedNode && (
                    <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-divider-regular text-text-tertiary">
                      {t('knowledgeGraphSelectNodeHint', { ns: 'dataset' })}
                    </div>
                  )}
                  {!!selectedNode && (
                    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                      <div>
                        <div className="mb-2 system-sm-medium text-text-secondary">
                          {t('knowledgeGraphSelectedNode', { ns: 'dataset' })}
                        </div>
                        <NodeCard node={selectedNode} />
                        <div className="mt-4 mb-2 system-sm-medium text-text-secondary">
                          {t('knowledgeGraphRelatedNodes', { ns: 'dataset' })}
                        </div>
                        {!relatedNodes.length && (
                          <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-divider-regular text-text-tertiary">
                            {t('knowledgeGraphNodesEmpty', { ns: 'dataset' })}
                          </div>
                        )}
                        {!!relatedNodes.length && (
                          <div className="grid grid-cols-1 gap-3">
                            {relatedNodes.map(node => (
                              <NodeCard key={node.id} node={node} />
                            ))}
                          </div>
                        )}
                      </div>
                      <div>
                        <div className="mb-2 system-sm-medium text-text-secondary">
                          {t('knowledgeGraphRelatedRelationships', { ns: 'dataset' })}
                        </div>
                        {!relatedRelationships.length && (
                          <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-divider-regular text-text-tertiary">
                            {t('knowledgeGraphRelationshipsEmpty', { ns: 'dataset' })}
                          </div>
                        )}
                        {!!relatedRelationships.length && (
                          <div className="grid grid-cols-1 gap-3">
                            {relatedRelationships.map(relationship => (
                              <RelationshipCard
                                key={relationship.id}
                                relationship={relationship}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </section>
        </div>
      )}
      <ImportTemplateModal
        graphId={graphId}
        show={showImportModal}
        onClose={() => setShowImportModal(false)}
      />
    </div>
  )
}

export default KnowledgeGraphDetail
