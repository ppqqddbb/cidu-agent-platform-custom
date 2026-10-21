import type { FC } from 'react'
import type { GraphRetrievalConfig } from '../types'
import { Select, SelectContent, SelectItem, SelectItemIndicator, SelectItemText, SelectTrigger, SelectValue } from '@langgenius/dify-ui/select'
import { Switch } from '@langgenius/dify-ui/switch'
import { useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import Input from '@/app/components/base/input'

const i18nPrefix = 'nodes.knowledgeGraphRetrieval.retrievalConfig'

const defaultConfig: Required<GraphRetrievalConfig> = {
  strategy: 'node',
  target_node_types: ['ProductModel'],
  match_mode: 'any',
  include_paths: true,
  path_depth: 8,
  include_parameters: true,
  parameter_relation_types: ['DEFINES_PARAMETER'],
  deduplicate: true,
}

type Props = {
  value?: GraphRetrievalConfig
  onChange: (value: GraphRetrievalConfig) => void
  readonly?: boolean
}

const splitList = (value: string) => value.split(',').map(item => item.trim()).filter(Boolean)

const RetrievalConfig: FC<Props> = ({
  value,
  onChange,
  readonly,
}) => {
  const { t: rawT } = useTranslation()
  const t = useCallback(
    (key: string, options?: Record<string, unknown>) =>
      (rawT as unknown as (key: string, options?: Record<string, unknown>) => string)(key, options),
    [rawT],
  )
  const config = useMemo(() => ({
    ...defaultConfig,
    ...(value || {}),
  }), [value])

  const updateConfig = useCallback((nextConfig: Partial<GraphRetrievalConfig>) => {
    onChange({
      ...config,
      ...nextConfig,
    })
  }, [config, onChange])

  return (
    <div className="space-y-3 rounded-lg bg-workflow-block-parma-bg p-3">
      <div className="space-y-1">
        <div className="system-xs-medium-uppercase text-text-tertiary">
          {t(`${i18nPrefix}.strategy`, { ns: 'workflow' })}
        </div>
        <Select
          defaultValue={config.strategy}
          disabled={readonly}
          onValueChange={strategy => updateConfig({ strategy: strategy as GraphRetrievalConfig['strategy'] })}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="path">
              <SelectItemText>{t(`${i18nPrefix}.strategyPath`, { ns: 'workflow' })}</SelectItemText>
              <SelectItemIndicator />
            </SelectItem>
            <SelectItem value="node">
              <SelectItemText>{t(`${i18nPrefix}.strategyNode`, { ns: 'workflow' })}</SelectItemText>
              <SelectItemIndicator />
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
      {config.strategy === 'node' && (
        <>
          <div className="space-y-1">
            <div className="system-xs-medium-uppercase text-text-tertiary">
              {t(`${i18nPrefix}.targetNodeTypes`, { ns: 'workflow' })}
            </div>
            <Input
              value={config.target_node_types.join(',')}
              onChange={e => updateConfig({ target_node_types: splitList(e.target.value) })}
              placeholder="ProductModel"
              disabled={readonly}
            />
          </div>
          <div className="space-y-1">
            <div className="system-xs-medium-uppercase text-text-tertiary">
              {t(`${i18nPrefix}.matchMode`, { ns: 'workflow' })}
            </div>
            <Select
              defaultValue={config.match_mode}
              disabled={readonly}
              onValueChange={matchMode => updateConfig({ match_mode: matchMode as GraphRetrievalConfig['match_mode'] })}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="any">
                  <SelectItemText>{t(`${i18nPrefix}.matchAny`, { ns: 'workflow' })}</SelectItemText>
                  <SelectItemIndicator />
                </SelectItem>
                <SelectItem value="all">
                  <SelectItemText>{t(`${i18nPrefix}.matchAll`, { ns: 'workflow' })}</SelectItemText>
                  <SelectItemIndicator />
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-between">
            <div className="system-xs-medium-uppercase text-text-tertiary">
              {t(`${i18nPrefix}.includePaths`, { ns: 'workflow' })}
            </div>
            <Switch
              checked={config.include_paths}
              onCheckedChange={checked => updateConfig({ include_paths: checked })}
              disabled={readonly}
            />
          </div>
          {config.include_paths && (
            <div className="space-y-1">
              <div className="system-xs-medium-uppercase text-text-tertiary">
                {t(`${i18nPrefix}.pathDepth`, { ns: 'workflow' })}
              </div>
              <Input
                type="number"
                min={1}
                max={8}
                value={config.path_depth}
                onChange={e => updateConfig({ path_depth: Number(e.target.value || 4) })}
                disabled={readonly}
              />
            </div>
          )}
          <div className="flex items-center justify-between">
            <div className="system-xs-medium-uppercase text-text-tertiary">
              {t(`${i18nPrefix}.includeParameters`, { ns: 'workflow' })}
            </div>
            <Switch
              checked={config.include_parameters}
              onCheckedChange={checked => updateConfig({ include_parameters: checked })}
              disabled={readonly}
            />
          </div>
          {config.include_parameters && (
            <div className="space-y-1">
              <div className="system-xs-medium-uppercase text-text-tertiary">
                {t(`${i18nPrefix}.parameterRelationTypes`, { ns: 'workflow' })}
              </div>
              <Input
                value={config.parameter_relation_types.join(',')}
                onChange={e => updateConfig({ parameter_relation_types: splitList(e.target.value) })}
                placeholder="DEFINES_PARAMETER"
                disabled={readonly}
              />
            </div>
          )}
          <div className="flex items-center justify-between">
            <div className="system-xs-medium-uppercase text-text-tertiary">
              {t(`${i18nPrefix}.deduplicate`, { ns: 'workflow' })}
            </div>
            <Switch
              checked={config.deduplicate}
              onCheckedChange={checked => updateConfig({ deduplicate: checked })}
              disabled={readonly}
            />
          </div>
        </>
      )}
    </div>
  )
}

export default RetrievalConfig
