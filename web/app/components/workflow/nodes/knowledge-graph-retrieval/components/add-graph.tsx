'use client'

import type { FC } from 'react'
import type { KnowledgeGraph } from '@/models/knowledge-graph'
import { Button } from '@langgenius/dify-ui/button'
import { cn } from '@langgenius/dify-ui/cn'
import {
  Dialog,
  DialogCloseButton,
  DialogContent,
  DialogTitle,
} from '@langgenius/dify-ui/dialog'
import { useBoolean } from 'ahooks'
import * as React from 'react'
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Input from '@/app/components/base/input'
import Loading from '@/app/components/base/loading'
import { Checkbox } from '@langgenius/dify-ui/checkbox'

type Props = {
  graphs: KnowledgeGraph[]
  selectedIds: string[]
  loading?: boolean
  onChange: (graphs: KnowledgeGraph[]) => void
}

const AddGraph: FC<Props> = ({
  graphs,
  selectedIds,
  loading,
  onChange,
}) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const [isShowModal, {
    setTrue: showModal,
    setFalse: hideModal,
  }] = useBoolean(false)
  const [selectedIdsInModal, setSelectedIdsInModal] = useState(() => selectedIds)
  const [keyword, setKeyword] = useState('')

  const filteredGraphs = useMemo(() => {
    const trimmedKeyword = keyword.trim().toLowerCase()
    if (!trimmedKeyword)
      return graphs
    return graphs.filter(graph => graph.name.toLowerCase().includes(trimmedKeyword))
  }, [graphs, keyword])

  const selectedGraphs = useMemo(() => {
    return selectedIdsInModal.reduce<KnowledgeGraph[]>((acc, graphId) => {
      const graph = graphs.find(item => item.id === graphId)
      if (graph)
        acc.push(graph)
      return acc
    }, [])
  }, [graphs, selectedIdsInModal])

  const toggleGraph = (graph: KnowledgeGraph) => {
    setSelectedIdsInModal((currentIds) => {
      if (currentIds.includes(graph.id))
        return currentIds.filter(id => id !== graph.id)
      return [...currentIds, graph.id]
    })
  }

  const resetModalState = () => {
    // Keep modal selection in sync when the panel changes outside the dialog.
    setSelectedIdsInModal(selectedIds)
    setKeyword('')
  }

  const handleShowModal = () => {
    resetModalState()
    showModal()
  }

  const handleSelect = () => {
    onChange(selectedGraphs)
    hideModal()
  }

  const handleOpenChange = (open: boolean) => {
    if (open)
      return
    resetModalState()
    hideModal()
  }

  return (
    <div>
      <div className="cursor-pointer rounded-md p-1 select-none hover:bg-state-base-hover" onClick={handleShowModal} data-testid="add-graph-button">
        <span className="i-ri-add-line h-4 w-4 text-text-tertiary" />
      </div>
      {isShowModal && (
        <Dialog open={isShowModal} onOpenChange={handleOpenChange}>
          <DialogContent className="max-w-[420px]">
            <DialogCloseButton />
            <DialogTitle className="title-2xl-semi-bold text-text-primary">
              {t('nodes.knowledgeGraphRetrieval.selectGraphTitle', { ns: 'workflow' })}
            </DialogTitle>
            <div className="mt-6">
              <Input
                showLeftIcon
                showClearIcon
                value={keyword}
                placeholder={t('placeholder.search', { ns: 'common' })}
                onChange={event => setKeyword(event.target.value)}
                onClear={() => setKeyword('')}
              />
            </div>
            <div className="mt-4 max-h-[286px] space-y-1 overflow-y-auto">
              {loading
                ? (
                    <div className="flex h-[160px]">
                      <Loading type="area" />
                    </div>
                  )
                : filteredGraphs.length
                  ? filteredGraphs.map(graph => (
                      <div
                        key={graph.id}
                        className={cn(
                          'flex h-10 cursor-pointer items-center gap-2 rounded-lg border-[0.5px] border-components-panel-border-subtle bg-components-panel-on-panel-item-bg px-2 shadow-xs hover:border-components-panel-border hover:bg-components-panel-on-panel-item-bg-hover hover:shadow-sm',
                          selectedIdsInModal.includes(graph.id) && 'border-[1.5px] border-components-option-card-option-selected-border bg-state-accent-hover shadow-xs hover:border-components-option-card-option-selected-border hover:bg-state-accent-hover hover:shadow-xs',
                        )}
                        onClick={() => toggleGraph(graph)}
                      >
                        <Checkbox
                          checked={selectedIdsInModal.includes(graph.id)}
                          onClick={(event) => {
                            event.stopPropagation()
                          }}
                          onCheckedChange={() => {
                            toggleGraph(graph)
                          }}
                        />
                        <div className="w-0 grow truncate system-sm-medium text-text-secondary">
                          {graph.name}
                        </div>
                      </div>
                    ))
                  : (
                      <div className="flex h-[128px] items-center justify-center rounded-lg bg-background-section text-xs text-text-tertiary">
                        {t('noData', { ns: 'common' })}
                      </div>
                    )}
            </div>
            <div className="mt-6 flex items-center justify-between">
              <div className="system-sm-medium text-text-secondary">
                {selectedIdsInModal.length > 0 && t('operation.selectCount', { ns: 'common', count: selectedIdsInModal.length })}
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => handleOpenChange(false)}>
                  {t('operation.cancel', { ns: 'common' })}
                </Button>
                <Button variant="primary" disabled={loading} onClick={handleSelect}>
                  {t('operation.add', { ns: 'common' })}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}

export default React.memo(AddGraph)
