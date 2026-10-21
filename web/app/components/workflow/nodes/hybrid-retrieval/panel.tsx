import type { FC } from 'react'
import type { KnowledgeRetrievalNodeType } from '../knowledge-retrieval/types'
import type { HybridRetrievalNodeType } from './types'
import type { NodePanelProps } from '@/app/components/workflow/types'
import { intersectionBy } from 'es-toolkit/compat'
import {
  memo,
  useCallback,
  useMemo,
} from 'react'
import { useTranslation } from 'react-i18next'
import Field from '@/app/components/workflow/nodes/_base/components/field'
import OutputVars, { VarItem } from '@/app/components/workflow/nodes/_base/components/output-vars'
import Split from '@/app/components/workflow/nodes/_base/components/split'
import VarReferencePicker from '../_base/components/variable/var-reference-picker'
import AddGraph from '../knowledge-graph-retrieval/components/add-graph'
import GraphList from '../knowledge-graph-retrieval/components/graph-list'
import GraphRetrievalConfig from '../knowledge-graph-retrieval/components/retrieval-config'
import TopKInput from '../knowledge-graph-retrieval/components/top-k-input'
import AddKnowledge from '../knowledge-retrieval/components/add-dataset'
import DatasetList from '../knowledge-retrieval/components/dataset-list'
import MetadataFilter from '../knowledge-retrieval/components/metadata/metadata-filter'
import RetrievalConfig from '../knowledge-retrieval/components/retrieval-config'
import useConfig from './use-config'

const i18nPrefix = 'nodes.hybridRetrieval'

const Panel: FC<NodePanelProps<HybridRetrievalNodeType>> = ({
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
    handleQueryAttachmentChange,
    filterStringVar,
    filterFileVar,
    handleModelChanged,
    handleCompletionParamsChange,
    handleRetrievalModeChange,
    handleMultipleRetrievalConfigChange,
    selectedDatasets,
    selectedDatasetsLoaded,
    handleOnDatasetsChange,
    rerankModelOpen,
    setRerankModelOpen,
    handleAddCondition,
    handleMetadataFilterModeChange,
    handleRemoveCondition,
    handleToggleConditionLogicalOperator,
    handleUpdateCondition,
    handleMetadataModelChange,
    handleMetadataCompletionParamsChange,
    availableStringVars,
    availableStringNodesWithParent,
    availableNumberVars,
    availableNumberNodesWithParent,
    showImageQueryVarSelector,
    graphs,
    graphsLoading,
    selectedGraphs,
    handleGraphsChange,
    handleGraphTopKChange,
    handleGraphRetrievalConfigChange,
  } = useConfig(id, data)
  const retrievalInputs = inputs as unknown as KnowledgeRetrievalNodeType

  const metadataList = useMemo(() => {
    return intersectionBy(...selectedDatasets.filter((dataset) => {
      return !!dataset.doc_metadata
    }).map((dataset) => {
      return dataset.doc_metadata!
    }), 'name')
  }, [selectedDatasets])

  return (
    <div className="pt-2">
      <div className="space-y-4 px-4 pb-2">
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

        {showImageQueryVarSelector && (
          <Field title={t('nodes.knowledgeRetrieval.queryAttachment', { ns: 'workflow' })}>
            <VarReferencePicker
              nodeId={id}
              readonly={readOnly}
              isShowNodeName
              value={inputs.query_attachment_selector}
              onChange={handleQueryAttachmentChange}
              filterVar={filterFileVar}
            />
          </Field>
        )}

        <Field
          title={t(`${i18nPrefix}.knowledge`, { ns: 'workflow' })}
          operations={(
            <div className="flex items-center space-x-1">
              <RetrievalConfig
                payload={{
                  retrieval_mode: inputs.retrieval_mode,
                  multiple_retrieval_config: inputs.multiple_retrieval_config,
                  single_retrieval_config: inputs.single_retrieval_config,
                }}
                onRetrievalModeChange={handleRetrievalModeChange}
                onMultipleRetrievalConfigChange={handleMultipleRetrievalConfigChange}
                singleRetrievalModelConfig={inputs.single_retrieval_config?.model}
                onSingleRetrievalModelChange={handleModelChanged}
                onSingleRetrievalModelParamsChange={handleCompletionParamsChange}
                readonly={readOnly || !selectedDatasets.length}
                rerankModalOpen={rerankModelOpen}
                onRerankModelOpenChange={setRerankModelOpen}
                selectedDatasets={selectedDatasets}
              />
              {!readOnly && (<div className="h-3 w-px bg-divider-regular"></div>)}
              {!readOnly && (
                <AddKnowledge
                  selectedIds={inputs.dataset_ids}
                  onChange={handleOnDatasetsChange}
                />
              )}
            </div>
          )}
        >
          <DatasetList
            list={selectedDatasets}
            onChange={handleOnDatasetsChange}
            readonly={readOnly}
          />
        </Field>

        <Field
          title={t(`${i18nPrefix}.knowledgeGraph`, { ns: 'workflow' })}
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

        <Field title={t(`${i18nPrefix}.graphTopK`, { ns: 'workflow' })}>
          <TopKInput
            value={inputs.graph_top_k}
            onChange={handleGraphTopKChange}
            readonly={readOnly}
          />
        </Field>
        <Field title={t(`${i18nPrefix}.graphRetrievalConfig`, { ns: 'workflow' })} supportFold>
          <GraphRetrievalConfig
            value={inputs.graph_retrieval_config}
            onChange={handleGraphRetrievalConfigChange}
            readonly={readOnly}
          />
        </Field>
      </div>
      <div className="mb-2 py-2">
        <MetadataFilter
          metadataList={metadataList}
          selectedDatasetsLoaded={selectedDatasetsLoaded}
          metadataFilterMode={retrievalInputs.metadata_filtering_mode}
          metadataFilteringConditions={retrievalInputs.metadata_filtering_conditions}
          handleAddCondition={handleAddCondition}
          handleMetadataFilterModeChange={handleMetadataFilterModeChange}
          handleRemoveCondition={handleRemoveCondition}
          handleToggleConditionLogicalOperator={handleToggleConditionLogicalOperator}
          handleUpdateCondition={handleUpdateCondition}
          metadataModelConfig={retrievalInputs.metadata_model_config}
          handleMetadataModelChange={handleMetadataModelChange}
          handleMetadataCompletionParamsChange={handleMetadataCompletionParamsChange}
          availableStringVars={availableStringVars}
          availableStringNodesWithParent={availableStringNodesWithParent}
          availableNumberVars={availableNumberVars}
          availableNumberNodesWithParent={availableNumberNodesWithParent}
        />
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
