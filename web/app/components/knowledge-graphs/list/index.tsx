'use client'

import { useQuery } from '@tanstack/react-query'
import { useDebounceFn } from 'ahooks'
import { useAtomValue } from 'jotai'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Input from '@/app/components/base/input'
import Loading from '@/app/components/base/loading'
import { isCurrentWorkspaceEditorAtom } from '@/context/workspace-state'
import useDocumentTitle from '@/hooks/use-document-title'
import { consoleQuery } from '@/service/client'
import CreateGraphModal from './create-graph-modal'
import GraphCard from './graph-card'
import GraphFooter from './graph-footer'
import NewGraphCard from './new-graph-card'

const KnowledgeGraphList = () => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const isCurrentWorkspaceEditor = useAtomValue(isCurrentWorkspaceEditorAtom)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [keywords, setKeywords] = useState('')
  const [searchKeywords, setSearchKeywords] = useState('')
  useDocumentTitle(t('knowledgeGraphTitle', { ns: 'dataset' }))

  const { run: handleSearch } = useDebounceFn(() => {
    setSearchKeywords(keywords)
  }, { wait: 500 })
  const handleKeywordsChange = (value: string) => {
    setKeywords(value)
    handleSearch()
  }

  const graphQuery = useQuery(consoleQuery.knowledgeGraphs.list.queryOptions({
    input: {
      query: {
        page: 1,
        limit: 60,
        keyword: searchKeywords || undefined,
      },
    },
  }))

  return (
    <div className="relative flex grow flex-col overflow-y-auto bg-background-body">
      <div className="sticky top-0 z-10 flex items-center justify-end gap-x-1 bg-background-body px-12 pt-4 pb-2">
        <div className="flex items-center justify-center gap-2">
          <Input
            showLeftIcon
            showClearIcon
            wrapperClassName="w-[240px]"
            value={keywords}
            onChange={e => handleKeywordsChange(e.target.value)}
            onClear={() => handleKeywordsChange('')}
          />
        </div>
      </div>
      {graphQuery.isLoading && <Loading />}
      {!graphQuery.isLoading && (
        <nav className="grid grow grid-cols-1 content-start gap-3 px-12 pt-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {isCurrentWorkspaceEditor && <NewGraphCard onCreate={() => setShowCreateModal(true)} />}
          {graphQuery.data?.data.map(graph => (
            <GraphCard key={graph.id} graph={graph} />
          ))}
        </nav>
      )}
      <GraphFooter />
      <CreateGraphModal show={showCreateModal} onClose={() => setShowCreateModal(false)} />
    </div>
  )
}

export default KnowledgeGraphList
