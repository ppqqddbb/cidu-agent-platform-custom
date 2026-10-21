import type { RefObject } from 'react'
import type { KnowledgeGraphRetrievalNodeType } from './types'
import type { Props as FormProps } from '@/app/components/workflow/nodes/_base/components/before-run-form/form'
import type { InputVar, Variable } from '@/app/components/workflow/types'
import { useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { InputVarType } from '@/app/components/workflow/types'

const i18nPrefix = 'nodes.knowledgeGraphRetrieval'

type Params = {
  payload: KnowledgeGraphRetrievalNodeType
  runInputData: Record<string, unknown>
  runInputDataRef: RefObject<Record<string, unknown>>
  getInputVars: (textList: string[]) => InputVar[]
  setRunInputData: (data: Record<string, unknown>) => void
  toVarInputs: (variables: Variable[]) => InputVar[]
}

const useSingleRunFormParams = ({
  payload,
  runInputData,
  runInputDataRef,
  setRunInputData,
}: Params) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const query = typeof runInputData.query === 'string' ? runInputData.query : ''

  const setQuery = useCallback((newQuery: string) => {
    setRunInputData({
      ...runInputDataRef.current,
      query: newQuery,
    })
  }, [runInputDataRef, setRunInputData])

  const forms = useMemo<FormProps[]>(() => [
    {
      inputs: [{
        label: t(`${i18nPrefix}.queryText`, { ns: 'workflow' })!,
        variable: 'query',
        type: InputVarType.paragraph,
        required: false,
      }],
      values: { query },
      onChange: (keyValue: Record<string, unknown>) => setQuery(String(keyValue.query || '')),
    },
  ], [query, setQuery, t])

  const getDependentVars = () => {
    return [payload.query_variable_selector]
  }

  const getDependentVar = (variable: string) => {
    if (variable === 'query')
      return payload.query_variable_selector
  }

  return {
    forms,
    getDependentVars,
    getDependentVar,
  }
}

export default useSingleRunFormParams
