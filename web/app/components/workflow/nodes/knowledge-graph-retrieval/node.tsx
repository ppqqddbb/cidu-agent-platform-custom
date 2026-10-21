import type { FC } from 'react'
import type { KnowledgeGraphRetrievalNodeType } from './types'
import type { NodeProps } from '@/app/components/workflow/types'
import { RiGitBranchLine } from '@remixicon/react'
import * as React from 'react'
import { useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'

const Node: FC<NodeProps<KnowledgeGraphRetrievalNodeType>> = ({
  data,
}) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const selectedGraphs = useMemo(() => {
    const graphs = data._knowledgeGraphs || []
    return data.graph_ids.reduce<{ id: string, name: string }[]>((acc, graphId) => {
      const graph = graphs.find(item => item.id === graphId)
      acc.push(graph || {
        id: graphId,
        name: t('nodes.knowledgeGraphRetrieval.unknownGraph', { ns: 'workflow' }),
      })
      return acc
    }, [])
  }, [data._knowledgeGraphs, data.graph_ids, t])

  if (!selectedGraphs.length)
    return null

  return (
    <div className="mb-1 px-3 py-1">
      <div className="space-y-0.5">
        {selectedGraphs.map(graph => (
          <div key={graph.id} className="flex h-[26px] items-center gap-x-1 rounded-md bg-workflow-block-parma-bg px-1">
            <div className="flex h-4 w-4 shrink-0 items-center justify-center rounded-[5px] bg-util-colors-green-green-500 text-white">
              <RiGitBranchLine className="h-3 w-3" />
            </div>
            <div className="w-0 grow truncate system-xs-regular text-text-secondary">
              {graph.name}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default React.memo(Node)
