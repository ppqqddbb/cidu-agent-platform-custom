import type { FC } from 'react'
import type { HybridRetrievalNodeType } from './types'
import type { NodeProps } from '@/app/components/workflow/types'
import type { DataSet } from '@/models/datasets'
import { RiGitBranchLine } from '@remixicon/react'
import * as React from 'react'
import { useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import AppIcon from '@/app/components/base/app-icon'
import { useDatasetsDetailStore } from '../../datasets-detail-store/store'

const Node: FC<NodeProps<HybridRetrievalNodeType>> = ({
  data,
}) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const datasetsDetail = useDatasetsDetailStore(s => s.datasetsDetail)

  const selectedDatasets = useMemo(() => {
    return data.dataset_ids?.reduce<DataSet[]>((acc, id) => {
      if (datasetsDetail[id])
        acc.push(datasetsDetail[id])
      return acc
    }, []) || []
  }, [data.dataset_ids, datasetsDetail])

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

  if (!selectedDatasets.length && !selectedGraphs.length)
    return null

  return (
    <div className="mb-1 px-3 py-1">
      <div className="space-y-0.5">
        {selectedDatasets.map(({ id, name, icon_info }) => {
          const iconInfo = icon_info || {
            icon: 'D',
            icon_type: 'emoji' as const,
            icon_background: '#FFF4ED',
            icon_url: '',
          }
          return (
            <div key={id} className="flex h-[26px] items-center gap-x-1 rounded-md bg-workflow-block-parma-bg px-1">
              <AppIcon
                size="xs"
                iconType={iconInfo.icon_type}
                icon={iconInfo.icon}
                background={iconInfo.icon_type === 'image' ? undefined : iconInfo.icon_background}
                imageUrl={iconInfo.icon_type === 'image' ? iconInfo.icon_url : undefined}
                className="shrink-0"
              />
              <div className="w-0 grow truncate system-xs-regular text-text-secondary">
                {name}
              </div>
            </div>
          )
        })}
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
