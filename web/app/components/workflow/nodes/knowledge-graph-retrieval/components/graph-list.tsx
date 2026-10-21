'use client'

import type { FC } from 'react'
import type { KnowledgeGraph } from '@/models/knowledge-graph'
import { RiDeleteBinLine, RiGitBranchLine } from '@remixicon/react'
import { produce } from 'immer'
import * as React from 'react'
import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import ActionButton, { ActionButtonState } from '@/app/components/base/action-button'

type Props = {
  selectedGraphs: KnowledgeGraph[]
  onChange: (graphs: KnowledgeGraph[]) => void
  readonly?: boolean
}

const GraphList: FC<Props> = ({
  selectedGraphs,
  onChange,
  readonly,
}) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )

  const handleRemove = React.useCallback((index: number) => {
    return (event: React.MouseEvent) => {
      event.stopPropagation()
      const nextGraphs = produce(selectedGraphs, (draft) => {
        draft.splice(index, 1)
      })
      onChange(nextGraphs)
    }
  }, [onChange, selectedGraphs])

  return (
    <div className="space-y-1">
      {selectedGraphs.length
        ? selectedGraphs.map((graph, index) => (
            <div key={graph.id} className="group/graph-item flex h-10 items-center justify-between rounded-lg border-[0.5px] border-components-panel-border-subtle bg-components-panel-on-panel-item-bg px-2 hover:bg-components-panel-on-panel-item-bg-hover">
              <div className="flex w-0 grow items-center gap-1.5">
                <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-util-colors-green-green-500 text-white">
                  <RiGitBranchLine className="h-3.5 w-3.5" />
                </div>
                <div className="w-0 grow truncate system-sm-medium text-text-secondary">{graph.name}</div>
              </div>
              {!readonly && (
                <ActionButton
                  aria-label={t('operation.remove', { ns: 'common' })}
                  onClick={handleRemove(index)}
                  state={ActionButtonState.Default}
                  className="hidden group-hover/graph-item:flex"
                >
                  <RiDeleteBinLine className="h-4 w-4 text-text-tertiary" />
                </ActionButton>
              )}
            </div>
          ))
        : (
            <div className="cursor-default rounded-lg bg-background-section p-3 text-center text-xs text-text-tertiary select-none">
              {t('nodes.knowledgeGraphRetrieval.emptyGraphTip', { ns: 'workflow' })}
            </div>
          )}
    </div>
  )
}

export default React.memo(GraphList)
