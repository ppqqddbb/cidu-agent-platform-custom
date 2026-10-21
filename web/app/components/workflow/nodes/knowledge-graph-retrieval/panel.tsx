import type { FC } from 'react'
import type { KnowledgeGraphRetrievalNodeType } from './types'
import type { NodePanelProps } from '@/app/components/workflow/types'
import { memo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import Field from '@/app/components/workflow/nodes/_base/components/field'
import OutputVars, { VarItem } from '@/app/components/workflow/nodes/_base/components/output-vars'
import Split from '@/app/components/workflow/nodes/_base/components/split'
import VarReferencePicker from '@/app/components/workflow/nodes/_base/components/variable/var-reference-picker'
import AddGraph from './components/add-graph'
import GraphList from './components/graph-list'
import RetrievalConfig from './components/retrieval-config'
import TopKInput from './components/top-k-input'
import useConfig from './use-config'

const i18nPrefix = 'nodes.knowledgeGraphRetrieval'

const Panel: FC<NodePanelProps<KnowledgeGraphRetrievalNodeType>> = ({
  id,
  data,
}) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const {
    readOnly,
    inputs,
    handleQueryVarChange,
    handleGraphsChange,
    handleTopKChange,
    handleRetrievalConfigChange,
    filterStringVar,
    graphs,
    graphsLoading,
    selectedGraphs,
  } = useConfig(id, data)

  return (
    <div className="pt-2">
      <div className="space-y-4 px-4 pb-4">
        <Field title={t(`${i18nPrefix}.queryText`, { ns: 'workflow' })} required>
          <VarReferencePicker
            nodeId={id}
            readonly={readOnly}
            isShowNodeName
            value={inputs.query_variable_selector}
            onChange={handleQueryVarChange}
            filterVar={filterStringVar}
          />
        </Field>
        <Field
          title={t(`${i18nPrefix}.knowledgeGraph`, { ns: 'workflow' })}
          required
          operations={
            readOnly
              ? undefined
              : (
                  <AddGraph
                    graphs={graphs}
                    selectedIds={inputs.graph_ids}
                    onChange={handleGraphsChange}
                    loading={graphsLoading}
                  />
                )
          }
        >
          <GraphList
            selectedGraphs={selectedGraphs}
            onChange={handleGraphsChange}
            readonly={readOnly}
          />
        </Field>
        <Field title={t(`${i18nPrefix}.topK`, { ns: 'workflow' })}>
          <TopKInput
            value={inputs.top_k}
            onChange={handleTopKChange}
            readonly={readOnly}
          />
        </Field>
        <Field title={t(`${i18nPrefix}.retrievalConfig.title`, { ns: 'workflow' })} supportFold>
          <RetrievalConfig
            value={inputs.retrieval_config}
            onChange={handleRetrievalConfigChange}
            readonly={readOnly}
          />
        </Field>
      </div>
      <Split />
      <div>
        <OutputVars>
          <VarItem
            name="result"
            type="Array[Object]"
            description={t(`${i18nPrefix}.outputVars.output`, { ns: 'workflow' })}
            subItems={[
              {
                name: 'content',
                type: 'string',
                description: t(`${i18nPrefix}.outputVars.content`, { ns: 'workflow' }),
              },
              {
                name: 'title',
                type: 'string',
                description: t(`${i18nPrefix}.outputVars.title`, { ns: 'workflow' }),
              },
              {
                name: 'metadata',
                type: 'object',
                description: t(`${i18nPrefix}.outputVars.metadata`, { ns: 'workflow' }),
              },
            ]}
          />
        </OutputVars>
      </div>
    </div>
  )
}

export default memo(Panel)
