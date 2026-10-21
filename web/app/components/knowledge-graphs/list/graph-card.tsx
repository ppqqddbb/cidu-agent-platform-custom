'use client'

import type { KnowledgeGraph } from '@/models/knowledge-graph'
import { Button } from '@langgenius/dify-ui/button'
import { toast } from '@langgenius/dify-ui/toast'
import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import CopyableIdRow from '@/app/components/base/copyable-id-row'
import { useRouter } from '@/next/navigation'
import { useDeleteKnowledgeGraph } from '@/service/use-knowledge-graph'

type GraphCardProps = {
  graph: KnowledgeGraph
}

const GraphCard = ({ graph }: GraphCardProps) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const router = useRouter()
  const deleteGraph = useDeleteKnowledgeGraph()

  const handleDelete = (event: React.MouseEvent) => {
    event.preventDefault()
    event.stopPropagation()
    deleteGraph.mutate({
      params: {
        graphId: graph.id,
      },
    }, {
      onSuccess: () => {
        toast(t('knowledgeGraphDeleted', { ns: 'dataset' }), { type: 'success' })
      },
    })
  }

  return (
    <div
      className="group flex h-[190px] cursor-pointer flex-col rounded-xl border-[0.5px] border-components-card-border bg-components-card-bg p-4 shadow-xs shadow-shadow-shadow-3 transition-all duration-200 hover:bg-components-card-bg-alt hover:shadow-md"
      onClick={() => router.push(`/knowledge-graphs/${graph.id}`)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-util-colors-blue-blue-50 text-util-colors-blue-blue-600">
            <span className="i-ri-git-branch-line h-5 w-5" />
          </span>
          <div className="min-w-0">
            <div className="truncate system-md-semibold text-text-primary" title={graph.name}>{graph.name}</div>
            <div className="mt-0.5 system-xs-regular text-text-tertiary">{t('knowledgeGraphIsolated', { ns: 'dataset' })}</div>
          </div>
        </div>
        <Button
          variant="ghost"
          size="small"
          disabled={deleteGraph.isPending}
          onClick={handleDelete}
        >
          <span className="i-ri-delete-bin-line h-4 w-4" />
        </Button>
      </div>
      <div className="mt-4 line-clamp-3 grow body-sm-regular text-text-secondary">
        {graph.description || t('knowledgeGraphEmptyDescription', { ns: 'dataset' })}
      </div>
      <CopyableIdRow
        label={t('knowledgeGraphId', { ns: 'dataset' })}
        id={graph.id}
        className="mt-4"
      />
    </div>
  )
}

export default GraphCard
